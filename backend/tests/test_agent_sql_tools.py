"""LC-03：受限 SQL 工具（get_database_schema / check_sql / execute_sql）离线测试。

不连接真实数据库、不调用真实模型：
- check_sql / get_database_schema 走真实 SQLGlot 策略（纯校验，不触库）；
- execute_sql 通过 EXECUTOR_FACTORY 接缝注入假执行器；
- 覆盖 schema 返回、普通 SELECT 校验通过、写 SQL 被底座拒绝、
  拒绝后 execute_sql 关闭、功能开关关闭时不暴露工具。
"""
import pytest

from backend.app.services.agent import sql_tools
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.app.services.agent.query_analytics_executor import QueryAnalyticsResult
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call as _tool_call

VALID_SQL = (
    "SELECT ship_id, name, ship_type FROM agent_data.v_ships "
    "WHERE ship_type = :ship_type ORDER BY ship_id"
)
VALID_PARAMS = [{"name": "ship_type", "type": "text", "value": "Tanker"}]


def test_old_simulation_sql_catalog_hidden_for_real_ais():
    assert sql_tools.sql_tools_enabled() is False


class _FakeExecutor:
    """记录入参并返回固定结果的假执行器。"""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []
        self.disposed = False

    def execute(self, *, sql, params, purpose, request_id, call_id, cancel_event=None):
        self.calls.append(
            {"sql": sql, "params": params, "purpose": purpose,
             "request_id": request_id, "call_id": call_id}
        )
        if self.error is not None:
            raise self.error
        return self.result

    def dispose(self):
        self.disposed = True


def _fake_result():
    return QueryAnalyticsResult(
        query_id="aq_test_001",
        status="ok",
        columns=("ship_type", "ship_count"),
        rows=(("Tanker", 12), ("Chemical", 9)),
        returned_row_count=2,
        truncated=False,
        source={"catalog_version": "1.0"},
        limitations=("固定夹具结果，仅用于测试",),
    )


@pytest.fixture
def fake_executor(monkeypatch):
    executor = _FakeExecutor(result=_fake_result())
    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", lambda: executor)
    return executor


# ------------------------------------------------------------ schema 工具
def test_schema_tool_returns_catalog_views():
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_database_schema", {}),
        "catalog 提供 v_ships、v_events、v_news 三个语义视图，批准 JOIN 只有 "
        "v_news.event_id = v_events.event_id。",
    ])
    outcome = run_lc_agent(None, "数据库里有哪些可查询的视图？", llm=llm, sql_enabled=True)
    assert outcome["tools_used"] == ["get_database_schema"]
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "ok"
    names = {view["name"] for view in envelope["views"]}
    assert names == {"agent_data.v_ships", "agent_data.v_events", "agent_data.v_news"}
    ships = next(v for v in envelope["views"] if v["name"] == "agent_data.v_ships")
    assert any(column["name"] == "ship_type" for column in ships["columns"])
    assert envelope["allowed_joins"]


# ------------------------------------------------------------ check_sql
def test_check_sql_accepts_valid_select():
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_database_schema", {}),
        _tool_call("check_sql", {"sql": VALID_SQL, "params": VALID_PARAMS,
                                 "purpose": "按船型统计模拟船"}),
        "校验通过，SQL 合法。",
    ])
    outcome = run_lc_agent(None, "按船型统计有多少艘船", llm=llm, sql_enabled=True)
    envelope = outcome["results"]["call_002"]
    assert envelope["tool_name"] == "check_sql"
    assert envelope["status"] == "ok"
    assert "agent_data.v_ships" in envelope["referenced_views"]


def test_check_sql_refuses_write():
    llm = ScriptedFakeLLM(script=[
        _tool_call("check_sql", {"sql": "DELETE FROM agent_data.v_ships",
                                 "purpose": "尝试删除"}),
        "该 SQL 被只读策略拒绝：智能体只允许受限 SELECT，不能执行任何写入。",
    ])
    outcome = run_lc_agent(None, "删除数据库里的船", llm=llm, sql_enabled=True)
    envelope = outcome["results"]["call_001"]
    assert envelope["tool_name"] == "check_sql"
    assert envelope["status"] == "refused"
    assert envelope["code"] == "refused"
    assert "拒绝" in outcome["answer"]


def test_check_sql_flags_literal_and_suggests_params():
    llm = ScriptedFakeLLM(script=[
        _tool_call("check_sql", {
            "sql": "SELECT * FROM agent_data.v_ships WHERE ship_type = 'Tanker'",
            "purpose": "按船型筛选",
        }),
        "字符串字面量不被允许，条件值必须使用 :name 绑定参数。",
    ])
    outcome = run_lc_agent(None, "查 Tanker 船", llm=llm, sql_enabled=True)
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "refused"
    assert "绑定参数" in envelope["message"]


