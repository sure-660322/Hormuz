"""AG-03：query_ship_dwell 智能体工具的离线自动测试。

不连接真实数据库、不调用真实模型（结构同 test_agent_data_health.py）：
- repository 层用 monkeypatch 打桩（dwell manifest / dwell 行 / 源最大时间）；
- 模型响应用脚本化假客户端模拟 Tool Calling（含一次非法参数纠正场景）。

覆盖（对应 AG-03 验收边界）：
1. 正常结果（kind + 带时区窗口 + 全字段 + 阈值/构建参数快照）；
2. 空结果 = 派生层内无该类型停留的有效零结果；
3. 派生层未构建（status=not_built，不报成零段）；
4. 非法参数（kind 不在枚举内）触发纠正循环后成功；
5. 截断（匹配数超过 limit：truncated=True、计数保留）；
6. 模型可选择并调用该工具；
7. 工具结果进入最终响应且符合 schemas_agent 契约；
8. 全流程无任何数据库写入。
"""
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.repositories import dwell as dwell_repo
from backend.app.schemas_agent import AgentAnalyzeResponse
from backend.app.services.agent import runner
from backend.app.services.agent.runner import TOOL_REGISTRY, TOOL_SCHEMAS, run_agent

UTC = timezone.utc

MANIFEST_ROW = {
    "row_count": 12,
    "built_at": datetime(2026, 9, 20, 12, 5, 0, tzinfo=UTC),
    "params": {"anchor_max_kn": 3.0, "drift_max_kn": 5.0, "min_duration_min": 30},
}


def _dwell_row(ship_id, dwell_no, kind, enter, leave, duration_min):
    return {
        "ship_id": ship_id,
        "dwell_no": dwell_no,
        "kind": kind,
        "enter_at": enter,
        "leave_at": leave,
        "duration_min": duration_min,
        "displacement_radius_m": 120.5,
        "max_speed_kn": 1.2,
        "point_count": 40,
        "data_source": "simulation",
        "geometry": '{"type":"Point","coordinates":[56.35,26.55]}',
        "ship_name": f"SIM V2 油轮 {ship_id:03d}",
        "mmsi": f"999900{ship_id:03d}",
        "ship_type": "Tanker",
    }


ANCHOR_ROW = _dwell_row(
    4, 1, "at_anchor",
    datetime(2026, 3, 1, 2, 0, 0, tzinfo=UTC),
    datetime(2026, 3, 1, 3, 40, 0, tzinfo=UTC),
    100.0,
)
DRIFT_ROW = _dwell_row(
    9, 2, "drift",
    datetime(2026, 3, 2, 8, 0, 0, tzinfo=UTC),
    datetime(2026, 3, 2, 9, 30, 0, tzinfo=UTC),
    90.0,
)
SOURCE_MAX = datetime(2026, 3, 4, 23, 59, 14, tzinfo=UTC)

FINAL_ANSWER = (
    "模拟批次中 SIM V2 油轮 004 在 2026-03-01T02:00Z 至 03:40Z 有一段锚泊，"
    "时长 100 分钟；阈值以构建参数快照为准。"
)


# ---- 脚本化假模型客户端 ----
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


def _dwell_script(arguments="{}", final_answer=FINAL_ANSWER):
    return [
        _FakeMessage(tool_calls=[_FakeToolCall("call_dwell_1", "query_ship_dwell", arguments)]),
        _FakeMessage(content=final_answer),
    ]


@pytest.fixture
def patched_repo(monkeypatch):
    """打桩 dwell repository：manifest + 两条停留行（锚泊/漂航各一）+ 源最大时间。"""
    seen = {}

    def _fetch_dwells(db, kind, start, end, limit):
        seen["kind"] = kind
        seen["window"] = (start, end)
        rows = [ANCHOR_ROW, DRIFT_ROW]
        if kind is not None:
            rows = [row for row in rows if row["kind"] == kind]
        return [dict(row) for row in rows[:limit]]

    monkeypatch.setattr(dwell_repo, "fetch_manifest", lambda db: dict(MANIFEST_ROW))
    monkeypatch.setattr(dwell_repo, "fetch_dwells", _fetch_dwells)
    monkeypatch.setattr(dwell_repo, "fetch_source_max_time", lambda db: SOURCE_MAX)
    return seen


