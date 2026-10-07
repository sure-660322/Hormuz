"""动态通行统计/比较/证据/元数据服务测试（issue #40）。

与 test_real_ais_agent_passages.py 相同的假会话模式：不连接真实数据库，
按 (closure_at, end_at) 返回预置的汇总行与变迁行，验证分窗编排、稳定键去重、
方向/船型过滤下推、零结果与无观测区分、比较零基期与分页完整性。
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.agent import strait_statistics as stats
from backend.app.services.agent.config import UNKNOWN_SHIP_TYPE_OPTION
from backend.app.services.agent.results import build_result

UTC = timezone.utc
D1 = datetime(2026, 2, 26, tzinfo=UTC)   # UTC 自然日窗 [D1, D1+1d)


class _Mapped:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def one(self):
        return self.rows[0]

    def all(self):
        return self.rows


def _transition(ship_id, recorded_at, *, previous_at, name=None, ship_type=None,
                start_fix_id=None, completion_fix_id=None,
                previous_side="west", side="east", left_corridor=False):
    return {
        "ship_id": ship_id, "name": name or f"ship {ship_id}",
        "ship_type": ship_type,
        "side": side, "previous_side": previous_side,
        "recorded_at": recorded_at, "longitude": 56.8 if side == "east" else 56.1,
        "latitude": 26.5,
        "previous_at": previous_at, "previous_lon": 56.1, "previous_lat": 26.5,
        "left_corridor": left_corridor,
        "start_fix_id": start_fix_id if start_fix_id is not None else recorded_at.hour * 100 + ship_id,
        "completion_fix_id": completion_fix_id if completion_fix_id is not None else recorded_at.hour * 100 + ship_id + 1,
    }


class _FakeSession:
    """按窗口返回预置数据；记录全部调用供断言。"""

    def __init__(self, windows=None, meta_types=(), meta_batches=()):
        self.windows = windows or {}   # (closure_at, end_at) -> (summary_dict, [rows])
        self.meta_types = list(meta_types)
        self.meta_batches = list(meta_batches)
        self.calls = []

    def execute(self, query, params):
        sql = str(query)
        self.calls.append((sql, dict(params)))
        if "window_position_count" in sql:  # 门线窗口汇总（与批次覆盖 count(*) 区分）
            summary, _ = self.windows.get(
                (params["closure_at"], params["end_at"]),
                ({"position_count": 0, "window_position_count": 0,
                  "coverage_start": None, "coverage_end": None}, []),
            )
            return _Mapped([summary])
        if "GROUP BY s.ship_type" in sql:
            return _Mapped(self.meta_types)
        if "GROUP BY p.source_batch_id" in sql:
            return _Mapped(self.meta_batches)
        _, rows = self.windows.get(
            (params["closure_at"], params["end_at"]),
            ({"position_count": 0, "window_position_count": 0,
              "coverage_start": None, "coverage_end": None}, []),
        )
        return _Mapped(rows)


def _summary(count):
    return {"position_count": count, "window_position_count": count,
            "coverage_start": D1, "coverage_end": D1 + timedelta(hours=1)}


def _windows(*days):
    """days: (closure_at, position_count, [rows])"""
    return {(closure, closure + timedelta(days=1)): (_summary(count), rows)
            for closure, count, rows in days}


# --------------------------------------------------------------- 统计服务

def test_multi_day_aggregation_and_window_dedupe():
    day2 = D1 + timedelta(days=1)
    ship_a_day1 = _transition(1, D1 + timedelta(hours=6), previous_at=D1 + timedelta(hours=4))
    ship_b_day1 = _transition(2, D1 + timedelta(hours=8), previous_at=D1 + timedelta(hours=7),
                              side="west", previous_side="east")  # 入湾
    ship_a_day2 = _transition(1, day2 + timedelta(hours=3), previous_at=day2 + timedelta(hours=1))
    session = _FakeSession(_windows(
        (D1, 10, [ship_a_day1, ship_b_day1]),
        (day2, 20, [ship_a_day2]),
    ))
    result = stats.query_strait_passage_statistics(session, D1, day2 + timedelta(days=1))
    assert result.status == "ok"
    assert [day.day for day in result.daily] == [D1.date(), day2.date()]
    assert result.daily[0].passage_count == 2
    assert result.daily[0].inbound_count == 1 and result.daily[0].outbound_count == 1
    assert result.daily[1].passage_count == 1
    # 全窗去重：ship 1 两天各一次 → 次数 3，去重艘数 2；每日去重之和(2+1=3)不等于全窗艘数
    assert result.window.passage_count == 3
    assert result.window.unique_ship_count == 2
    assert result.daily[0].unique_ship_count + result.daily[1].unique_ship_count == 3
    # 逐日编排：每天 2 条 SQL（汇总 + 变迁）
    assert len(session.calls) == 4


def test_stable_key_dedupes_across_sub_windows():
    """同一稳定键在相邻子窗重复出现时只计一次（不依赖 P1/P2 编号）。"""
    day2 = D1 + timedelta(days=1)
    shared = _transition(1, D1 + timedelta(hours=23), previous_at=D1 + timedelta(hours=21),
                         start_fix_id=100, completion_fix_id=101)
    duplicate = _transition(1, D1 + timedelta(hours=23), previous_at=D1 + timedelta(hours=21),
                            start_fix_id=100, completion_fix_id=101)
    session = _FakeSession(_windows(
        (D1, 5, [shared]),
        (day2, 5, [duplicate]),
    ))
    result = stats.query_strait_passage_statistics(session, D1, day2 + timedelta(days=1))
    assert result.window.passage_count == 1


def test_cross_midnight_completion_day_by_observed_time():
    """完成观测时间（UTC）决定归日；前置侧别可来自前一天。"""
    day2 = D1 + timedelta(days=1)
    crossing = _transition(7, day2 + timedelta(minutes=5), previous_at=D1 + timedelta(hours=22))
    session = _FakeSession(_windows(
        (D1, 5, []),
        (day2, 5, [crossing]),
    ))
    result = stats.query_strait_passage_statistics(session, D1, day2 + timedelta(days=1))
    assert result.daily[0].passage_count == 0 and result.daily[0].status == "zero"
    assert result.daily[1].passage_count == 1


def test_uncertain_candidates_not_in_confirmed_and_partial_status():
    session = _FakeSession(_windows(
        (D1, 5, [
            _transition(1, D1 + timedelta(hours=2), previous_at=D1 - timedelta(hours=7)),  # 长间隔
            _transition(2, D1 + timedelta(hours=3), previous_at=D1 + timedelta(hours=2),
                        left_corridor=True),
        ]),
    ))
    result = stats.query_strait_passage_statistics(session, D1, D1 + timedelta(days=1))
    assert result.status == "partial"
    assert result.window.passage_count == 0
    assert result.window.uncertain_candidate_count == 2
    assert result.daily[0].status == "partial"


def test_no_observation_differs_from_zero():
    """全部子窗无报位 → no_data，不解释为真实零通行。"""
    session = _FakeSession(_windows((D1, 0, []), (D1 + timedelta(days=1), 0, [])))
    result = stats.query_strait_passage_statistics(session, D1, D1 + timedelta(days=2))
    assert result.status == "no_data"
    assert all(day.status == "no_observation" for day in result.daily)
    assert any("真实零通行" in item for item in result.limitations)


def test_period_over_7_days_rejected():
    session = _FakeSession()
    with pytest.raises(ValueError, match="7 天"):
        stats.query_strait_passage_statistics(session, D1, D1 + timedelta(days=8))


def test_ship_type_and_direction_filters_pushed_to_sql():
    session = _FakeSession(_windows((D1, 5, [])))
    stats.query_strait_passage_statistics(
        session, D1, D1 + timedelta(days=1),
        ship_types=["油轮", UNKNOWN_SHIP_TYPE_OPTION], direction="inbound",
    )
    _, params = session.calls[1]  # 变迁查询
    assert params["ship_type_list"] == ["油轮"]
    assert params["unknown_type_list"] == ["未知"]
    assert params["direction"] == "east_to_west"
    transitions_sql = session.calls[1][0]
    assert "CAST(:direction AS text)" in transitions_sql
    assert "ship_type = ANY(CAST(:ship_type_list AS text[]))" in transitions_sql


def test_unknown_only_filter_and_window_position_count():
    session = _FakeSession(_windows((D1, 5, [])))
    stats.query_strait_passage_statistics(
        session, D1, D1 + timedelta(hours=6), ship_types=[UNKNOWN_SHIP_TYPE_OPTION],
    )
    _, params = session.calls[1]
    assert "ship_type_list" not in params  # 纯未知桶不下发已知列表
    assert params["unknown_type_list"] == ["未知"]


# --------------------------------------------------------------- 比较服务

def _period(closure, count, rows):
    return (closure, count, rows)


def test_compare_delta_rate_and_zero_base():
    day2 = D1 + timedelta(days=1)
    day3 = D1 + timedelta(days=2)
    session = _FakeSession(_windows(
        _period(D1, 5, []),
        _period(day2, 5, []),
        _period(day3, 5, [_transition(1, day3 + timedelta(hours=2), previous_at=day3)]),
    ))
    result = stats.compare_strait_passage_statistics(
        session, D1, D1 + timedelta(days=2), day3, day3 + timedelta(days=1),
    )
    by_metric = {m.metric: m for m in result.metrics}
    assert by_metric["passage_count"].a_value == 0 and by_metric["passage_count"].b_value == 1
    assert by_metric["passage_count"].delta == 1
    assert by_metric["passage_count"].change_rate is None  # A=0 不产生 Infinity/NaN
    assert result.a_avg_passages_per_day == 0  # A 期 2 天均为有效零结果
    assert result.b_avg_passages_per_day == 1
    assert any("null" in note for note in result.comparability_notes)


def test_compare_overlap_and_unequal_windows_noted():
    session = _FakeSession(_windows(
        _period(D1, 5, [_transition(1, D1 + timedelta(hours=2), previous_at=D1)]),
        _period(D1 + timedelta(hours=12), 5, []),
        _period(D1 + timedelta(days=1), 5, []),
    ))
    result = stats.compare_strait_passage_statistics(
        session, D1, D1 + timedelta(days=1),
        D1 + timedelta(hours=12), D1 + timedelta(days=2),
    )
    assert result.windows_overlap
    assert any("重叠" in note for note in result.comparability_notes)
    assert result.a_period_days != result.b_period_days
    assert any("窗口长度不同" in note for note in result.comparability_notes)


# --------------------------------------------------------------- 证据分页

def _five_confirmed():
    return [
        _transition(index + 1, D1 + timedelta(hours=2 * index + 2),
                    previous_at=D1 + timedelta(hours=2 * index))
        for index in range(5)
    ]


def test_evidence_pagination_keeps_complete_counts():
    session = _FakeSession(_windows((D1, 5, _five_confirmed())))
    page1 = stats.query_strait_passage_evidence(session, D1, D1 + timedelta(days=1), page=1, page_size=2)
    page3 = stats.query_strait_passage_evidence(session, D1, D1 + timedelta(days=1), page=3, page_size=2)
    assert page1["matched_count"] == 5 and page1["confirmed_count"] == 5
    assert page1["returned_count"] == 2 and page3["returned_count"] == 1
    assert page1["page_count"] == 3
    keys = {item["stable_key"] for item in page1["items"] + page3["items"]}
    assert len(keys) == 3  # 分页不重复/不遗漏
    with pytest.raises(ValueError, match="超出范围"):
        stats.query_strait_passage_evidence(session, D1, D1 + timedelta(days=1), page=4, page_size=2)


def test_evidence_day_filter_and_uncertain_inclusion():
    day2 = D1 + timedelta(days=1)
    uncertain = _transition(9, D1 + timedelta(hours=3), previous_at=D1 - timedelta(hours=8))
    confirmed_day2 = _transition(8, day2 + timedelta(hours=3), previous_at=day2 + timedelta(hours=1))
    session = _FakeSession(_windows(
        (D1, 5, [uncertain]),
        (day2, 5, [confirmed_day2]),
    ))
    only_confirmed = stats.query_strait_passage_evidence(
        session, D1, day2 + timedelta(days=1), day=D1.date(),
    )
    assert only_confirmed["matched_count"] == 0 and only_confirmed["uncertain_candidate_count"] == 1
    with_uncertain = stats.query_strait_passage_evidence(
        session, D1, day2 + timedelta(days=1), day=D1.date(), include_uncertain=True,
    )
    assert with_uncertain["matched_count"] == 1
    assert with_uncertain["items"][0]["uncertain_reason"] == "long_gap"
    day2_confirmed = stats.query_strait_passage_evidence(
        session, D1, day2 + timedelta(days=1), day=day2.date(),
    )
    assert day2_confirmed["matched_count"] == 1  # 2h 间隔 → 确定通行
    assert day2_confirmed["uncertain_candidate_count"] == 0
    assert day2_confirmed["confirmed_count"] == 1
    with pytest.raises(ValueError, match="day"):
        stats.query_strait_passage_evidence(session, D1, day2 + timedelta(days=1), day=day2.date() + timedelta(days=5))
    with pytest.raises(ValueError, match="day"):
        stats.query_strait_passage_evidence(session, D1, day2 + timedelta(days=1), day=day2.date() + timedelta(days=5))


# --------------------------------------------------------------- 元数据

def test_meta_ship_types_unknown_bucket_and_case_batch():
    session = _FakeSession(
        meta_types=[{"ship_type": "油轮", "ship_count": 3}, {"ship_type": None, "ship_count": 2},
                    {"ship_type": "未知", "ship_count": 1}],
        meta_batches=[
            {"batch_id": 1, "position_count": 10, "ship_count": 5,
             "coverage_start": D1, "coverage_end": D1 + timedelta(hours=1)},
            {"batch_id": 8, "position_count": 4, "ship_count": 1,
             "coverage_start": D1, "coverage_end": D1 + timedelta(hours=1)},
        ],
    )
    meta = stats.get_strait_passage_meta(session)
    values = {option["value"]: option["ship_count"] for option in meta.ship_type_options}
    assert values["油轮"] == 3
    assert values[UNKNOWN_SHIP_TYPE_OPTION] == 3  # NULL + 未知 合并
    kinds = {row["batch_id"]: row["kind"] for row in meta.coverage}
    assert kinds[1] == "seven_day_batch" and kinds[8] == "case_supplement"


# --------------------------------------------------------------- 面板动作

def test_build_result_analysis_actions_bind_own_query():
    envelope = {
        "call_id": "call_001", "tool_name": "query_strait_passage_statistics", "status": "ok",
        "start_at": "2026-02-26T00:00:00+00:00", "end_at": "2026-02-27T00:00:00+00:00",
        "ship_types": ["油轮"], "direction": "inbound",
        "window": {"passage_count": 46}, "daily": [], "determination_version": "v",
        "limitations": [],
    }
    outcome = build_result(
        ["query_strait_passage_statistics"], {"call_001": envelope},
        D1, D1 + timedelta(days=1), "测试", "回答",
    )
    assert len(outcome["analysis_actions"]) == 1
    action = outcome["analysis_actions"][0]
    assert action["type"] == "passage_analysis"
    assert action["query"]["mode"] == "single"
    assert action["query"]["ship_types"] == ["油轮"]
    assert action["query"]["start_at"] == "2026-02-26T00:00:00+00:00"  # 绑定自己的参数
    assert outcome["analysis_actions"][0]["summary"]["window"]["passage_count"] == 46

    compare_envelope = {
        "call_id": "call_002", "tool_name": "compare_strait_passage_statistics", "status": "ok",
        "a_period": {"start_at": "2026-02-25T00:00:00+00:00", "end_at": "2026-02-27T00:00:00+00:00"},
        "b_period": {"start_at": "2026-03-01T00:00:00+00:00", "end_at": "2026-03-03T00:00:00+00:00"},
        "ship_types": None, "direction": None, "metrics": [], "determination_version": "v",
        "limitations": [],
    }
    outcome2 = build_result(
        ["compare_strait_passage_statistics"], {"call_002": compare_envelope},
        D1, D1 + timedelta(days=1), "测试", "回答",
    )
    assert outcome2["analysis_actions"][0]["query"]["mode"] == "compare"
    assert outcome2["analysis_actions"][0]["query"]["b_start_at"] == "2026-03-01T00:00:00+00:00"

    failed = dict(envelope, call_id="call_003", status="error")
    outcome3 = build_result(
        ["query_strait_passage_statistics"], {"call_003": failed},
        D1, D1 + timedelta(days=1), "测试", "回答",
    )
    assert outcome3["analysis_actions"] == []  # 失败调用不生成动作


def test_direction_filtered_payload_masks_opposite_direction():
    """方向过滤时未统计方向置 null（不是 0），避免模型把「未统计」误述为「零通行」。"""
    from backend.app.services.agent.business_tools import _mask_uncounted_direction

    payload = {
        "direction": "east_to_west",
        "window": {"passage_count": 5, "inbound_count": 5, "outbound_count": 0},
        "daily": [{"day": "2026-02-28", "inbound_count": 5, "outbound_count": 0}],
    }
    masked = _mask_uncounted_direction(payload)
    assert masked["window"]["outbound_count"] is None
    assert masked["daily"][0]["outbound_count"] is None
    assert masked["window"]["inbound_count"] == 5  # 已统计方向保留真实计数
    assert "direction_note" in masked

    plain = {"direction": None, "window": {"outbound_count": 3}, "daily": []}
    assert _mask_uncounted_direction(plain)["window"]["outbound_count"] == 3
    compare = {
        "direction": "outbound",
        "a_period": {"window": {"inbound_count": 0, "outbound_count": 2}},
        "b_period": {"window": {"inbound_count": 0, "outbound_count": 4}},
    }
    masked_compare = _mask_uncounted_direction(compare)
    assert masked_compare["a_period"]["window"]["inbound_count"] is None
    assert masked_compare["b_period"]["window"]["inbound_count"] is None