# ------------------------------------------------------------ execute_sql
def test_execute_sql_returns_rows_via_executor(fake_executor):
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_database_schema", {}),
        _tool_call("check_sql", {"sql": VALID_SQL, "params": VALID_PARAMS,
                                 "purpose": "按船型统计"}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS,
                                   "purpose": "按船型统计"}),
        "按船型统计：Tanker 12 艘、Chemical 9 艘（固定夹具）。",
    ])
    outcome = run_lc_agent(None, "按船型统计有多少艘船", llm=llm, sql_enabled=True)
    assert outcome["tools_used"] == [
        "get_database_schema", "check_sql", "execute_sql",
    ]
    envelope = outcome["results"]["call_003"]
    assert envelope["status"] == "ok"
    assert envelope["query_id"] == "aq_test_001"
    assert envelope["columns"] == ["ship_type", "ship_count"]
    assert envelope["rows"] == [["Tanker", 12], ["Chemical", 9]]
    assert envelope["returned_row_count"] == 2
    assert fake_executor.disposed
    assert fake_executor.calls[0]["request_id"]


def test_execute_sql_refusal_closes_further_sql(fake_executor):
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError

    fake_executor.error = QueryExecutionError(
        status="refused", code="AGENT_QUERY_POLICY",
        public_message="查询被安全策略拒绝", http_status=200,
        query_id="aq_refused", retryable=False, query_executed=False,
    )
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": "DROP TABLE agent_data.v_ships",
                                   "purpose": "尝试删表"}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS,
                                   "purpose": "换写法重试"}),
        "查询被只读策略拒绝，且重试已被终止；我只能说明无法完成该请求。",
    ])
    outcome = run_lc_agent(None, "帮我删掉船表再统计船数", llm=llm, sql_enabled=True)
    first = outcome["results"]["call_001"]
    second = outcome["results"]["call_002"]
    assert first["status"] == "refused"
    assert second["code"] == "SQL_CLOSED"
    # 拒绝后重试被底座拦截：假执行器只在第一次被调用
    assert len(fake_executor.calls) == 1


def test_execute_sql_success_closes_further_sql(fake_executor):
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        "已得到首次查询结果。",
    ])
    outcome = run_lc_agent(None, "查船型", llm=llm, sql_enabled=True)
    assert outcome["results"]["call_001"]["status"] == "ok"
    assert outcome["results"]["call_002"]["code"] == "SQL_CLOSED"
    assert len(fake_executor.calls) == 1


@pytest.mark.parametrize("status,code", [
    ("refused", "AGENT_QUERY_REFUSED"),
    ("timeout", "AGENT_QUERY_TIMEOUT"),
    ("permission_failed", "AGENT_QUERY_UNAVAILABLE"),
    ("source_unavailable", "AGENT_QUERY_UNAVAILABLE"),
])
def test_sql_terminal_errors_never_retry(fake_executor, status, code):
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError
    fake_executor.error = QueryExecutionError(
        status=status, code=code, public_message="查询不可用", http_status=200,
        retryable=False, query_executed=status == "timeout",
    )
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": VALID_SQL}),
        _tool_call("execute_sql", {"sql": VALID_SQL}),
        "查询失败。",
    ])
    outcome = run_lc_agent(None, "查船型", llm=llm, sql_enabled=True)
    assert outcome["results"]["call_001"]["status"] == status
    assert outcome["results"]["call_002"]["code"] == "SQL_CLOSED"
    assert len(fake_executor.calls) == 1


def test_first_unexecuted_syntax_error_has_one_correction(monkeypatch):
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError

    class SyntaxThenSuccess(_FakeExecutor):
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise QueryExecutionError(
                    status="syntax_error", code="AGENT_QUERY_SYNTAX",
                    public_message="语法错误", http_status=200,
                    retryable=True, query_executed=False,
                )
            return _fake_result()

    executor = SyntaxThenSuccess()
    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", lambda: executor)
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": "SELECT BAD"}),
        _tool_call("execute_sql", {"sql": VALID_SQL}),
        _tool_call("execute_sql", {"sql": VALID_SQL}),
        "已得到结果。",
    ])
    outcome = run_lc_agent(None, "查船型", llm=llm, sql_enabled=True)
    assert [v["status"] for v in outcome["results"].values()] == [
        "syntax_error", "ok", "error",
    ]
    assert outcome["results"]["call_003"]["code"] == "SQL_CLOSED"
    assert len(executor.calls) == 2


