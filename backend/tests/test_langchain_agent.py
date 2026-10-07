"""LC-01：LangChain create_agent 智能体的离线自动测试。

不连接真实数据库、不调用真实模型：
- 模型用脚本化假 ChatModel（ScriptedFakeLLM）模拟「工具调用 → 最终回答」；
- repository 层按场景打桩；
- 覆盖 LC-01 验收：自然问候、范围外问题、模型不可用、Decimal 工具结果不再 500、
  工具错误降级、超时与历史消息。
"""
import time
import os
import subprocess
import sys
from pathlib import Path
from threading import Event
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.exc import SQLAlchemyError

from backend.app.repositories import data_health as health_repo
from backend.app.services.agent import langchain_runner
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.app.services.agent.results import AgentTimeoutError
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call as _tool_call

UTC = timezone.utc


# ---- get_data_health 打桩（结构样例数值，不代表当前批次真实数量） ----
SOURCE_ROWS_DECIMAL = [
    {
        "data_source": "simulation",
        "position_count": 9354,
        "ship_count": 30,
        "coverage_start": datetime(2026, 2, 26, 2, 43, 10, tzinfo=UTC),
        "coverage_end": datetime(2026, 3, 4, 23, 59, 14, tzinfo=UTC),
        "median_gap_minutes": Decimal("17.0"),  # ::numeric，Decimal 500 的原始来源
    }
]
GLOBAL_ROWS = [{"ships": 30, "events": 64, "news": 247, "positions": 9354}]
MANIFEST_ROWS = [
    {
        "table_name": "ship_tracks",
        "row_count": 30,
        "built_at": datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC),
        "params": {"tolerance_seconds": 300},
    }
]


@pytest.fixture
def patched_health_repo(monkeypatch):
    monkeypatch.setattr(
        health_repo, "fetch_source_counts",
        lambda db: [dict(r) for r in SOURCE_ROWS_DECIMAL],
    )
    monkeypatch.setattr(
        health_repo, "fetch_global_counts", lambda db: dict(GLOBAL_ROWS[0])
    )
    monkeypatch.setattr(
        health_repo, "fetch_derived_manifests", lambda db: [dict(r) for r in MANIFEST_ROWS]
    )


# ------------------------------------------------------------ 问候与范围外
def test_greeting_answered_without_tools():
    llm = ScriptedFakeLLM(script=["你好！我是霍尔木兹海峡海事态势分析智能体，"
                                  "可以查询模拟船舶通行、轨迹、停留、相遇和新闻事件。"])
    outcome = run_lc_agent(None, "你好", llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert outcome["results"] == {}
    assert "智能体" in outcome["answer"]


def test_out_of_scope_question_answered_without_tools():
    llm = ScriptedFakeLLM(script=["我主要负责霍尔木兹海峡海事态势的只读查询，"
                                  "没有天气工具，无法可靠查询天气。"])
    outcome = run_lc_agent(None, "今天天气怎么样", llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert "天气" in outcome["answer"]


# ------------------------------------------------------------ 模型不可用
def test_model_unavailable_raises_config_error(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from backend.app.services.agent.model_client import AgentConfigError

    with pytest.raises(AgentConfigError):
        run_lc_agent(None, "你好")


# ------------------------------------------------------------ Decimal 不再 500
def test_decimal_tool_result_serializes(patched_health_repo):
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}),
        "数据健康：当前模拟批次共 30 艘船、9354 条报位，中位报位间隔 17 分钟。",
    ])
    outcome = run_lc_agent(None, "现在数据健康吗？", llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["get_data_health"]
    envelope = outcome["results"]["call_001"]
    assert envelope["tool_name"] == "get_data_health"
    sources = envelope["source"]["by_data_source"]
    assert sources[0]["median_gap_minutes"] == 17  # Decimal 已转 int，可 JSON 序列化
    import json

    from backend.app.services.agent.serialization import to_jsonable

    # 契约路径：响应先经统一序列化再 json.dumps（LC-01 前 Decimal 在此抛 TypeError → 500）
    json.dumps(to_jsonable(outcome), ensure_ascii=False)


# ------------------------------------------------------------ 工具错误降级
def test_tool_database_error_degrades_to_observation(patched_health_repo, monkeypatch):
    def _boom(db):
        raise SQLAlchemyError("connection lost (测试桩)")

    monkeypatch.setattr(health_repo, "fetch_source_counts", _boom)
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}),
        "数据库暂时不可用，数据健康查询失败，请稍后重试。",
    ])
    outcome = run_lc_agent(None, "现在数据健康吗？", llm=llm)
    assert outcome["status"] in {"no_data", "partial", "ok"}
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "error"
    assert envelope["code"] == "DATABASE_UNAVAILABLE"
    assert "不可用" in outcome["answer"]


