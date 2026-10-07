"""阶段三（issue #41）：三个区域活动智能体工具的离线自动测试。

不连接真实数据库、不调用真实模型、不写入任何数据：
- area_activity.repository 打桩（报位/边界行/覆盖统计）；
- 模型响应用脚本化假 ChatModel（backend/tests/fake_llm.py）驱动 create_agent。

覆盖：
1. 工具返回约定字段（query 回显区域/时间/筛选、summary、有界明细、limits、limitations）；
2. 矩形参数缺失时使用当前区域上下文；显式矩形只替换该次调用、不改变当前区域；
3. 参数错误（无时区时间、start>=end、窗口>7 天、矩形跨度>10°、west>east、只给部分边界）
   返回 error envelope 而不是未捕获异常；
4. analysis_actions：成功调用生成一条、同名多次只留最后一条、失败调用不生成、
   其它类型动作不被覆盖；
5. area_context 请求校验（缺字段/超范围 → 422）与路由透传；
6. 工具与服务层同一参数结果一致（两种入口复用同一 service）。
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import SystemMessage, ToolMessage
from pydantic import ValidationError

from backend.app.schemas_agent import AgentAnalyzeRequest, AgentAnalyzeResponse
from backend.app.services.agent import results
from backend.app.services.agent.area_tools import AGENT_SNAPSHOT_SHIP_LIMIT, AGENT_VISIT_LIMIT
from backend.app.services.agent.business_tools import make_business_tools
from backend.app.services.agent.request_guard import new_state
from backend.app.services.agent.serialization import to_jsonable
from backend.app.services.area_activity import service as area_service
from backend.app.services.area_activity.boundaries import default_bounds
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call

UTC = timezone.utc
START = datetime(2026, 2, 25, 0, 0, tzinfo=UTC)
END = datetime(2026, 2, 26, 0, 0, tzinfo=UTC)
AT = datetime(2026, 2, 25, 12, 0, tzinfo=UTC)
CLOSURE_AT = datetime(2026, 2, 28, 15, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 3, 1, 15, 0, tzinfo=UTC)
NAIVE_AT = "2026-02-25T12:00:00"  # 无时区，必须被拒绝

# 前端面板当前区域与工具显式矩形：两者都能覆盖到 A，但 B/C 只在更宽的显式矩形内。
REQUEST_AREA = {
    "west": 55.9, "south": 25.9, "east": 57.0, "north": 27.0,
    "area_id": "panel_rect_1", "label": "面板当前区域",
}
TOOL_AREA = {"west": 55.0, "south": 25.0, "east": 57.5, "north": 27.5}

FINAL_ANSWER = "已按当前区域回显结果：出现去重船数不代表交通量，明细之外还有未列出的条目。"


def _stats(**overrides) -> dict:
    payload = {
        "scoped_fix_count": 10, "region_fix_count": 4, "window_region_fix_count": 2,
        "first_fix_at": START, "last_fix_at": END,
    }
    payload.update(overrides)
    return payload


def _snapshot_row(ship_id: int, latitude: float, longitude: float, **overrides) -> dict:
    row = {
        "ship_id": ship_id, "name": f"SHIP {ship_id}", "mmsi": f"100000{ship_id:03d}",
        "ship_type": "油轮", "flag": "PA", "fix_id": 1000 + ship_id,
        "latitude": latitude, "longitude": longitude, "speed": 8.0,
        "recorded_at": AT - timedelta(minutes=10), "source_batch_id": 1,
    }
    row.update(overrides)
    return row


# A 在默认/请求/显式三个矩形内；B 只在显式矩形内（纬度更低）；C 只在显式矩形内（经度更东）
SNAPSHOT_ROWS = [
    _snapshot_row(1, 26.5, 56.5),
    _snapshot_row(2, 25.5, 56.5),
    _snapshot_row(3, 26.5, 57.25),
]


def _visit_row(ship_id: int = 1, base: datetime = START, **overrides) -> dict:
    row = {
        "ship_id": ship_id, "ship_name": f"SHIP {ship_id}", "mmsi": f"10000000{ship_id}",
        "ship_type": "油轮", "fix_id": 100 + ship_id, "recorded_at": base,
        "latitude": 26.5, "longitude": 56.5, "speed": 8.0,
        "seg_no": 0, "ship_fix_seq": 1, "is_seg_start": True, "is_seg_end": True,
        "start_break_kind": None,
        "prev_inside": False, "prev_at": base - timedelta(minutes=10),
        "prev_fix_id": 50 + ship_id, "prev_lat": 25.0, "prev_lon": 55.0,
        "between_first_fix_id": None, "between_first_at": None,
        "between_last_fix_id": None, "between_last_at": None,
        "next_inside": False, "next_at": base + timedelta(minutes=5),
        "next_fix_id": 200 + ship_id, "next_lat": 25.0, "next_lon": 55.0,
        **_stats(),
    }
    row.update(overrides)
    return row


def _segment_rows(ship_id: int, start: datetime, minutes: int = 30) -> list[dict]:
    """一条完整的区域内段（起止各一条报位）：用于让船时不为 0。"""
    end = start + timedelta(minutes=minutes)
    return [
        _visit_row(ship_id, start, fix_id=1000 + ship_id, ship_fix_seq=1,
                   is_seg_start=True, is_seg_end=False),
        _visit_row(ship_id, end, fix_id=2000 + ship_id, ship_fix_seq=2,
                   latitude=26.6, longitude=56.6,
                   is_seg_start=False, is_seg_end=True,
                   next_at=end + timedelta(minutes=5)),
    ]


@pytest.fixture
def stub(monkeypatch):
    """把区域服务仓储层替换为可编程打桩（与 test_area_activity_service.py 同口径）。"""
    state = {"rows": [], "stats": _stats(), "coverage": [], "snapshot_rows": []}
    monkeypatch.setattr(area_service.repository, "apply_session_settings", lambda *a, **k: None)
    monkeypatch.setattr(area_service.repository, "fetch_latest_fixes",
                        lambda *a, **k: list(state["snapshot_rows"]))
    monkeypatch.setattr(area_service.repository, "fetch_activity_boundaries",
                        lambda *a, **k: list(state["rows"]))
    monkeypatch.setattr(area_service.repository, "fetch_scope_stats", lambda *a, **k: dict(state["stats"]))
    monkeypatch.setattr(area_service.repository, "fetch_batch_coverage",
                        lambda *a, **k: list(state["coverage"]))
    return state


def _tools(area_context=None, db=None, state=None):
    state = state if state is not None else new_state(8, 60.0)
    built = make_business_tools(db, CLOSURE_AT, WINDOW_END, False, state, area_context=area_context)
    return {tool.name: tool for tool in built}, state


def _invoke(name, args, area_context=None, db=None, state=None):
    tools, state = _tools(area_context=area_context, db=db, state=state)
    return json.loads(tools[name].invoke(args)), tools, state


def _run(script, area_context=None, db=None, question="这个区域现在情况如何？"):
    return results_to_outcome(script, area_context=area_context, db=db, question=question)


def results_to_outcome(script, area_context=None, db=None, question="这个区域现在情况如何？"):
    from backend.app.services.agent.langchain_runner import run_lc_agent

    return run_lc_agent(
        db, question, llm=ScriptedFakeLLM(script=script), area_context=area_context,
    )


# ------------------------------------------------------------------ 1. 区域解析
def test_snapshot_uses_default_area_when_no_context(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS

    envelope, _, _ = _invoke("query_area_ship_snapshot", {"at": AT.isoformat()})

    assert envelope["status"] == "ok"
    assert envelope["mode"] == "snapshot"
    assert envelope["area"]["area_id"] == "hormuz_core_v1"
    assert envelope["area"]["version"] == "1.0.0"
    assert envelope["area"]["is_default"] is True
    assert envelope["area"]["source"] == "default"
    assert envelope["query"]["area_id"] == "hormuz_core_v1"
    assert envelope["query"]["area_version"] == "1.0.0"
    assert envelope["query"]["area_is_default"] is True
    assert envelope["query"]["at"] == AT.isoformat()
    assert envelope["query"]["filters"]["ship_types"] is None
    # 默认区域只覆盖 A；B/C 在默认矩形外
    assert [ship["ship_id"] for ship in envelope["ships"]] == [1]
    assert envelope["summary"]["out_of_area_fresh_count"] == 2


def test_snapshot_uses_current_request_area(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS

    envelope, _, _ = _invoke("query_area_ship_snapshot", {"at": AT.isoformat()},
                             area_context=REQUEST_AREA)

    assert envelope["query"]["area_id"] == "panel_rect_1"
    assert envelope["query"]["area_is_default"] is False
    assert envelope["area"]["source"] == "request"
    assert envelope["area"]["label"] == "面板当前区域"
    assert [ship["ship_id"] for ship in envelope["ships"]] == [1]


def test_explicit_rect_replaces_area_only_for_that_call(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS
    tools, _ = _tools(area_context=REQUEST_AREA)
    snapshot = tools["query_area_ship_snapshot"]

    explicit = json.loads(snapshot.invoke({"at": AT.isoformat(), **TOOL_AREA}))
    assert explicit["query"]["area_id"] == "custom"
    assert explicit["area"]["source"] == "custom"
    assert explicit["area"]["is_default"] is False
    assert [ship["ship_id"] for ship in explicit["ships"]] == [1, 2, 3]

    # 显式矩形只作用于该次调用：同一请求内下一次调用仍使用当前区域
    again = json.loads(snapshot.invoke({"at": AT.isoformat()}))
    assert again["query"]["area_id"] == "panel_rect_1"
    assert [ship["ship_id"] for ship in again["ships"]] == [1]


def test_snapshot_list_is_bounded_and_reports_remainder(stub):
    stub["snapshot_rows"] = [_snapshot_row(index, 26.5, 56.5) for index in range(1, 61)]

    envelope, _, _ = _invoke("query_area_ship_snapshot", {"at": AT.isoformat()})

    assert envelope["status"] == "ok"
    assert len(envelope["ships"]) == AGENT_SNAPSHOT_SHIP_LIMIT
    assert envelope["limits"]["list_truncated"] is True
    assert envelope["limits"]["agent_ship_limit"] == AGENT_SNAPSHOT_SHIP_LIMIT
    assert envelope["limits"]["unlisted_ship_count"] == 60 - AGENT_SNAPSHOT_SHIP_LIMIT
    assert envelope["summary"]["in_area_count"] == 60
    assert envelope["summary"]["unlisted_ship_count"] == 10
    assert any("未列出" in item for item in envelope["limitations"])


def test_snapshot_no_data_is_not_zero_ships(stub):
    stub["snapshot_rows"] = []

    envelope, _, _ = _invoke("query_area_ship_snapshot", {"at": AT.isoformat()})

    assert envelope["status"] == "no_data"
    assert envelope["ships"] == []
    assert any("不等于该区域没有船" in item for item in envelope["limitations"])


def test_activity_returns_summary_daily_and_bounded_visits(stub):
    rows: list[dict] = []
    for index, ship_id in enumerate(range(1, 41)):
        rows.extend(_segment_rows(ship_id, START + timedelta(minutes=index)))
    stub["rows"] = rows

    envelope, _, _ = _invoke("query_area_ship_activity", {
        "start_at": START.isoformat(), "end_at": END.isoformat(),
    }, area_context=REQUEST_AREA)

    assert envelope["mode"] == "activity"
    assert envelope["query"]["area_id"] == "panel_rect_1"
    assert envelope["query"]["start_at"] == START.isoformat()
    assert envelope["query"]["end_at"] == END.isoformat()
    assert envelope["query"]["window"]["days"] == 1
    assert envelope["summary"]["ships_observed"] == 40
    assert envelope["summary"]["observed_entry_count"] == 40
    assert envelope["summary"]["observed_exit_count"] == 40
    assert envelope["summary"]["observed_ship_hours"] == 20.0  # 40 艘 × 0.5 小时
    assert envelope["summary"]["visit_count"] == 40
    assert len(envelope["daily"]) == 1
    assert envelope["daily"][0]["date"] == "2026-02-25"
    # 明细截断但汇总不截断
    assert len(envelope["visits"]) == AGENT_VISIT_LIMIT
    assert envelope["limits"]["detail_truncated"] is True
    assert envelope["limits"]["visits_not_shown"] == 40 - AGENT_VISIT_LIMIT
    assert envelope["status"] == "partial"
    assert any(f"工具明细最多列出 {AGENT_VISIT_LIMIT} 条访问" in item
               for item in envelope["limitations"])
    assert any("还有 10 条未列出" in item for item in envelope["limitations"])


def test_activity_no_data_distinguishes_missing_and_zero(stub):
    stub["rows"] = []
    stub["stats"] = _stats(scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
                           first_fix_at=None, last_fix_at=None)

    envelope, _, _ = _invoke("query_area_ship_activity", {
        "start_at": START.isoformat(), "end_at": END.isoformat(),
    })

    assert envelope["status"] == "no_data"
    assert envelope["summary"]["ships_observed"] == 0
    assert any("没有任何 nnu_ais 报位" in item for item in envelope["limitations"])


def test_compare_returns_metrics_delta_and_change_rate(stub):
    # A 期 2 艘、B 期 1 艘：delta=-1、change_rate=-0.5
    stub["rows"] = (
        _segment_rows(1, START + timedelta(minutes=10))
        + _segment_rows(2, START + timedelta(minutes=20))
        + _segment_rows(3, START + timedelta(days=1, minutes=10))
    )

    envelope, _, _ = _invoke("compare_area_ship_activity", {
        "start_a": START.isoformat(), "end_a": END.isoformat(),
        "start_b": (START + timedelta(days=1)).isoformat(),
        "end_b": (START + timedelta(days=2)).isoformat(),
    })

    assert envelope["mode"] == "compare"
    assert envelope["status"] == "ok"
    assert envelope["query"]["start_a"] == START.isoformat()
    metrics = {item["key"]: item for item in envelope["metrics"]}
    assert metrics["ships_observed"]["a"] == 2
    assert metrics["ships_observed"]["b"] == 1
    assert metrics["ships_observed"]["delta"] == -1.0
    assert metrics["ships_observed"]["change_rate"] == -0.5
    assert envelope["summary"]["a"]["ships_observed"] == 2
    assert envelope["summary"]["b"]["ships_observed"] == 1
    assert envelope["summary"]["delta"]["ships_observed"] == -1.0
    assert envelope["summary"]["change_rate"]["ships_observed"] == -0.5
    assert envelope["query"]["comparability"]["equal_length"] is True
    assert envelope["query"]["comparability"]["warnings"] == []
    assert envelope["limits"]["detail_returned"] is False


def test_compare_change_rate_null_is_preserved(stub):
    stub["rows"] = []
    stub["stats"] = _stats(scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
                           first_fix_at=None, last_fix_at=None)

    envelope, _, _ = _invoke("compare_area_ship_activity", {
        "start_a": START.isoformat(), "end_a": END.isoformat(),
        "start_b": (START + timedelta(days=1)).isoformat(),
        "end_b": (START + timedelta(days=2)).isoformat(),
    })

    assert envelope["status"] == "no_data"
    metrics = {item["key"]: item for item in envelope["metrics"]}
    assert metrics["ships_observed"]["change_rate"] is None
    assert envelope["summary"]["change_rate"]["ships_observed"] is None
    assert any("change_rate=null" in item for item in envelope["limitations"])
    assert any("不可比" in item for item in envelope["query"]["comparability"]["warnings"])


# -------------------------------------------------------------- 2. 参数错误降级
@pytest.mark.parametrize("tool_name,args,expected", [
    ("query_area_ship_snapshot", {"at": NAIVE_AT}, "时区"),
    ("query_area_ship_snapshot", {"at": AT.isoformat(), "west": 56.0}, "同时给出或同时省略"),
    ("query_area_ship_snapshot", {"at": AT.isoformat(), "west": -5.0, "south": 25.0,
                                  "east": 6.0, "north": 27.0}, "跨度"),
    ("query_area_ship_snapshot", {"at": AT.isoformat(), "west": 57.0, "south": 25.0,
                                  "east": 56.0, "north": 27.0}, "west < east"),
    ("query_area_ship_snapshot", {"at": AT.isoformat(), "south": 27.0, "west": 55.9,
                                  "east": 57.0, "north": 25.9}, "south < north"),
    ("query_area_ship_activity", {"start_at": START.isoformat(),
                                  "end_at": START.isoformat()}, "start < end"),
    ("query_area_ship_activity", {"start_at": START.isoformat(),
                                  "end_at": (START + timedelta(days=8)).isoformat()}, "最长 7 天"),
    ("query_area_ship_activity", {"start_at": NAIVE_AT, "end_at": END.isoformat()}, "时区"),
    ("compare_area_ship_activity",
     {"start_a": START.isoformat(), "end_a": END.isoformat(),
      "start_b": START.isoformat(), "end_b": (START + timedelta(days=9)).isoformat()}, "B 窗口"),
    ("query_area_ship_activity", {"start_at": START.isoformat(), "end_at": END.isoformat(),
                                  "batch_ids": [0]}, "正整数"),
])
def test_invalid_arguments_return_error_envelope(stub, tool_name, args, expected):
    """参数/上限错误必须是 error envelope（模型可纠正），不能抛未捕获异常。"""
    envelope, _, state = _invoke(tool_name, args)

    assert envelope["status"] == "error"
    assert envelope["code"] == "INVALID_TOOL_ARGS"
    assert expected in envelope["message"]
    assert envelope["tool_name"] == tool_name
    assert state["results"][envelope["call_id"]]["status"] == "error"
    # 失败的调用不生成分析动作
    assert results._area_analysis_actions(state["results"]) == []


def test_snapshot_missing_at_is_rejected_by_schema(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS
    llm = ScriptedFakeLLM(script=[
        tool_call("query_area_ship_snapshot", {}),
        tool_call("query_area_ship_snapshot", {"at": AT.isoformat()}),
        FINAL_ANSWER,
    ])

    from backend.app.services.agent.langchain_runner import run_lc_agent

    outcome = run_lc_agent(None, "现在区域内有哪些船？", llm=llm)

    assert outcome["status"] == "ok"
    # 只有补齐 at 的那次调用进入 envelope（schema 校验拒绝的调用不消耗预算）
    assert list(outcome["results"]) == ["call_001"]
    correction = [m for m in llm.received[1] if isinstance(m, ToolMessage)]
    assert correction and "at" in correction[0].content


# ------------------------------------------------------------ 3. analysis_actions
def test_analysis_action_generated_for_successful_tool(stub):
    stub["rows"] = (
        _segment_rows(1, START + timedelta(minutes=10))
        + _segment_rows(2, START + timedelta(hours=1))
    )

    outcome = _run([
        tool_call("query_area_ship_activity",
                  {"start_at": START.isoformat(), "end_at": END.isoformat()}),
        FINAL_ANSWER,
    ], area_context=REQUEST_AREA)

    actions = outcome["analysis_actions"]
    assert len(actions) == 1
    action = actions[0]
    assert action == {
        "type": "area_activity",
        "trigger": "suggested",
        "mode": "activity",
        "query": {
            # 实际生效边界（此处为请求区域）与归一化后的 area_id
            "west": 55.9, "south": 25.9, "east": 57.0, "north": 27.0,
            "area_id": "custom", "area_version": None, "area_is_default": False,
            "ship_types": None, "batch_ids": None,
            "start_at": START.isoformat(), "end_at": END.isoformat(),
        },
        "summary": {
            "status": "ok",
            "ships_observed": 2,
            "observed_entry_count": 2,
            "observed_exit_count": 2,
            "observed_ship_hours": 1.0,
            "visit_count": 2,
            "window_days": 1,
            "window_length_hours": 24.0,
            "visits_not_shown": 0,
            "detail_truncated": False,
        },
        "tool": "query_area_ship_activity",
        "call_id": "call_001",
    }
    # 面板区域标识仍可在工具结果里核对（动作 query 只保留归一化 area_id）
    assert outcome["results"]["call_001"]["area"]["area_id"] == "panel_rect_1"


def test_analysis_action_keeps_last_call_for_same_tool(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS

    outcome = _run([
        tool_call("query_area_ship_snapshot", {"at": AT.isoformat()}, call_id="call_1"),
        tool_call("query_area_ship_snapshot", {"at": AT.isoformat(), **TOOL_AREA}, call_id="call_2"),
        FINAL_ANSWER,
    ], area_context=REQUEST_AREA)

    assert list(outcome["results"]) == ["call_001", "call_002"]
    actions = outcome["analysis_actions"]
    assert len(actions) == 1
    assert actions[0]["call_id"] == "call_002"
    assert actions[0]["mode"] == "snapshot"
    assert actions[0]["query"]["west"] == TOOL_AREA["west"]
    assert actions[0]["query"]["area_id"] == "custom"
    assert actions[0]["summary"]["in_area_count"] == 3
    assert actions[0]["summary"]["listed_ship_count"] == 3


def test_failed_tool_call_generates_no_action(stub):
    outcome = _run([
        tool_call("query_area_ship_activity",
                  {"start_at": NAIVE_AT, "end_at": END.isoformat()}),
        FINAL_ANSWER,
    ])

    assert outcome["results"]["call_001"]["status"] == "error"
    assert outcome["analysis_actions"] == []


def test_no_area_tool_means_empty_actions(stub):
    outcome = _run(["你好！我可以查询区域活动、船舶通行与轨迹。"], question="你好")

    assert outcome["tools_used"] == []
    assert outcome["analysis_actions"] == []

    empty = results.build_result([], {}, CLOSURE_AT, WINDOW_END, "用户输入", "无工具回答")
    assert empty["analysis_actions"] == []


def test_other_analysis_action_types_are_preserved(stub, monkeypatch):
    """#40 的通行动作与区域动作共存：build_result 只追加，不覆盖/重排其它类型。

    本工作树没有 passage_analysis 实现，用包装 _area_analysis_actions 的方式模拟
    同轮已存在其它类型动作，锁定「列表追加」契约。
    """
    stub["snapshot_rows"] = SNAPSHOT_ROWS
    real = results._area_analysis_actions
    passage = {"type": "passage_analysis", "trigger": "suggested", "mode": "passage",
               "query": {}, "summary": {}, "tool": "query_strait_passages", "call_id": "call_000"}

    def _with_passage(envelopes):
        return [passage] + real(envelopes)

    monkeypatch.setattr(results, "_area_analysis_actions", _with_passage)

    outcome = _run([
        tool_call("query_area_ship_snapshot", {"at": AT.isoformat()}),
        FINAL_ANSWER,
    ])

    assert [item["type"] for item in outcome["analysis_actions"]] == [
        "passage_analysis", "area_activity",
    ]


def test_analysis_action_survives_response_model(stub):
    stub["rows"] = [_visit_row(1)]

    outcome = _run([
        tool_call("query_area_ship_activity",
                  {"start_at": START.isoformat(), "end_at": END.isoformat()}),
        FINAL_ANSWER,
    ])
    payload = to_jsonable(outcome)
    payload["request_id"] = "req-area-test"

    response = AgentAnalyzeResponse(**payload)

    assert len(response.analysis_actions) == 1
    action = response.analysis_actions[0]
    assert action.type == "area_activity"
    assert action.mode == "activity"
    assert action.tool == "query_area_ship_activity"
    assert action.query["start_at"] == START.isoformat()


# ------------------------------------------------- 4. area_context 校验与透传
def test_request_schema_requires_all_bounds_and_range():
    request = AgentAnalyzeRequest(question="区域内有哪些船？")
    assert request.area_context is None  # 向后兼容：不传即默认区域

    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(question="区域内有哪些船？", area_context={
            "west": 56.0, "south": 26.0, "east": 57.0,
        })
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(question="区域内有哪些船？", area_context={
            "west": -181.0, "south": 26.0, "east": 57.0, "north": 27.0,
        })
    with pytest.raises(ValidationError):
        AgentAnalyzeRequest(question="区域内有哪些船？", area_context={
            "west": 56.0, "south": -91.0, "east": 57.0, "north": 27.0,
        })


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_http_invalid_area_context_returns_422(monkeypatch):
    client = _client()

    missing = client.post("/agent/analyze", json={
        "question": "区域内有哪些船？",
        "area_context": {"west": 56.0, "south": 26.0, "east": 57.0},
    })
    assert missing.status_code == 422

    out_of_range = client.post("/agent/analyze", json={
        "question": "区域内有哪些船？",
        "area_context": {"west": 56.0, "south": 26.0, "east": 181.0, "north": 27.0},
    })
    assert out_of_range.status_code == 422


def test_router_forwards_area_context(monkeypatch):
    from backend.app.routers import agent as agent_router
    from backend.app.services.agent.model_client import AgentConfigError

    seen = {}

    def fake_run(db, **kwargs):
        seen.update(kwargs)
        raise AgentConfigError("测试提前结束：不调用真实模型")

    monkeypatch.setattr(agent_router, "run_lc_agent", fake_run)

    response = _client().post("/agent/analyze", json={
        "question": "当前区域内有哪些船？",
        "area_context": REQUEST_AREA,
    })

    assert response.status_code == 503
    assert seen["area_context"] == REQUEST_AREA


def test_system_prompt_contains_current_area(stub):
    llm = ScriptedFakeLLM(script=["已了解当前区域。"])
    results_to_outcome(["已了解当前区域。"], area_context=REQUEST_AREA, question="这个区域是什么范围？")

    from backend.app.services.agent.langchain_runner import run_lc_agent

    run_lc_agent(None, "这个区域是什么范围？", llm=llm, area_context=REQUEST_AREA)
    system = next(m for m in llm.received[0] if isinstance(m, SystemMessage))
    assert "当前请求区域" in system.content
    assert "panel_rect_1" in system.content
    assert "55.9" in system.content and "27.0" in system.content
    # 默认区域仍然是提示词里的固定基准（名称/版本/边界）
    assert "hormuz_core_v1" in system.content
    assert "不是官方航道" in system.content

    default_llm = ScriptedFakeLLM(script=["已了解默认区域。"])
    run_lc_agent(None, "默认区域是哪里？", llm=default_llm)
    default_system = next(m for m in default_llm.received[0] if isinstance(m, SystemMessage))
    assert "请求未提供自定义矩形" in default_system.content


# --------------------------------------------- 5. 两种入口同参数结果一致
def test_snapshot_tool_matches_direct_service_call(stub):
    stub["snapshot_rows"] = SNAPSHOT_ROWS

    envelope, _, _ = _invoke("query_area_ship_snapshot",
                             {"at": AT.isoformat(), "ship_type": ["油轮"]})
    direct = area_service.query_snapshot(
        None, at=AT, bounds=default_bounds(), is_default=True,
        ship_type_values=["油轮"], limit=AGENT_SNAPSHOT_SHIP_LIMIT,
    )

    assert envelope["status"] == direct["status"]
    assert to_jsonable(direct["ships"]) == envelope["ships"]
    assert to_jsonable(direct["summary"]) == {
        key: envelope["summary"][key] for key in direct["summary"]
    }
    assert envelope["query"]["filters"]["ship_types"] == ["油轮"]


def test_activity_tool_matches_direct_service_call(stub):
    stub["rows"] = [_visit_row(1), _visit_row(2, START + timedelta(hours=1))]

    envelope, _, _ = _invoke("query_area_ship_activity", {
        "start_at": START.isoformat(), "end_at": END.isoformat(), "batch_ids": [4],
    })
    direct = area_service.query_activity(
        None, start=START, end=END, bounds=default_bounds(), is_default=True,
        batch_ids=[4], visit_limit=AGENT_VISIT_LIMIT,
    )

    assert envelope["status"] == direct["status"]
    assert to_jsonable(direct["summary"]) == envelope["summary"]
    assert to_jsonable(direct["visits"]) == envelope["visits"]
    assert to_jsonable(direct["daily"]) == envelope["daily"]
    assert envelope["query"]["filters"]["batch_ids"] == [4]