def test_second_unexecuted_syntax_error_closes_branch(monkeypatch):
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError

    class SyntaxExecutor(_FakeExecutor):
        def execute(self, **kwargs):
            self.calls.append(kwargs)
            raise QueryExecutionError(
                status="syntax_error", code="AGENT_QUERY_SYNTAX",
                public_message="语法错误", http_status=200,
                retryable=True, query_executed=False,
            )

    executor = SyntaxExecutor()
    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", lambda: executor)
    llm = ScriptedFakeLLM(script=[
        _tool_call("execute_sql", {"sql": "SELECT BAD"}),
        _tool_call("execute_sql", {"sql": "SELECT BAD AGAIN"}),
        _tool_call("execute_sql", {"sql": VALID_SQL}),
        "语法无法修复。",
    ])
    outcome = run_lc_agent(None, "查船型", llm=llm, sql_enabled=True)
    assert outcome["results"]["call_003"]["code"] == "SQL_CLOSED"
    assert len(executor.calls) == 2


def test_sql_tools_share_eight_call_budget(fake_executor):
    llm = ScriptedFakeLLM(script=[
        *[_tool_call("get_database_schema", {}) for _ in range(6)],
        _tool_call("check_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        "查询完成。",
    ])
    outcome = run_lc_agent(None, "查船型", llm=llm, sql_enabled=True)
    assert outcome["results"]["call_008"]["status"] == "ok"
    assert outcome["results"]["call_009"]["code"] == "TOOL_BUDGET_EXCEEDED"
    assert outcome["status"] == "partial"
    assert len(fake_executor.calls) == 1
    assert llm._calls == 9


def test_sql_budget_shared_with_knowledge_and_business(fake_executor, monkeypatch):
    from backend.app.services.agent import business_tools

    business_calls = []
    monkeypatch.setattr(business_tools.health_service, "get_data_health",
                        lambda db: business_calls.append(1) or {"source": {}})
    llm = ScriptedFakeLLM(script=[
        *[_tool_call("search_project_knowledge", {"query": "模拟船"}) for _ in range(4)],
        _tool_call("get_data_health", {}),
        _tool_call("get_database_schema", {}),
        _tool_call("check_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "params": VALID_PARAMS}),
        _tool_call("get_data_health", {}),
        "完成。",
    ])
    outcome = run_lc_agent(None, "查数据", llm=llm, sql_enabled=True)
    assert outcome["results"]["call_009"]["code"] == "TOOL_BUDGET_EXCEEDED"
    assert outcome["status"] == "partial"
    assert len(business_calls) == 1
    assert len(fake_executor.calls) == 1
    assert llm._calls == 9


# ------------------------------------------------------------ 功能开关
def test_sql_tools_hidden_when_disabled():
    seen_tools = []

    class _Recorder(ScriptedFakeLLM):
        def bind_tools(self, tools, **kwargs):
            seen_tools.extend(tool.name for tool in tools)
            return self

    llm = _Recorder(script=["我没有受限 SQL 工具可用。"])
    outcome = run_lc_agent(None, "按船型统计", llm=llm, sql_enabled=False)
    assert outcome["status"] == "ok"
    for hidden in ("get_database_schema", "check_sql", "execute_sql"):
        assert hidden not in seen_tools
    assert "search_project_knowledge" in seen_tools
    assert "query_strait_passages" in seen_tools


def test_sql_tools_exposed_when_enabled():
    seen_tools = []

    class _Recorder(ScriptedFakeLLM):
        def bind_tools(self, tools, **kwargs):
            seen_tools.extend(tool.name for tool in tools)
            return self

    llm = _Recorder(script=["好的。"])
    run_lc_agent(None, "按船型统计", llm=llm, sql_enabled=True)
    for name in ("get_database_schema", "check_sql", "execute_sql"):
        assert name in seen_tools


# ------------------------------------------------------------ 写意图走底座拒绝（前置分类已移除）
def test_write_intent_answered_via_policy_refusal():
    """LC-03 移除固定短语分类后：「删除数据库」由模型调用 check_sql 并被策略拒绝。"""
    llm = ScriptedFakeLLM(script=[
        _tool_call("check_sql", {"sql": "DELETE FROM agent_data.v_ships",
                                 "purpose": "用户要求删除"}),
        "这个请求涉及写库，被只读策略拒绝；智能体只允许受限 SELECT 查询。",
    ])
    outcome = run_lc_agent(None, "删除数据库", llm=llm, sql_enabled=True)
    assert outcome["tools_used"] == ["check_sql"]
    assert outcome["results"]["call_001"]["status"] == "refused"
    assert "拒绝" in outcome["answer"]