def test_tool_invalid_args_degrade_to_observation():
    llm = ScriptedFakeLLM(script=[
        _tool_call("search_ships", {"keyword": ""}),
        "检索关键字不能为空，请提供船名、MMSI、IMO、船型或船旗关键字。",
    ])
    outcome = run_lc_agent(None, "帮我找船", llm=llm)
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "error"
    assert envelope["code"] == "INVALID_TOOL_ARGS"


# ------------------------------------------------------------ 多轮 history
def test_history_turns_are_passed_to_model():
    llm = ScriptedFakeLLM(script=["好的，它是 SIM V2 化学品船 019。"])
    outcome = run_lc_agent(
        None,
        "它是什么船型？",
        history=[
            {"role": "user", "content": "刚才那艘通过海峡的船叫什么？"},
            {"role": "assistant", "content": "是 SIM V2 化学品船 019。"},
        ],
        llm=llm,
    )
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []


# ------------------------------------------------------------ 超时
def test_overall_budget_timeout():
    llm = ScriptedFakeLLM(script=["不会走到这里"], sleep_seconds=2.0)
    with pytest.raises(AgentTimeoutError):
        run_lc_agent(None, "你好", llm=llm, budget_seconds=0.2)


def test_late_model_tools_cannot_touch_executor_or_repository(monkeypatch):
    from backend.app.services.agent import sql_tools, business_tools

    counts = {"sql": 0, "business": 0}

    class Executor:
        def execute(self, **kwargs):
            counts["sql"] += 1
            raise AssertionError("SQL must not start")

        def dispose(self):
            pass

    def business(db):
        counts["business"] += 1
        raise AssertionError("repository must not start")

    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", Executor)
    monkeypatch.setattr(business_tools.health_service, "get_data_health", business)
    llm = ScriptedFakeLLM(script=[
        AIMessage(content="", tool_calls=[
            {"name": "execute_sql", "args": {"sql": "SELECT ship_id FROM agent_data.v_ships"}, "id": "sql"},
            {"name": "get_data_health", "args": {}, "id": "business"},
        ]),
        "超时",
    ], sleep_seconds=0.12)
    with pytest.raises(AgentTimeoutError):
        run_lc_agent(None, "查数据", llm=llm, sql_enabled=True, budget_seconds=0.02)
    assert counts == {"sql": 0, "business": 0}
    time.sleep(0.05)
    assert counts == {"sql": 0, "business": 0}


def test_timeout_waits_for_inflight_tool_before_session_release(monkeypatch):
    from backend.app.services.agent import business_tools, sql_tools

    entered = Event()
    finished = Event()
    session = object()
    counts = {"business": 0, "sql": 0}

    def slow_business(db):
        assert db is session
        counts["business"] += 1
        entered.set()
        time.sleep(0.45)
        finished.set()
        return {"source": {}, "limitations": []}

    class Executor:
        def execute(self, **kwargs):
            counts["sql"] += 1
            raise AssertionError("SQL after deadline")

        def dispose(self):
            pass

    monkeypatch.setattr(business_tools.health_service, "get_data_health", slow_business)
    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", Executor)
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}),
        _tool_call("execute_sql", {"sql": "SELECT ship_id FROM agent_data.v_ships"}),
        "完成",
    ])
    with pytest.raises(AgentTimeoutError):
        run_lc_agent(session, "查数据", llm=llm, sql_enabled=True, budget_seconds=0.20)
    assert entered.is_set() and finished.is_set()
    assert counts == {"business": 1, "sql": 0}
    time.sleep(0.05)
    assert counts == {"business": 1, "sql": 0}


def test_timeout_cancels_inflight_sql_before_return(monkeypatch):
    from backend.app.services.agent import sql_tools
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError

    events = {"entered": Event(), "finished": Event()}

    class Executor:
        def execute(self, *, cancel_event, **kwargs):
            events["entered"].set()
            assert cancel_event.wait(1.0)
            events["finished"].set()
            raise QueryExecutionError(
                status="timeout", code="AGENT_QUERY_TIMEOUT",
                public_message="查询超时", http_status=504, query_executed=True,
            )

        def dispose(self):
            pass

    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", Executor)
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": "SELECT ship_id FROM agent_data.v_ships"}),
        "超时",
    ])
    with pytest.raises(AgentTimeoutError):
        run_lc_agent(None, "查船", llm=llm, sql_enabled=True, budget_seconds=0.20)
    assert events["entered"].is_set() and events["finished"].is_set()


