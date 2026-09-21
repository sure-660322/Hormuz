import os
from types import SimpleNamespace

import pytest

from backend.app.schemas_agent import AgentAnalyzeResponse
from backend.app.services.agent import runner
from backend.app.services.agent.query_analytics_executor import (
    QueryAnalyticsResult,
    QueryExecutionError,
)


class _ToolCall:
    def __init__(self, call_id: str, name: str, arguments: str = "{}"):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=arguments)


class _Message:
    def __init__(self, *, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _Completions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.script.pop(0))])


class _Client:
    def __init__(self, script):
        self.completions = _Completions(script)
        self.chat = SimpleNamespace(completions=self.completions)


class _Executor:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.calls = []
        self.disposed = False

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def dispose(self):
        self.disposed = True


@pytest.fixture
def analytics_env(monkeypatch):
    values = {
        "AGENT_QUERY_ENABLED": "true",
        "AGENT_QUERY_BIND_HOST": "127.0.0.1",
        "AGENT_DB_USER": "agent_reader_login",
        "AGENT_DB_PASSWORD": "test-only",
        "AGENT_DB_HOST": "127.0.0.1",
        "AGENT_DB_PORT": "5432",
        "AGENT_DB_NAME": "test",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _success():
    return QueryAnalyticsResult(
        query_id="aq_test_001",
        status="ok",
        columns=("event_type", "event_count"),
        rows=(("incident", 2),),
        returned_row_count=1,
        truncated=False,
        source={
            "catalog_version": "v1",
            "views": ["agent_data.v_events"],
            "data_scope": {"agent_data.v_events": "news events"},
        },
        limitations=("事件数据来自报道聚合",),
    )


def _analytics_args():
    return (
        '{"sql":"SELECT event_type, COUNT(*) AS event_count '
        'FROM agent_data.v_events GROUP BY event_type",'
        '"params":[],"purpose":"统计事件类型"}'
    )


def test_default_flag_hides_query_analytics(monkeypatch):
    monkeypatch.setenv("AGENT_QUERY_ENABLED", "false")
    assert "query_analytics" in runner.TOOL_REGISTRY
    assert "query_analytics" not in runner._active_tool_registry()


def test_enabled_query_analytics_uses_isolated_executor_and_call_id(analytics_env, monkeypatch):
    executor = _Executor([_success()])
    monkeypatch.setattr(runner, "QUERY_ANALYTICS_EXECUTOR_FACTORY", lambda: executor)
    client = _Client([
        _Message(tool_calls=[_ToolCall("provider_unsafe_id", "query_analytics", _analytics_args())]),
        _Message(content="事件类型统计见结构化结果。"),
    ])

    outcome = runner.run_agent(None, client, "按事件类型统计数量", request_id="req_test")

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_analytics"]
    assert list(outcome["results"]) == ["call_001"]
    result = outcome["results"]["call_001"]
    assert result["tool_name"] == "query_analytics"
    assert result["rows"] == [["incident", 2]]
    assert executor.calls[0]["request_id"] == "req_test"
    assert executor.calls[0]["call_id"] == "call_001"
    assert executor.disposed is True
    assert any(item["function"]["name"] == "query_analytics" for item in client.completions.calls[0]["tools"])


def test_syntax_error_allows_one_pre_execution_repair(analytics_env, monkeypatch):
    syntax = QueryExecutionError(
        status="syntax_error",
        code="AGENT_QUERY_SYNTAX",
        public_message="SQL 语法无法解析",
        http_status=200,
        query_id="aq_bad",
        retryable=True,
        query_executed=False,
    )
    executor = _Executor([syntax, _success()])
    monkeypatch.setattr(runner, "QUERY_ANALYTICS_EXECUTOR_FACTORY", lambda: executor)
    client = _Client([
        _Message(tool_calls=[_ToolCall("p1", "query_analytics", _analytics_args())]),
        _Message(tool_calls=[_ToolCall("p2", "query_analytics", _analytics_args())]),
        _Message(content="已完成一次语法修复并返回统计。"),
    ])

    outcome = runner.run_agent(None, client, "按事件类型统计数量", request_id="req_retry")

    assert outcome["status"] == "ok"
    assert list(outcome["results"]) == ["call_001", "call_002"]
    assert outcome["results"]["call_001"]["status"] == "syntax_error"
    assert outcome["results"]["call_002"]["status"] == "ok"
    assert len(executor.calls) == 2


def test_security_refusal_is_terminal_and_never_retried(analytics_env, monkeypatch):
    refused = QueryExecutionError(
        status="refused",
        code="AGENT_QUERY_REFUSED",
        public_message="查询未通过只读安全策略",
        http_status=200,
        query_id="aq_refused",
        query_executed=False,
    )
    executor = _Executor([refused])
    monkeypatch.setattr(runner, "QUERY_ANALYTICS_EXECUTOR_FACTORY", lambda: executor)
    client = _Client([
        _Message(tool_calls=[_ToolCall("p1", "query_analytics", _analytics_args())]),
        _Message(content="不应被请求"),
    ])

    outcome = runner.run_agent(None, client, "尝试越权查询", request_id="req_refused")

    assert outcome["status"] == "refused"
    assert outcome["results"]["call_001"]["code"] == "AGENT_QUERY_REFUSED"
    assert len(client.completions.calls) == 1
    assert len(executor.calls) == 1


def test_timeout_without_other_success_propagates_for_http_mapping(analytics_env, monkeypatch):
    timeout = QueryExecutionError(
        status="timeout",
        code="AGENT_QUERY_TIMEOUT",
        public_message="query_analytics 查询超时",
        http_status=504,
        query_id="aq_timeout",
        query_executed=True,
    )
    executor = _Executor([timeout])
    monkeypatch.setattr(runner, "QUERY_ANALYTICS_EXECUTOR_FACTORY", lambda: executor)
    client = _Client([_Message(tool_calls=[_ToolCall("p1", "query_analytics", _analytics_args())])])

    with pytest.raises(QueryExecutionError, match="查询超时") as caught:
        runner.run_agent(None, client, "复杂统计", request_id="req_timeout")
    assert caught.value.http_status == 504


def test_preflight_clarification_refusal_and_non_data_need_no_model():
    clarification = runner.run_agent(None, None, "查一下")
    assert clarification["status"] == "needs_clarification"
    assert clarification["tools_used"] == []
    assert clarification["results"] == {}
    assert clarification["clarification"]

    refused = runner.run_agent(None, None, "删除数据库")
    assert refused["status"] == "refused"
    assert refused["results"] == {}

    non_data = runner.run_agent(None, None, "这些船位是真实 AIS 吗？")
    assert non_data["status"] == "ok"
    assert non_data["tools_used"] == []
    assert "教学模拟" in non_data["answer"]


def test_response_schema_rejects_unknown_status():
    outcome = runner.run_agent(None, None, "查一下")
    outcome["request_id"] = "req_schema"
    response = AgentAnalyzeResponse(**outcome)
    assert response.schema_version == "4"
    outcome["status"] = "unexpected"
    with pytest.raises(ValueError):
        AgentAnalyzeResponse(**outcome)


def test_status_aggregation_does_not_hide_a_second_tool_failure():
    results = {
        "call_001": {"call_id": "call_001", "tool_name": "query_strait_passages", "status": "ok"},
        "call_002": {"call_id": "call_002", "tool_name": "query_analytics", "status": "timeout"},
    }
    assert runner._normalize_status(["query_strait_passages", "query_analytics"], results) == "partial"


def test_http_preflight_skips_model_configuration(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    monkeypatch.setattr(
        agent_router,
        "build_client",
        lambda: (_ for _ in ()).throw(AssertionError("preflight must not build a model client")),
    )
    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None

    response = TestClient(app).post("/agent/analyze", json={"question": "查一下"})

    assert response.status_code == 200
    assert response.json()["status"] == "needs_clarification"
    assert response.json()["results"] == {}


def test_http_maps_query_timeout_to_stable_error(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    monkeypatch.setattr(agent_router, "build_client", lambda: object())
    monkeypatch.setattr(
        agent_router,
        "run_agent",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            QueryExecutionError(
                status="timeout",
                code="AGENT_QUERY_TIMEOUT",
                public_message="query_analytics 查询超时",
                http_status=504,
                query_id="aq_http_timeout",
                query_executed=True,
            )
        ),
    )
    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None

    response = TestClient(app).post("/agent/analyze", json={"question": "统计新闻数量"})

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["code"] == "AGENT_QUERY_TIMEOUT"
    assert "aq_http_timeout" not in response.text


@pytest.mark.skipif(
    os.getenv("SQL04_TEST_INTEGRATION") != "1",
    reason="use scripts/verify_query_analytics_integration.ps1",
)
def test_real_postgres_runner_tool_round_trip():
    client = _Client([
        _Message(tool_calls=[_ToolCall("provider_call", "query_analytics", _analytics_args())]),
        _Message(content="固定夹具中 shipping 类型事件为 1 条。"),
    ])

    outcome = runner.run_agent(None, client, "按事件类型统计数量", request_id="req_sql05_pg17")

    assert outcome["status"] == "ok"
    result = outcome["results"]["call_001"]
    assert result["columns"] == ["event_type", "event_count"]
    assert result["rows"] == [["shipping", 1]]
    assert result["source"]["catalog_version"] == "1.0"
    assert result["source"]["views"] == ["agent_data.v_events"]
