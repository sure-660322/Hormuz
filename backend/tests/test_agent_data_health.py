"""AG-02：get_data_health 智能体工具的离线自动测试。

不连接真实数据库、不调用真实模型：
- repository 层用 monkeypatch 打桩（前三个场景）或记录型假会话承载真实只读 SQL（写操作检查）；
- 模型响应用脚本化假客户端模拟 Tool Calling 两阶段（工具调用 → 最终回答）。

覆盖（对应任务要求的 7 个场景）：
1. 正常结果；2. 来源缺数据；3. 派生层未构建；4. 查询失败（500 DATA_QUERY_FAILED）；
5. 模型可选择并调用该工具；6. 工具结果进入最终响应且符合响应契约；
7. 全流程无任何数据库写入。
"""
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

from backend.app.repositories import data_health as health_repo
from backend.app.schemas_agent import AgentAnalyzeResponse
from backend.app.services.agent import runner
from backend.app.services.agent.runner import TOOL_REGISTRY, TOOL_SCHEMAS, run_agent

UTC = timezone.utc

# ---- 正常结果的 fixture（数值仅为例行结构样例，不代表当前批次真实数量） ----
SOURCE_ROWS = [
    {
        "data_source": "simulation",
        "position_count": 9354,
        "ship_count": 30,
        "coverage_start": datetime(2026, 2, 26, 2, 43, 10, tzinfo=UTC),
        "coverage_end": datetime(2026, 3, 4, 23, 59, 14, tzinfo=UTC),
        "median_gap_minutes": 17.0,
    },
]
GLOBAL_ROWS = [{"ships": 30, "events": 64, "news": 247, "positions": 9354}]
MANIFEST_ROWS = [
    {
        "table_name": "ship_tracks",
        "row_count": 30,
        "built_at": datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC),
        "params": {"tolerance_seconds": 300},
    },
    {
        "table_name": "ship_dwell",
        "row_count": 12,
        "built_at": datetime(2026, 9, 20, 12, 5, 0, tzinfo=UTC),
        "params": {"anchor_max_kn": 3.0},
    },
    {
        "table_name": "encounters",
        "row_count": 4,
        "built_at": datetime(2026, 9, 20, 12, 10, 0, tzinfo=UTC),
        "params": {"max_distance_nm": 3.0},
    },
    {
        "table_name": "event_ship_links",
        "row_count": 8,
        "built_at": datetime(2026, 9, 20, 12, 15, 0, tzinfo=UTC),
        "params": {"radius_km": 50},
    },
]

FINAL_ANSWER = (
    "数据健康：当前模拟批次共 30 艘船、9354 条报位；"
    "ship_tracks 的 stale=false，但 stale 只是时间启发式。"
)


# ---- 脚本化假模型客户端（OpenAI SDK 形状的最小模拟） ----
class _FakeToolCall:
    def __init__(self, call_id, name, arguments="{}"):
        self.id = call_id
        self.function = SimpleNamespace(name=name, arguments=arguments)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeCompletion:
    def __init__(self, message):
        self.choices = [SimpleNamespace(message=message)]


class _FakeCompletions:
    """按脚本顺序返回消息，并记录每次 create 的入参（含 tools schema）。"""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        assert self._script, "模型请求次数超过脚本"
        return _FakeCompletion(self._script.pop(0))


class _FakeClient:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=_FakeCompletions(script))


def _health_script(final_answer=FINAL_ANSWER):
    """两阶段脚本：先调用 get_data_health，再给出最终回答。"""
    return [
        _FakeMessage(tool_calls=[_FakeToolCall("call_health_1", "get_data_health")]),
        _FakeMessage(content=final_answer),
    ]


@pytest.fixture
def patched_repo(monkeypatch):
    """打桩 data_health repository 的三个只读查询，返回正常 fixture。"""
    monkeypatch.setattr(health_repo, "fetch_source_counts", lambda db: [dict(r) for r in SOURCE_ROWS])
    monkeypatch.setattr(health_repo, "fetch_global_counts", lambda db: dict(GLOBAL_ROWS[0]))
    monkeypatch.setattr(
        health_repo, "fetch_derived_manifests", lambda db: [dict(r) for r in MANIFEST_ROWS]
    )
    return None


def _run_health_question(client, db=None, question="现在数据健康吗？各来源有多少报位？"):
    return run_agent(db, client, question=question, trace=[])


# ---------------------------------------------------------------- 1. 正常结果
def test_normal_result(patched_repo):
    outcome = _run_health_question(_FakeClient(_health_script()))

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["get_data_health"]

    health = outcome["results"]["get_data_health"]
    assert health["source"]["by_data_source"][0]["data_source"] == "simulation"
    assert health["source"]["by_data_source"][0]["position_count"] == 9354
    assert health["source"]["totals"]["news"] == 247

    derived = {row["table"]: row for row in health["derived"]}
    assert set(derived) == set(health_repo.DERIVED_TABLES)
    # built_at（2026-09-20）晚于最新源报位（2026-03-04）→ stale=False（时间启发式）
    assert derived["ship_tracks"]["stale"] is False
    assert derived["ship_tracks"]["params"] == {"tolerance_seconds": 300}
    assert all("status" not in row for row in derived.values())


# ------------------------------------------------------------ 2. 来源缺数据
def test_missing_source_is_not_zero(patched_repo, monkeypatch):
    monkeypatch.setattr(health_repo, "fetch_source_counts", lambda db: [])

    outcome = _run_health_question(_FakeClient(_health_script()))
    health = outcome["results"]["get_data_health"]

    # 来源列表为空：只能表示未导入/无记录，不能解释为真实数量为零
    assert health["source"]["by_data_source"] == []
    assert any("不能解释为真实数量为零" in item for item in health["limitations"])
    # 没有来源时间基准，stale 无法判定，必须为 None 而不是 False
    assert all(row["stale"] is None for row in health["derived"])
    assert outcome["status"] == "ok"


