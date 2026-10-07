"""区域活动服务层测试：参数校验、上限拒绝、no_data 与有效零结果的区分、在场新鲜度。

数据库访问全部用打桩替换（backend/tests/conftest.py 已提供占位环境变量）；
真实 SQL 与源表的对照由独立测试库样例验证覆盖。
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.area_activity import params, service
from backend.app.services.area_activity.boundaries import default_bounds

UTC = timezone.utc
START = datetime(2026, 2, 25, 0, 0, tzinfo=UTC)
END = datetime(2026, 2, 26, 0, 0, tzinfo=UTC)


def stats(**overrides) -> dict:
    payload = {
        "scoped_fix_count": 10, "region_fix_count": 4, "window_region_fix_count": 2,
        "first_fix_at": START, "last_fix_at": END,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def patched(monkeypatch):
    """把仓储层替换为可编程打桩；默认空批次、空边界行、给定统计。"""
    state = {"rows": [], "stats": stats(), "coverage": []}

    monkeypatch.setattr(service.repository, "apply_session_settings", lambda *a, **k: None)
    monkeypatch.setattr(service.repository, "fetch_activity_boundaries", lambda *a, **k: state["rows"])
    monkeypatch.setattr(service.repository, "fetch_scope_stats", lambda *a, **k: state["stats"])
    monkeypatch.setattr(service.repository, "fetch_batch_coverage", lambda *a, **k: state["coverage"])
    monkeypatch.setattr(service.repository, "fetch_latest_fixes", lambda *a, **k: state["snapshot_rows"])
    state["snapshot_rows"] = []
    return state


def activity(**overrides):
    payload = dict(start=START, end=END, bounds=default_bounds(), is_default=True)
    payload.update(overrides)
    return service.query_activity(None, **payload)


def test_activity_requires_timezone_and_ordered_window(patched):
    with pytest.raises(service.AreaActivityError, match="时区"):
        activity(start=START.replace(tzinfo=None))
    with pytest.raises(service.AreaActivityError, match="start < end"):
        activity(end=START)
    with pytest.raises(service.AreaActivityError, match="最长 7 天"):
        activity(end=START + timedelta(days=8))


def test_activity_rejects_lookback_and_limit_out_of_range(patched):
    with pytest.raises(service.AreaActivityError, match="state_lookback_seconds"):
        activity(lookback_seconds=-1)
    with pytest.raises(service.AreaActivityError, match="state_lookahead_seconds"):
        activity(lookahead_seconds=params.MAX_LOOKBACK_SECONDS + 1)
    with pytest.raises(service.AreaActivityError, match="visit_limit"):
        activity(visit_limit=0)
    with pytest.raises(service.AreaActivityError, match="visit_limit"):
        activity(visit_limit=params.MAX_VISIT_ROWS + 1)


def test_no_scope_fixes_is_no_data(patched):
    patched["stats"] = stats(scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
                             first_fix_at=None, last_fix_at=None)
    payload = activity()
    assert payload["status"] == "no_data"
    assert payload["summary"]["ships_observed"] == 0
    assert any("没有任何 nnu_ais 报位" in item for item in payload["limitations"])


def test_scope_without_region_fix_is_valid_zero(patched):
    patched["stats"] = stats(region_fix_count=0, window_region_fix_count=0)
    payload = activity()
    assert payload["status"] == "ok"
    assert payload["summary"]["ships_observed"] == 0
    assert payload["summary"]["observed_ship_seconds"] == 0.0
    assert any("有效零结果" in item for item in payload["limitations"])


def test_scanned_fix_limit_rejects_without_truncating(patched):
    patched["rows"] = [{"ship_id": 1, **stats(scoped_fix_count=params.MAX_SCANNED_FIXES + 1)}]
    with pytest.raises(service.AreaActivityError, match="超过上限"):
        activity()


def test_boundary_row_limit_rejects(patched):
    patched["rows"] = [{"ship_id": 1, **stats()}] * (params.MAX_BOUNDARY_ROWS + 1)
    with pytest.raises(service.AreaActivityError, match="访问明细超过上限"):
        activity()


def test_candidate_ship_limit_rejects(patched):
    patched["rows"] = [{"ship_id": index, **stats()} for index in range(
        params.MAX_CANDIDATE_SHIPS + 1)]
    with pytest.raises(service.AreaActivityError, match="候选船数"):
        activity()


def test_daily_and_summary_come_from_full_visits_even_when_detail_truncated(patched):
    rows = []
    for index in range(4):
        ship_id = index + 1
        base = START + timedelta(hours=index)
        rows.append({
            "ship_id": ship_id, "ship_name": f"SHIP {ship_id}", "mmsi": f"10000000{index}",
            "ship_type": "油轮", "fix_id": 100 + index, "recorded_at": base,
            "latitude": 26.5, "longitude": 56.5, "speed": 8.0,
            "seg_no": 0, "ship_fix_seq": 1, "is_seg_start": True, "is_seg_end": True,
            "start_break_kind": None,
            "prev_inside": False, "prev_at": base - timedelta(minutes=10),
            "prev_fix_id": 50 + index, "prev_lat": 25.0, "prev_lon": 55.0,
            "between_first_fix_id": None, "between_first_at": None,
            "between_last_fix_id": None, "between_last_at": None,
            "next_inside": False, "next_at": base + timedelta(minutes=5),
            "next_fix_id": 200 + index, "next_lat": 25.0, "next_lon": 55.0,
            **stats(),
        })
    patched["rows"] = rows
    payload = activity(visit_limit=2)
    assert payload["limits"]["detail_truncated"] is True
    assert payload["limits"]["returned_visit_count"] == 2
    assert len(payload["visits"]) == 2
    assert payload["summary"]["ships_observed"] == 4          # 汇总不受明细截断影响
    assert payload["summary"]["observed_entry_count"] == 4
    assert payload["status"] == "partial"


def test_ship_type_filter_resolution(patched):
    payload = activity(ship_type_values=["油轮", params.SHIP_TYPE_MISSING])
    filters = payload["query"]["filters"]
    assert filters["ship_types"] == ["油轮", params.SHIP_TYPE_MISSING]
    assert filters["include_missing"] is True
    assert filters["include_unknown"] is False

    payload = activity(ship_type_values=[params.SHIP_TYPE_UNKNOWN])
    assert payload["query"]["filters"]["include_unknown"] is True

    payload = activity()
    assert payload["query"]["filters"]["ship_types"] is None


def test_compare_rejects_overlong_window_and_reports_no_data(patched):
    with pytest.raises(service.AreaActivityError, match="B 窗口"):
        service.compare_activity(
            None, start_a=START, end_a=END,
            start_b=START, end_b=START + timedelta(days=9),
            bounds=default_bounds(), is_default=True,
        )

    patched["stats"] = stats(scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
                             first_fix_at=None, last_fix_at=None)
    payload = service.compare_activity(
        None, start_a=START, end_a=END,
        start_b=START + timedelta(days=1), end_b=START + timedelta(days=3),
        bounds=default_bounds(), is_default=True,
    )
    assert payload["status"] == "no_data"
    assert payload["comparability"]["equal_length"] is False
    assert any("不可比" in item for item in payload["comparability"]["warnings"])
    metrics = {item["key"]: item for item in payload["metrics"]}
    assert metrics["ships_observed"]["change_rate"] is None
    assert metrics["observed_ship_hours_per_day"]["a"] == 0.0


def test_activity_passes_batch_ids_and_ship_types_to_repository(monkeypatch):
    """批次筛选必须真的进入查询参数（否则统计与覆盖说明会不一致）。"""
    captured = {}

    def fake_fetch(db, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(service.repository, "apply_session_settings", lambda *a, **k: None)
    monkeypatch.setattr(service.repository, "fetch_activity_boundaries", fake_fetch)
    monkeypatch.setattr(service.repository, "fetch_scope_stats", lambda *a, **k: stats(
        scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
        first_fix_at=None, last_fix_at=None,
    ))
    monkeypatch.setattr(service.repository, "fetch_batch_coverage", lambda *a, **k: [])

    payload = activity(batch_ids=[4], ship_type_values=["油轮"])
    assert captured["batch_ids"] == [4]
    assert captured["ship_types"] == ["油轮"]
    assert payload["query"]["filters"]["batch_ids"] == [4]


def test_activity_sql_scopes_batches_and_probes_short_excursions():
    """SQL 文本层：批次条件覆盖上下文与越界探测；短间隔也走探测分支。"""
    from backend.app.services.area_activity import params as activity_params
    from backend.app.services.area_activity import repository

    sql = str(repository.ACTIVITY_BOUNDARIES).format(
        inside=repository.INSIDE_EXPRESSION,
        scope=repository.SCOPE_PREDICATE,
        ship_type_scope_filter="",
        batch_probe_filter=repository.BATCH_PROBE_FILTER,
        batch_probe_filter_x=repository.BATCH_PROBE_FILTER_X,
    )
    # 上下文过滤 + 首探测(b) + 末探测(x) 都应带批次条件
    assert sql.count("source_batch_id") >= 3
    assert sql.count("CAST(:batch_ids AS bigint[])") >= 3
    assert ":probe_seconds" in sql
    assert sql.count(":probe_seconds") >= 2
    # 探测阈值由外扩范围与最大可信航速推出，必须小于缺报阈值
    assert activity_params.EXCURSION_PROBE_SECONDS == 480
    assert activity_params.EXCURSION_PROBE_SECONDS < activity_params.GAP_SECONDS


def test_snapshot_freshness_and_no_fallback(patched):
    patched["snapshot_rows"] = [
        # 新鲜且在区内
        {"ship_id": 1, "name": "A", "mmsi": "1", "ship_type": "油轮", "flag": None,
         "fix_id": 11, "latitude": 26.5, "longitude": 56.5, "speed": 5.0,
         "recorded_at": START - timedelta(minutes=10), "source_batch_id": 1},
        # 新鲜但在区外：不得用更早的区内报位补回（该船当前只有这一条）
        {"ship_id": 2, "name": "B", "mmsi": "2", "ship_type": "货船", "flag": None,
         "fix_id": 12, "latitude": 25.0, "longitude": 55.0, "speed": 5.0,
         "recorded_at": START - timedelta(minutes=5), "source_batch_id": 1},
        # 过期：不计入在场
        {"ship_id": 3, "name": "C", "mmsi": "3", "ship_type": "货船", "flag": None,
         "fix_id": 13, "latitude": 26.6, "longitude": 56.6, "speed": 5.0,
         "recorded_at": START - timedelta(hours=3), "source_batch_id": 1},
    ]
    payload = service.query_snapshot(
        None, at=START, bounds=default_bounds(), is_default=True,
    )
    assert payload["status"] == "ok"
    assert payload["summary"] == {
        "in_area_count": 1, "out_of_area_fresh_count": 1, "stale_fix_count": 1,
        "evaluated_ship_count": 3, "freshness_seconds": params.FRESHNESS_SECONDS,
    }
    assert [ship["ship_id"] for ship in payload["ships"]] == [1]
    assert payload["ships"][0]["age_seconds"] == 600.0
    assert payload["limits"]["list_truncated"] is False


def test_snapshot_requires_timezone_and_bounds(patched):
    with pytest.raises(service.AreaActivityError, match="时区"):
        service.query_snapshot(None, at=START.replace(tzinfo=None),
                               bounds=default_bounds(), is_default=True)
    with pytest.raises(service.AreaActivityError, match="freshness_seconds"):
        service.query_snapshot(None, at=START, bounds=default_bounds(), is_default=True,
                               freshness_seconds=0)
