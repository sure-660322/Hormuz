"""LC-04 多表达矩阵测试：同一意图的多种自然表述驱动同一工具路径。

背景：docs/langchain_agent_v1_plan.md §7——v4 的固定问句前置分类已删除，
问候、范围外、知识、SQL 统计、业务技能、澄清全部交给模型 + 工具底座。
本文件替换旧 test_query_analytics_sql06.py 的固定问句矩阵。

脚本化假模型（ScriptedFakeLLM）的固有局限：它按脚本输出工具调用，
无法验证真实模型的选择准确率（需真实 DeepSeek，见 docs 未验证项）；
本矩阵验证的是「模型一旦做出正确工具选择，每种表述的端到端契约行为一致」。
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app.repositories import data_health as health_repo
from backend.app.services.agent import sql_tools
from backend.app.services.agent.langchain_runner import run_lc_agent
from backend.app.services.agent.query_analytics_executor import QueryAnalyticsResult
from backend.tests.fake_llm import ScriptedFakeLLM, tool_call as _tool_call

UTC = timezone.utc

GREETING_ANSWER = "你好！我是霍尔木兹海峡海事态势分析智能体，可以查询模拟船舶通行、轨迹、停留、相遇和新闻事件。"
OUT_OF_SCOPE_ANSWER = "我主要负责霍尔木兹海峡海事态势的只读查询，没有天气工具，无法可靠查询天气。"
CLARIFY_ANSWER = "请说明「那艘船」指的是哪一艘：可以提供船名、MMSI 或 IMO，我先用 search_ships 检索确认。"


# ------------------------------------------------------------ 问候（多表述）
@pytest.mark.parametrize("question", ["你好", "在吗", "嗨", "早上好，帮我看看数据"])
def test_greeting_expressions_need_no_tools(question):
    llm = ScriptedFakeLLM(script=[GREETING_ANSWER])
    outcome = run_lc_agent(None, question, llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert outcome["results"] == {}
    assert "智能体" in outcome["answer"]


# ------------------------------------------------------------ 范围外（多表述）
@pytest.mark.parametrize("question", ["今天天气怎么样", "你会写诗吗", "给我讲个笑话"])
def test_out_of_scope_expressions_need_no_tools(question):
    llm = ScriptedFakeLLM(script=[OUT_OF_SCOPE_ANSWER])
    outcome = run_lc_agent(None, question, llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert "天气" in outcome["answer"]


# ------------------------------------------------------------ 知识类（多表述 → search_project_knowledge）
@pytest.mark.parametrize("question", [
    "船是真实 AIS 吗",
    "这些船的数据是真的吗",
    "模拟船和新闻里的船是一回事吗",
    "相遇代表真实接触吗",
])
def test_knowledge_expressions_use_knowledge_tool(question):
    llm = ScriptedFakeLLM(script=[
        _tool_call("search_project_knowledge", {"query": question}),
        "船舶与船位是教学模拟数据，不是真实 AIS；events/news 是真实报道聚合，"
        "两个数据集相互独立，不得按船名认定为同一实体。",
    ])
    outcome = run_lc_agent(None, question, llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["search_project_knowledge"]
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "ok"
    assert envelope["count"] >= 1
    assert envelope["matches"]


# ------------------------------------------------------------ SQL 统计（多表述 → schema/check/execute 链）
VALID_SQL = (
    "SELECT ship_type, COUNT(*) AS ship_count FROM agent_data.v_ships "
    "GROUP BY ship_type ORDER BY ship_count DESC"
)


class _FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.disposed = False

    def execute(self, *, sql, params, purpose, request_id, call_id, cancel_event=None):
        self.calls.append({"sql": sql, "params": params, "purpose": purpose})
        return self.result

    def dispose(self):
        self.disposed = True


def _count_result():
    return QueryAnalyticsResult(
        query_id="aq_expr_001",
        status="ok",
        columns=("ship_type", "ship_count"),
        rows=(("Tanker", 12),),
        returned_row_count=1,
        truncated=False,
        source={"catalog_version": "1.0"},
        limitations=("固定夹具结果，仅用于测试",),
    )


@pytest.fixture
def fake_executor(monkeypatch):
    executor = _FakeExecutor(result=_count_result())
    monkeypatch.setattr(sql_tools, "EXECUTOR_FACTORY", lambda: executor)
    return executor


@pytest.mark.parametrize("question", [
    "一共几艘船？",
    "库里现在有多少条新闻？",
    "哪种事件类型最多？",
    "按船型统计一下数量",
])
def test_sql_stat_expressions_run_full_chain(question, fake_executor):
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_database_schema", {}),
        _tool_call("check_sql", {"sql": VALID_SQL, "purpose": question}),
        _tool_call("execute_sql", {"sql": VALID_SQL, "purpose": question}),
        "统计结果：Tanker 12 艘（固定夹具）。",
    ])
    outcome = run_lc_agent(None, question, llm=llm, sql_enabled=True)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["get_database_schema", "check_sql", "execute_sql"]
    envelope = outcome["results"]["call_003"]
    assert envelope["tool_name"] == "execute_sql"
    assert envelope["status"] == "ok"
    assert envelope["rows"] == [["Tanker", 12]]
    assert fake_executor.disposed


# ------------------------------------------------------------ 业务技能（多表述 → query_strait_passages）
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        rows = self._rows

        class _Mapping:
            def all(self):
                return list(rows)

        return _Mapping()


class _PassageSession:
    """承载 query_strait_passages 真实算法的只读假会话：一艘船西向东穿越。"""

    def __init__(self, rows):
        self._rows = rows
        self.executed = []

    def scalar(self, clause):
        self.executed.append(str(clause))
        return len(self._rows)

    def execute(self, clause, *args, **kwargs):
        sql = str(clause)
        self.executed.append(sql)
        assert sql.lstrip().lower().startswith("select")
        return _FakeResult(self._rows)

    def _write_attempt(self, *_args, **_kwargs):
        raise AssertionError("query_strait_passages 全流程不得触发任何数据库写入")

    commit = _write_attempt
    flush = _write_attempt
    add = _write_attempt
    delete = _write_attempt
    merge = _write_attempt
    bulk_save_objects = _write_attempt


# 西侧报位（窗口前，确定初始侧）→ 东侧报位（默认窗口内，观测完成）
PASSAGE_ROWS = [
    {"ship_id": 4, "name": "SIM V2 油轮 004", "longitude": 56.1, "latitude": 26.5,
     "recorded_at": datetime(2026, 2, 28, 14, 0, 0, tzinfo=UTC)},
    {"ship_id": 4, "name": "SIM V2 油轮 004", "longitude": 56.8, "latitude": 26.5,
     "recorded_at": datetime(2026, 2, 28, 16, 0, 0, tzinfo=UTC)},
]
PASSAGE_ANSWER = (
    "默认封锁窗口内有 1 艘模拟船完成西向东完整通行（SIM V2 油轮 004），"
    "观测完成时刻为 2026-02-28T16:00Z。"
)


@pytest.mark.parametrize("question", [
    "有多少船穿过了海峡？",
    "封锁后哪些船完成了穿越？",
    "这段时间有船从西向东通过霍尔木兹海峡吗？",
])
def test_passage_expressions_use_strait_tool(question):
    session = _PassageSession(PASSAGE_ROWS)
    llm = ScriptedFakeLLM(script=[
        _tool_call("query_strait_passages", {}),
        PASSAGE_ANSWER,
    ])
    outcome = run_lc_agent(session, question, llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_strait_passages"]
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "ok"
    assert envelope["query_summary"]["passage_count"] == 1
    assert envelope["evidence"][0]["direction"] == "west_to_east"
    assert envelope["ships"][0]["name"] == "SIM V2 油轮 004"


# ------------------------------------------------------------ 澄清（多表述 → 追问，不调工具）
@pytest.mark.parametrize("question", ["那艘船呢", "它后来去哪了", "再查查它"])
def test_vague_reference_expressions_ask_clarification(question):
    llm = ScriptedFakeLLM(script=[CLARIFY_ANSWER])
    outcome = run_lc_agent(None, question, llm=llm)
    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == []
    assert "请说明" in outcome["answer"]


# ------------------------------------------------------------ 故障降级（多表述 → DATABASE_UNAVAILABLE envelope）
@pytest.mark.parametrize("question", ["现在数据健康吗", "各来源有多少报位", "数据齐不齐"])
def test_degradation_expressions_honest_observation(question, monkeypatch):
    def _boom(db):
        raise SQLAlchemyError("connection lost (测试桩)")

    monkeypatch.setattr(health_repo, "fetch_source_counts", _boom)
    llm = ScriptedFakeLLM(script=[
        _tool_call("get_data_health", {}),
        "数据库暂时不可用，数据健康查询失败，请稍后重试。",
    ])
    outcome = run_lc_agent(None, question, llm=llm)
    envelope = outcome["results"]["call_001"]
    assert envelope["status"] == "error"
    assert envelope["code"] == "DATABASE_UNAVAILABLE"
    assert "不可用" in outcome["answer"]