def test_deepseek_script_skips_without_key():
    root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env.pop("DEEPSEEK_API_KEY", None)
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "test_deepseek_toolcall.py")],
        cwd=root, env=env, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.startswith("SKIP:")
    assert "ImportError" not in completed.stderr


def test_http_timeout_releases_session_only_after_worker_stops(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router
    from backend.app.services.agent import business_tools

    class SessionMarker:
        closed = False

    marker = SessionMarker()
    counts = {"before_close": 0, "after_close": 0}

    def dependency():
        try:
            yield marker
        finally:
            marker.closed = True

    def repository(db):
        time.sleep(0.40)
        key = "after_close" if db.closed else "before_close"
        counts[key] += 1
        return {"source": {}, "limitations": []}

    monkeypatch.setattr(business_tools.health_service, "get_data_health", repository)
    monkeypatch.setattr(langchain_runner, "build_llm", lambda: ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}), "完成",
    ]))
    # The default argument is bound at import time; route calls the wrapper below.
    original = langchain_runner.run_lc_agent
    monkeypatch.setattr(agent_router, "run_lc_agent",
                        lambda *args, **kwargs: original(*args, **kwargs, budget_seconds=0.20))
    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = dependency
    response = TestClient(app).post("/agent/analyze", json={"question": "查数据"})
    assert response.status_code == 504
    assert response.json()["detail"]["code"] == "AGENT_TIMEOUT"
    assert marker.closed
    assert counts["before_close"] == 1
    assert counts["after_close"] == 0
    stable = counts.copy()
    time.sleep(0.05)
    assert counts == stable


# ------------------------------------------------------------ 前置分类已移除（LC-03）
def test_vague_question_gets_natural_clarification():
    """「查一下」不再被固定短语拦截：模型自然追问，状态为 ok。"""
    llm = ScriptedFakeLLM(script=[
        "请说明要查询的对象、指标或时间范围，例如事件类型统计、船舶筛选或新闻数量。"
    ])
    outcome = run_lc_agent(None, "查一下", llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert "请说明" in outcome["answer"]


def test_business_tools_do_not_include_sql_tools():
    """10 个业务工具与 SQL 工具分模块：业务工具集不含任何 SQL/分析工具。"""
    from backend.app.services.agent.business_tools import make_business_tools

    state = {"tools_used": [], "results": {}, "tool_executions": 0,
             "call_sequence": 0, "max_tool_executions": 8}
    from datetime import datetime, timezone

    tools = make_business_tools(
        None, datetime(2026, 2, 28, 15, tzinfo=timezone.utc),
        datetime(2026, 3, 1, 15, tzinfo=timezone.utc), False, state,
    )
    names = {tool.name for tool in tools}
    assert names == {
        "query_strait_passages", "search_ships", "get_ship_track",
        "get_event_context", "get_data_health", "query_ship_dwell",
        "query_encounters", "query_event_ship_links",
        "query_strait_passage_statistics", "compare_strait_passage_statistics",
    }
    assert "query_analytics" not in names
    assert "execute_sql" not in names


# ------------------------------------------------------------ HTTP 路由层
def _test_app(monkeypatch, llm):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    monkeypatch.setattr(
        langchain_runner, "build_llm", lambda: llm
    )
    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_http_greeting_round_trip(monkeypatch):
    llm = ScriptedFakeLLM(script=["你好！我可以查询模拟船舶通行、轨迹、停留、相遇和新闻事件。"])
    client = _test_app(monkeypatch, llm)
    response = client.post("/agent/analyze", json={"question": "你好"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["tools_used"] == []
    assert body["schema_version"] == "4"
    assert body["request_id"]


def test_http_model_unavailable_503(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)

    response = client.post("/agent/analyze", json={"question": "你好"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "AGENT_UNAVAILABLE"


def test_http_decimal_no_longer_500(monkeypatch, patched_health_repo):
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}),
        "数据健康：30 艘船、9354 条报位，中位间隔 17 分钟。",
    ])
    client = _test_app(monkeypatch, llm)
    response = client.post("/agent/analyze", json={"question": "现在数据健康吗？"})
    assert response.status_code == 200  # LC-01 前此处为 500
    body = response.json()
    assert body["results"]["call_001"]["source"]["by_data_source"][0]["median_gap_minutes"] == 17