def _run_dwell_question(client, db=None, question="这段时间哪些船在锚地抛锚过？"):
    return run_agent(db, client, question=question, trace=[])


# ---------------------------------------------------------------- 1. 正常结果
def test_normal_result(patched_repo):
    args = (
        '{"kind":"at_anchor",'
        '"start_at":"2026-03-01T00:00:00+00:00","end_at":"2026-03-02T00:00:00+00:00"}'
    )
    outcome = _run_dwell_question(_FakeClient(_dwell_script(arguments=args)))

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_ship_dwell"]

    dwell = outcome["results"]["query_ship_dwell"]
    assert dwell["status"] == "ok"
    assert dwell["kind"] == "at_anchor"
    # 带时区窗口原样下推到 repository 层
    assert patched_repo["kind"] == "at_anchor"
    assert patched_repo["window"][0] == datetime(2026, 3, 1, tzinfo=UTC)

    assert dwell["returned_count"] == 1
    assert dwell["matched_count"] == 1
    assert dwell["truncated"] is False
    entry = dwell["dwells"][0]
    assert entry["ship_id"] == 4
    assert entry["kind"] == "at_anchor"
    assert entry["duration_min"] == 100.0
    assert entry["center"] == {"lng": 56.35, "lat": 26.55}
    assert entry["is_simulated"] is True
    # 阈值/构建参数快照保留（锚泊判据 <3 kn / 30 min），stale 为时间启发式
    assert dwell["params"]["anchor_max_kn"] == 3.0
    assert dwell["built_at"] == "2026-09-20T12:05:00+00:00"
    assert dwell["stale"] is False
    assert any("阈值" in item for item in dwell["limitations"])


# ------------------------------------------------------- 2. 空结果是有效零结果
def test_empty_result_is_valid_zero(patched_repo, monkeypatch):
    monkeypatch.setattr(dwell_repo, "fetch_dwells", lambda db, kind, start, end, limit: [])

    outcome = _run_dwell_question(_FakeClient(_dwell_script(arguments='{"kind":"drift"}')))
    dwell = outcome["results"]["query_ship_dwell"]

    assert dwell["status"] == "no_data"
    assert dwell["dwells"] == []
    assert dwell["returned_count"] == 0
    # 零段是「派生层内无该类型停留」的有效零结果，不等于派生层未构建
    assert dwell["built_at"] is not None


# ------------------------------------------------------------ 3. 派生层未构建
def test_not_built(patched_repo, monkeypatch):
    monkeypatch.setattr(dwell_repo, "fetch_manifest", lambda db: None)

    outcome = _run_dwell_question(_FakeClient(_dwell_script()))
    dwell = outcome["results"]["query_ship_dwell"]

    assert dwell["status"] == "not_built"
    assert dwell["dwells"] == []
    assert dwell["returned_count"] == 0
    assert dwell["matched_count"] == 0
    assert dwell["built_at"] is None
    assert dwell["params"] is None