# ------------------------------------------------------------ 3. 派生层未构建
def test_derived_not_built(patched_repo, monkeypatch):
    monkeypatch.setattr(health_repo, "fetch_derived_manifests", lambda db: [])

    outcome = _run_health_question(_FakeClient(_health_script()))
    health = outcome["results"]["get_data_health"]
    derived = {row["table"]: row for row in health["derived"]}

    assert set(derived) == set(health_repo.DERIVED_TABLES)
    for row in derived.values():
        assert row["status"] == "not_built"
        assert row["rows"] is None  # 未构建不能报成 0 行
        assert row["built_at"] is None
        assert row["stale"] is None  # 未构建无从谈新旧


# ------------------------------------------------------------ 4. 查询失败
def test_query_failure_maps_to_data_query_failed(patched_repo, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.app.database import get_db
    from backend.app.routers import agent as agent_router

    def _boom(db):
        raise SQLAlchemyError("connection lost (测试桩)")

    monkeypatch.setattr(health_repo, "fetch_source_counts", _boom)
    monkeypatch.setattr(agent_router, "build_client", lambda: _FakeClient(_health_script()))

    app = FastAPI()
    app.include_router(agent_router.router)
    app.dependency_overrides[get_db] = lambda: None  # 查询在打桩层失败，会话不会被使用
    client = TestClient(app)

    response = client.post("/agent/analyze", json={"question": "现在数据健康吗？"})
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "DATA_QUERY_FAILED"
    assert "request_id" in detail


# ------------------------------------------------------------ 5. 模型选择工具
def test_model_can_select_get_data_health(patched_repo):
    assert "get_data_health" in TOOL_REGISTRY
    tool = TOOL_REGISTRY["get_data_health"]
    assert tool.windowed is False
    assert tool.parameters == {"type": "object", "properties": {}}
    assert any(
        schema["function"]["name"] == "get_data_health" for schema in TOOL_SCHEMAS
    )

    client = _FakeClient(_health_script())
    trace = []
    outcome = run_agent(
        None, client, question="现在派生数据是不是最新的？", trace=trace
    )

    # 模型每次都收到包含 get_data_health 的 tools schema，并成功选中执行
    assert all(
        any(t["function"]["name"] == "get_data_health" for t in call["tools"])
        for call in client.chat.completions.calls
    )
    assert trace == [{"tool": "get_data_health", "arguments": "{}"}]
    assert outcome["tools_used"] == ["get_data_health"]


# ------------------------------------------------- 6. 工具结果进入最终响应
def test_tool_result_reaches_final_response(patched_repo):
    outcome = _run_health_question(_FakeClient(_health_script()))

    assert outcome["answer"] == FINAL_ANSWER
    health = outcome["results"]["get_data_health"]
    assert health["status"] == "ok"
    # 工具结果经 _jsonable 序列化：datetime 为 ISO 字符串
    assert health["derived"][0]["built_at"] == "2026-09-20T12:00:00+00:00"

    # 响应整体符合 schemas_agent 契约（顶层字段、context、results 均可序列化校验）
    payload = runner._jsonable(outcome)
    payload["request_id"] = "req-ag02-test"
    response = AgentAnalyzeResponse(**payload)
    assert response.tools_used == ["get_data_health"]
    assert "stale=false 不证明历史数据未被修改" in response.limitations
    assert any("只读" in item for item in response.limitations)


# ------------------------------------------------- 7. 全流程没有数据库写入
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        rows = self._rows

        class _Mapping:
            def __iter__(self):
                return iter(rows)

            def one(self):
                assert len(rows) == 1
                return rows[0]

        return _Mapping()


class _RecordingSession:
    """承载真实 repository SQL、记录全部执行语句的只读假会话。

    任何写/提交方法被调用即测试失败。
    """

    def __init__(self, rows_by_marker):
        self._rows_by_marker = rows_by_marker
        self.executed_sql = []

    def execute(self, clause, *args, **kwargs):
        sql = str(clause)
        self.executed_sql.append(sql)
        for marker, rows in self._rows_by_marker.items():
            if marker in sql:
                return _FakeResult(rows)
        raise AssertionError(f"未识别的 SQL：{sql[:80]}")

    def _write_attempt(self, *_args, **_kwargs):
        raise AssertionError("get_data_health 全流程不得触发任何数据库写入")

    commit = _write_attempt
    flush = _write_attempt
    add = _write_attempt
    delete = _write_attempt
    merge = _write_attempt
    bulk_save_objects = _write_attempt


_WRITE_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|merge)\b", re.IGNORECASE
)


def test_full_flow_performs_no_db_writes():
    session = _RecordingSession(
        {
            "FROM ship_positions p": SOURCE_ROWS,
            "FROM ships) AS ships": GLOBAL_ROWS,
            "FROM track_build_manifest m": MANIFEST_ROWS,
        }
    )

    outcome = _run_health_question(_FakeClient(_health_script()), db=session)

    assert outcome["status"] == "ok"
    assert len(session.executed_sql) == 3  # 三条只读 SELECT
    for sql in session.executed_sql:
        assert sql.lstrip().lower().startswith("select"), sql
        assert not _WRITE_RE.search(sql), sql

    health = outcome["results"]["get_data_health"]
    assert health["source"]["totals"]["positions"] == 9354
    assert {row["table"] for row in health["derived"]} == set(health_repo.DERIVED_TABLES)
