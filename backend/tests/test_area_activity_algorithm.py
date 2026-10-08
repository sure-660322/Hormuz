"""区域活动纯算法测试：segment 装配、访问状态机、时长裁剪、按日汇总与 A/B 比较。

这些测试用手工构造的「边界报位行」（与 repository.ACTIVITY_BOUNDARIES 输出同形）
验证状态机；SQL 侧与源表的真实一致性由独立测试库样例验证覆盖。
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.area_activity import algorithm, params
from backend.app.services.area_activity.boundaries import (
    AreaBounds,
    default_bounds,
    describe_area,
    resolve_bounds,
)

UTC = timezone.utc
INSIDE = {"lat": 26.5, "lon": 56.5}
OUTSIDE = {"lat": 25.0, "lon": 55.0}


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 2, day, hour, minute, tzinfo=UTC)


def row(
    fix_id: int,
    moment: datetime,
    *,
    ship_id: int = 1,
    seg_no: int = 0,
    seq: int = 1,
    position: dict | None = None,
    is_start: bool = False,
    is_end: bool = False,
    break_kind: str | None = None,
    prev: tuple | None = None,
    next_: tuple | None = None,
    between_first: tuple | None = None,
    between_last: tuple | None = None,
    ship_name: str = "TEST SHIP",
    mmsi: str = "123456789",
    ship_type: str = "油轮",
) -> dict:
    """构造一条边界报位行；prev/next/between_* = (fix_id, moment, lat, lon)。"""
    spot = position or INSIDE
    payload = {
        "ship_id": ship_id, "ship_name": ship_name, "mmsi": mmsi, "ship_type": ship_type,
        "fix_id": fix_id, "recorded_at": moment, "latitude": spot["lat"],
        "longitude": spot["lon"], "speed": 10.0,
        "seg_no": seg_no, "ship_fix_seq": seq,
        "is_seg_start": is_start, "is_seg_end": is_end,
        "start_break_kind": break_kind,
        "prev_inside": None, "prev_at": None, "prev_fix_id": None,
        "prev_lat": None, "prev_lon": None,
        "between_first_fix_id": None, "between_first_at": None,
        "between_last_fix_id": None, "between_last_at": None,
        "next_inside": None, "next_at": None, "next_fix_id": None,
        "next_lat": None, "next_lon": None,
    }
    if prev is not None:
        payload.update({
            "prev_inside": prev[4] if len(prev) > 4 else False,
            "prev_fix_id": prev[0], "prev_at": prev[1],
            "prev_lat": prev[2], "prev_lon": prev[3],
        })
        if len(prev) > 4:
            payload["prev_inside"] = prev[4]
        else:
            payload["prev_inside"] = False
    if next_ is not None:
        payload.update({
            "next_inside": next_[4] if len(next_) > 4 else False,
            "next_fix_id": next_[0], "next_at": next_[1],
            "next_lat": next_[2], "next_lon": next_[3],
        })
    if between_first is not None:
        payload["between_first_fix_id"] = between_first[0]
        payload["between_first_at"] = between_first[1]
    if between_last is not None:
        payload["between_last_fix_id"] = between_last[0]
        payload["between_last_at"] = between_last[1]
    return payload


def test_half_open_containment_and_validation():
    bounds = default_bounds()
    assert bounds.contains(25.8, 55.8)          # 南/西边含
    assert bounds.contains(27.0999, 57.0999)
    assert not bounds.contains(27.1, 56.5)      # 北边不含
    assert not bounds.contains(26.5, 57.1)      # 东边不含
    assert not bounds.contains(25.7999, 56.5)
    assert not bounds.contains(26.5, 55.7999)

    with pytest.raises(ValueError, match="south < north"):
        AreaBounds(south=27.0, west=55.8, north=26.0, east=57.1).validate()
    with pytest.raises(ValueError, match="west < east"):
        AreaBounds(south=25.8, west=57.1, north=27.1, east=55.8).validate()
    with pytest.raises(ValueError, match="跨度"):
        AreaBounds(south=10.0, west=40.0, north=30.0, east=60.0).validate()
    with pytest.raises(ValueError, match="同时给出"):
        resolve_bounds(25.8, 55.8, None, None)

    bounds, is_default = resolve_bounds(None, None, None, None)
    assert is_default and bounds == default_bounds()
    described = describe_area(bounds, is_default=True)
    assert described["area_id"] == params.DEFAULT_AREA_ID
    assert described["version"] == params.DEFAULT_AREA_VERSION
    assert described["bounds"] == {"south": 25.8, "west": 55.8, "north": 27.1, "east": 57.1}


def test_boundary_distance_flags_near_edge():
    bounds = default_bounds()
    assert bounds.distance_to_boundary_m(26.5, 56.5) > params.BOUNDARY_BAND_M
    assert bounds.distance_to_boundary_m(26.5, 55.8001) < params.BOUNDARY_BAND_M


def test_complete_visit_with_observed_entry_and_exit():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True, prev=(1, at(25, 9, 50), 25.0, 55.0)),
        row(4, at(25, 10, 10), seq=4, is_end=True, next_=(5, at(25, 10, 15), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    assert len(visits) == 1
    visit = visits[0]
    assert visit.visit_key == "s1:f2"
    assert visit.prior_state == "outside"
    assert visit.entry.observed and visit.entry.observed_at == at(25, 10, 0)
    assert visit.entry.bracket_seconds == 600.0
    assert not visit.entry.wide_bracket
    assert visit.exit.observed and visit.exit.observed_at == at(25, 10, 10)
    assert visit.exit.bracket_seconds == 300.0
    assert visit.observed_seconds == 600.0

    payload = algorithm.visit_payload(visit, at(25, 10, 0), at(25, 11, 0))
    assert payload["status"] == "complete"
    assert payload["flags"] == []
    assert payload["window_seconds"] == 600.0
    assert payload["segments"][0]["fix_count"] == 3  # seq 2..4

    summary = algorithm.summarize(visits, at(25, 10, 0), at(25, 11, 0))
    assert summary["ships_observed"] == 1
    assert summary["observed_entry_count"] == 1
    assert summary["observed_exit_count"] == 1
    assert summary["observed_ship_hours"] == pytest.approx(600 / 3600, abs=1e-3)
    assert summary["complete_visit_count"] == 1


def test_gap_keeps_one_interrupted_visit_without_crediting_gap():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True, prev=(1, at(25, 9, 50), 25.0, 55.0)),
        row(3, at(25, 10, 10), seq=3, is_end=True, next_=(4, at(25, 12, 0), 26.5, 56.5, True)),
        row(4, at(25, 12, 0), seq=4, seg_no=1, is_start=True, break_kind="gap",
            prev=(3, at(25, 10, 10), 26.5, 56.5, True)),
        row(5, at(25, 12, 10), seq=5, seg_no=1, is_end=True,
            next_=(6, at(25, 12, 20), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    assert len(visits) == 1
    visit = visits[0]
    assert len(visit.segments) == 2
    assert visit.observed_seconds == 1200.0            # 两段各 600 s
    assert visit.unobserved_gap_seconds == 6600.0      # 10:10 → 12:00 不计入
    assert "gap_interrupted" in visit.flags
    payload = algorithm.visit_payload(visit, at(25, 10, 0), at(25, 13, 0))
    assert payload["status"] == "interrupted"
    assert payload["observed_seconds"] == 1200.0
    assert payload["segments"][1]["fix_count"] == 2


def test_left_returned_splits_visits_and_uses_between_evidence():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True, prev=(1, at(25, 9, 50), 25.0, 55.0)),
        row(3, at(25, 10, 5), seq=3, is_end=True, next_=(5, at(25, 14, 0), 26.5, 56.5, True)),
        row(5, at(25, 14, 0), seq=5, seg_no=1, is_start=True, break_kind="left_returned",
            prev=(3, at(25, 10, 5), 26.5, 56.5, True),
            between_first=(4, at(25, 10, 10)), between_last=(4, at(25, 10, 10))),
        row(6, at(25, 14, 5), seq=6, seg_no=1, is_end=True,
            next_=(7, at(25, 14, 10), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    assert len(visits) == 2
    first, second = visits

    assert first.exit.observed and first.exit.observed_at == at(25, 10, 5)
    assert first.exit.outside_fix["recorded_at"] == at(25, 10, 10)
    assert not first.exit.outside_evidence_in_context
    assert first.exit.bracket_seconds == 300.0

    assert second.prior_state == "outside"
    assert second.entry.observed and second.entry.observed_at == at(25, 14, 0)
    assert second.entry.outside_fix["id"] == 4
    assert second.entry.bracket_seconds == (at(25, 14, 0) - at(25, 10, 10)).total_seconds()
    assert second.entry.wide_bracket
    assert "outside_evidence_out_of_context" in second.flags
    assert second.visit_key == "s1:f5"


def test_jump_break_is_uncertain_and_not_credited():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True, is_end=True,
            prev=(1, at(25, 9, 50), 25.0, 55.0),
            next_=(3, at(25, 10, 1), 26.9, 57.0, True)),
        row(3, at(25, 10, 1), seq=3, seg_no=1, is_start=True, break_kind="jump",
            position={"lat": 26.9, "lon": 57.0},
            prev=(2, at(25, 10, 0), 26.5, 56.5, True)),
        row(4, at(25, 10, 30), seq=4, seg_no=1, is_end=True,
            next_=(5, at(25, 10, 40), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    assert len(visits) == 1
    visit = visits[0]
    assert "jump_break" in visit.flags
    assert visit.unobserved_gap_seconds == 60.0
    assert visit.observed_seconds == 1740.0           # 10:01 → 10:30
    assert visit.entry.observed                     # 进入仍被观测到（09:50 → 10:00）
    payload = algorithm.visit_payload(visit, at(25, 10, 0), at(25, 11, 0))
    assert payload["status"] == "uncertain"


def test_unknown_prior_state_counts_no_entry():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True),   # 无更早报位：前置状态未知
        row(3, at(25, 10, 10), seq=3, is_end=True, next_=(4, at(25, 10, 20), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    visit = visits[0]
    assert visit.prior_state == "unknown"
    assert not visit.entry.observed
    payload = algorithm.visit_payload(visit, at(25, 10, 0), at(25, 11, 0))
    assert payload["status"] == "truncated_start"
    summary = algorithm.summarize(visits, at(25, 10, 0), at(25, 11, 0))
    assert summary["observed_entry_count"] == 0
    assert summary["prior_state_unknown_visit_count"] == 1


def test_started_before_window_is_truncated_and_entry_not_counted():
    rows = [
        row(2, at(25, 8, 50), seq=2, is_start=True),
        row(3, at(25, 9, 10), seq=3, is_end=True, next_=(4, at(25, 9, 20), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    window_start = at(25, 9, 0)
    payload = algorithm.visit_payload(visits[0], window_start, at(25, 11, 0))
    assert payload["started_before_window"]
    assert payload["status"] == "truncated_start"
    assert payload["window_seconds"] == 600.0
    summary = algorithm.summarize(visits, window_start, at(25, 11, 0))
    assert summary["ships_observed"] == 1
    assert summary["observed_entry_count"] == 0
    assert summary["observed_ship_seconds"] == 600.0
    assert summary["truncated_start_visit_count"] == 1


def test_unclosed_visit_is_truncated_end():
    rows = [row(2, at(25, 10, 0), seq=2, is_start=True, is_end=True,
                prev=(1, at(25, 9, 50), 25.0, 55.0))]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    payload = algorithm.visit_payload(visits[0], at(25, 10, 0), at(25, 11, 0))
    assert payload["status"] == "truncated_end"
    assert not payload["exit"]["observed"]
    summary = algorithm.summarize(visits, at(25, 10, 0), at(25, 11, 0))
    assert summary["observed_exit_count"] == 0
    assert summary["observed_ship_seconds"] == 0.0


def test_near_boundary_event_is_flagged_without_changing_counts():
    rows = [
        row(2, at(25, 10, 0), seq=2, is_start=True, position={"lat": 26.5, "lon": 55.8002},
            prev=(1, at(25, 9, 50), 25.0, 55.0)),
        row(3, at(25, 10, 10), seq=3, is_end=True, position={"lat": 26.5, "lon": 55.8002},
            next_=(4, at(25, 10, 20), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    payload = algorithm.visit_payload(visits[0], at(25, 10, 0), at(25, 11, 0))
    assert "near_boundary_entry" in payload["flags"]
    assert "near_boundary_exit" in payload["flags"]
    summary = algorithm.summarize(visits, at(25, 10, 0), at(25, 11, 0))
    assert summary["observed_entry_count"] == 1
    assert summary["near_boundary_event_count"] == 1


def test_daily_clipping_splits_ship_time_across_midnight():
    rows = [
        row(2, at(25, 23, 45), seq=2, is_start=True, prev=(1, at(25, 23, 35), 25.0, 55.0)),
        row(3, at(26, 0, 15), seq=3, is_end=True, next_=(4, at(26, 0, 25), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    start, end = at(25, 0, 0), at(27, 0, 0)
    daily = algorithm.daily_breakdown(visits, start, end)
    assert [item["date"] for item in daily] == ["2026-02-25", "2026-02-26"]
    assert daily[0]["observed_ship_seconds"] == 900.0
    assert daily[1]["observed_ship_seconds"] == 900.0
    assert daily[0]["ships_observed"] == 1 and daily[1]["ships_observed"] == 1
    assert daily[0]["observed_entry_count"] == 1
    assert daily[1]["observed_entry_count"] == 0
    assert daily[1]["observed_exit_count"] == 1
    summary = algorithm.summarize(visits, start, end)
    assert summary["ships_observed"] == 1                 # 每日去重不相加
    assert summary["observed_ship_seconds"] == 1800.0


def test_daily_window_clipping_outside_query_window():
    rows = [
        row(2, at(25, 23, 50), seq=2, is_start=True, prev=(1, at(25, 23, 40), 25.0, 55.0)),
        row(3, at(26, 0, 20), seq=3, is_end=True, next_=(4, at(26, 0, 30), 25.0, 55.0)),
    ]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    start, end = at(26, 0, 0), at(26, 1, 0)
    summary = algorithm.summarize(visits, start, end)
    assert summary["observed_ship_seconds"] == 1200.0     # 00:00–00:20 交集
    assert summary["ships_observed"] == 1
    daily = algorithm.daily_breakdown(visits, start, end)
    assert len(daily) == 1 and daily[0]["observed_ship_seconds"] == 1200.0
    # 窗外（02-25）的进入不计入本窗
    assert summary["observed_entry_count"] == 0


def test_compare_metrics_zero_base_and_per_day():
    summary_a = {"ships_observed": 0, "observed_entry_count": 0, "observed_exit_count": 0,
                 "observed_ship_hours": 0.0}
    summary_b = {"ships_observed": 4, "observed_entry_count": 6, "observed_exit_count": 5,
                 "observed_ship_hours": 12.0}
    metrics = {item["key"]: item for item in algorithm.compare_metrics(summary_a, summary_b, 2, 4)}
    assert metrics["ships_observed"]["change_rate"] is None
    assert metrics["ships_observed"]["delta"] == 4
    assert metrics["observed_ship_hours_per_day"]["a"] == 0.0
    assert metrics["observed_ship_hours_per_day"]["b"] == 3.0
    assert metrics["observed_ship_hours_per_day"]["change_rate"] is None

    metrics = {item["key"]: item for item in algorithm.compare_metrics(
        {"ships_observed": 2, "observed_entry_count": 2, "observed_exit_count": 2,
         "observed_ship_hours": 4.0},
        {"ships_observed": 3, "observed_entry_count": 4, "observed_exit_count": 3,
         "observed_ship_hours": 5.0},
        2, 2,
    )}
    assert metrics["ships_observed"]["change_rate"] == 0.5
    assert metrics["observed_ship_hours_per_day"]["a"] == 2.0
    assert metrics["observed_ship_hours_per_day"]["b"] == 2.5


def test_segments_are_dropped_when_truncated_mid_visit():
    rows = [row(2, at(25, 10, 0), seq=2, is_start=True, prev=(1, at(25, 9, 50), 25.0, 55.0))]
    visits = algorithm.assemble_visits(rows, default_bounds(), params.GAP_SECONDS)
    assert visits == [] or visits[0].segments[0].end_at is not None