# ---------------------------------------------------------------- 4. 非法参数
def test_invalid_kind_triggers_correction(patched_repo):
    script = [
        _FakeMessage(
            tool_calls=[_FakeToolCall("call_dwell_1", "query_ship_dwell", '{"kind":"anchored"}')]
        ),
        _FakeMessage(
            tool_calls=[_FakeToolCall("call_dwell_2", "query_ship_dwell", '{"kind":"at_anchor"}')]
        ),
        _FakeMessage(content=FINAL_ANSWER),
    ]
    client = _FakeClient(script)
    trace = []
    outcome = run_agent(None, client, question="哪些船抛锚过？", trace=trace)

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_ship_dwell"]
    # 第一次调用被纠正：模型收到非法 kind 的错误消息（Tool Calling 消息流里
    # 第二次 create 的 messages 含 role=tool 的纠正内容）
    second_call_messages = client.chat.completions.calls[1]["messages"]
    correction = [
        m for m in second_call_messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert correction and "at_anchor/drift/slow_transit" in correction[0]["content"]


# ------------------------------------------------------------------ 5. 截断
def test_truncation_keeps_matched_count(patched_repo, monkeypatch):
    many = [
        _dwell_row(4, index + 1, "at_anchor",
                   datetime(2026, 3, 1, 0, index, 0, tzinfo=UTC),
                   datetime(2026, 3, 1, 0, index, 30, tzinfo=UTC),
                   30.0)
        for index in range(60)
    ]
    monkeypatch.setattr(dwell_repo, "fetch_dwells", lambda db, kind, start, end, limit: many)

    outcome = _run_dwell_question(_FakeClient(_dwell_script(arguments='{"limit":10}')))
    dwell = outcome["results"]["query_ship_dwell"]

    assert dwell["returned_count"] == 10
    assert dwell["matched_count"] == 60
    assert dwell["truncated"] is True
    assert len(dwell["dwells"]) == 10


# ------------------------------------------------------------ 6. 模型选择工具
def test_model_can_select_query_ship_dwell(patched_repo):
    assert "query_ship_dwell" in TOOL_REGISTRY
    tool = TOOL_REGISTRY["query_ship_dwell"]
    assert tool.windowed is False
    assert any(schema["function"]["name"] == "query_ship_dwell" for schema in TOOL_SCHEMAS)

    client = _FakeClient(_dwell_script())
    trace = []
    outcome = run_agent(None, client, question="哪些船在锚地抛锚过？", trace=trace)

    assert all(
        any(t["function"]["name"] == "query_ship_dwell" for t in call["tools"])
        for call in client.chat.completions.calls
    )
    assert trace == [{"tool": "query_ship_dwell", "arguments": "{}"}]
    assert outcome["tools_used"] == ["query_ship_dwell"]


# ------------------------------------------------- 7. 工具结果进入最终响应
def test_tool_result_reaches_final_response(patched_repo):
    outcome = _run_dwell_question(_FakeClient(_dwell_script()))

    assert outcome["answer"] == FINAL_ANSWER
    dwell = outcome["results"]["query_ship_dwell"]
    # datetime 经 _jsonable 序列化为 ISO 字符串
    assert dwell["dwells"][0]["enter_at"] == "2026-03-01T02:00:00+00:00"

    payload = runner._jsonable(outcome)
    payload["request_id"] = "req-ag03-test"
    response = AgentAnalyzeResponse(**payload)
    assert response.tools_used == ["query_ship_dwell"]
    assert any("阈值" in item for item in response.limitations)
    assert any("不代表真实锚地" in item for item in response.limitations)


# ------------------------------------------------- 8. 全流程没有数据库写入
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        rows = self._rows

        class _Mapping:
            def __iter__(self):
                return iter(rows)

            def all(self):
                return list(rows)

            def one(self):
                assert len(rows) == 1
                return rows[0]

            def one_or_none(self):
                return rows[0] if rows else None

        return _Mapping()

    def scalar(self):
        if not self._rows:
            return None
        row = self._rows[0]
        if isinstance(row, dict):
            return next(iter(row.values()))
        return row


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
        raise AssertionError("query_ship_dwell 全流程不得触发任何数据库写入")

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
            "FROM ship_dwell d": [ANCHOR_ROW],
            "FROM track_build_manifest": [MANIFEST_ROW],
            "max(recorded_at) FROM ship_positions": [{"max": SOURCE_MAX}],
        }
    )

    outcome = _run_dwell_question(_FakeClient(_dwell_script()), db=session)

    assert outcome["status"] == "ok"
    assert len(session.executed_sql) == 3  # 三条只读 SELECT
    for sql in session.executed_sql:
        assert sql.lstrip().lower().startswith("select"), sql
        assert not _WRITE_RE.search(sql), sql

    dwell = outcome["results"]["query_ship_dwell"]
    assert dwell["returned_count"] == 1
    assert dwell["matched_count"] == 1
