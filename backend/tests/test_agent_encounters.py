"""AG-04：query_encounters 智能体工具的离线自动测试。

不连接真实数据库、不调用真实模型：
- repository 层用 monkeypatch 打桩（encounters manifest / 行 / 源最大时间）；
- 模型响应用脚本化假客户端模拟 Tool Calling（含阈值超限纠正场景）。

覆盖（对应 AG-04 验收边界）：
1. 正常结果（窗口 + max_distance_nm 过滤 + NM/米双单位 + 构建参数快照）；
2. 省略 max_distance_nm 时默认取构建阈值（查询层不额外缩小覆盖）；
3. 空结果 = 构建阈值内无相遇的有效零结果；
4. 派生层未构建（status=not_built）；
5. 请求阈值超过构建阈值 → 纠正循环（能力不支持，不得返回 0）；
6. 截断（匹配数超过 limit：truncated=True、计数保留）；
7. 模型可选择并调用该工具；
8. 工具结果进入最终响应且符合 schemas_agent 契约；
9. 全流程无任何数据库写入。
"""
import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.repositories import encounters as enc_repo
from backend.app.schemas_agent import AgentAnalyzeResponse
from backend.app.services.agent import runner
from backend.app.services.agent.runner import TOOL_REGISTRY, TOOL_SCHEMAS, run_agent

UTC = timezone.utc

MANIFEST_ROW = {
    "row_count": 4,
    "built_at": datetime(2026, 9, 20, 12, 10, 0, tzinfo=UTC),
    "params": {"distance_nm": 3.0, "overlap_min": 30, "sample_seconds": 60,
               "data_source": "simulation"},
}


def _encounter_row(min_distance_m):
    return {
        "id": 1,
        "ship_a_id": 4,
        "ship_b_id": 9,
        "min_distance_m": min_distance_m,
        "overlap_minutes": 45.0,
        "period_start": datetime(2026, 3, 1, 10, 0, 0, tzinfo=UTC),
        "period_end": datetime(2026, 3, 1, 10, 45, 0, tzinfo=UTC),
        "closest_point": '{"type":"Point","coordinates":[56.40,26.60]}',
        "data_source": "simulation",
        "params": "{}",
        "built_at": datetime(2026, 9, 20, 12, 10, 0, tzinfo=UTC),
        "ship_a_name": "SIM V2 油轮 004",
        "ship_a_mmsi": "999900004",
        "ship_a_type": "Tanker",
        "ship_b_name": "SIM V2 油轮 009",
        "ship_b_mmsi": "999900009",
        "ship_b_type": "Tanker",
    }


ENCOUNTER_ROW = _encounter_row(1852.0)  # 1.0 NM
SOURCE_MAX = datetime(2026, 3, 4, 23, 59, 14, tzinfo=UTC)

FINAL_ANSWER = (
    "相遇派生层内 SIM V2 油轮 004 与 SIM V2 油轮 009 在 2026-03-01 10:00–10:45 UTC "
    "时段内最近相距 1.0 海里（1852 米）；接近不等于实际交互。"
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


def _encounters_script(arguments="{}", final_answer=FINAL_ANSWER):
    return [
        _FakeMessage(tool_calls=[_FakeToolCall("call_enc_1", "query_encounters", arguments)]),
        _FakeMessage(content=final_answer),
    ]


@pytest.fixture
def patched_repo(monkeypatch):
    """打桩 encounters repository，并记录 fetch_encounters 的下推参数。"""
    seen = {}

    def _fetch_encounters(db, start, end, max_distance_m, limit):
        seen["window"] = (start, end)
        seen["max_distance_m"] = max_distance_m
        rows = [ENCOUNTER_ROW]
        if max_distance_m is not None:
            rows = [r for r in rows if r["min_distance_m"] <= max_distance_m]
        return [dict(r) for r in rows[:limit]]

    monkeypatch.setattr(enc_repo, "fetch_manifest", lambda db: dict(MANIFEST_ROW))
    monkeypatch.setattr(enc_repo, "fetch_encounters", _fetch_encounters)
    monkeypatch.setattr(enc_repo, "fetch_source_max_time", lambda db: SOURCE_MAX)
    return seen


def _run_encounters_question(client, db=None, question="这段时间哪些船相遇过？"):
    return run_agent(db, client, question=question, trace=[])


# ---------------------------------------------------------------- 1. 正常结果
def test_normal_result(patched_repo):
    args = (
        '{"start_at":"2026-03-01T00:00:00+00:00","end_at":"2026-03-02T00:00:00+00:00",'
        '"max_distance_nm":2.0}'
    )
    outcome = _run_encounters_question(_FakeClient(_encounters_script(arguments=args)))

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_encounters"]

    enc = outcome["results"]["query_encounters"]
    assert enc["status"] == "ok"
    assert enc["window"] == ["2026-03-01T00:00:00+00:00", "2026-03-02T00:00:00+00:00"]
    assert enc["max_distance_nm_filter"] == 2.0
    assert enc["requested_max_distance_nm"] == 2.0
    # 过滤条件原样下推 repository（2 NM = 3704 米）
    assert patched_repo["max_distance_m"] == 2.0 * 1852.0

    assert enc["returned_count"] == 1
    assert enc["matched_count"] == 1
    assert enc["truncated"] is False
    pair = enc["encounters"][0]
    assert pair["ship_a"]["id"] == 4
    assert pair["ship_b"]["id"] == 9
    # NM 与米双单位保留
    assert pair["min_distance_m"] == 1852.0
    assert pair["min_distance_nm"] == 1.0
    assert pair["closest_point"]["coordinates"] == [56.40, 26.60]
    assert pair["is_simulated"] is True
    # 构建参数快照（默认 3 NM / 30 min / 60 s 采样）与 stale 时间启发式
    assert enc["params"]["distance_nm"] == 3.0
    assert enc["params"]["sample_seconds"] == 60
    assert enc["built_at"] == "2026-09-20T12:10:00+00:00"
    assert enc["stale"] is False
    assert any("只能缩小不能扩大" in item for item in enc["limitations"])
    assert any("离散采样" in item for item in enc["limitations"])


# --------------------------------------- 2. 省略阈值时默认取构建阈值不过滤
def test_default_filter_uses_build_threshold(patched_repo):
    outcome = _run_encounters_question(_FakeClient(_encounters_script()))
    enc = outcome["results"]["query_encounters"]

    assert enc["status"] == "ok"
    assert enc["requested_max_distance_nm"] is None
    assert enc["max_distance_nm_filter"] == 3.0
    assert patched_repo["max_distance_m"] == 3.0 * 1852.0


# ------------------------------------------------------- 3. 空结果是有效零结果
def test_empty_result_is_valid_zero(patched_repo, monkeypatch):
    monkeypatch.setattr(enc_repo, "fetch_encounters", lambda db, s, e, m, limit: [])

    outcome = _run_encounters_question(
        _FakeClient(_encounters_script(arguments='{"max_distance_nm":1.0}'))
    )
    enc = outcome["results"]["query_encounters"]

    assert enc["status"] == "no_data"
    assert enc["encounters"] == []
    assert enc["returned_count"] == 0
    assert enc["built_at"] is not None  # 零对≠未构建


# ------------------------------------------------------------ 4. 派生层未构建
def test_not_built(patched_repo, monkeypatch):
    monkeypatch.setattr(enc_repo, "fetch_manifest", lambda db: None)

    outcome = _run_encounters_question(_FakeClient(_encounters_script()))
    enc = outcome["results"]["query_encounters"]

    assert enc["status"] == "not_built"
    assert "尚未重建" in enc["message"]
    assert enc["encounters"] == []
    assert enc["built_at"] is None
    assert enc["params"] is None


# --------------------------------------- 5. 阈值超过构建阈值 → 纠正而非零结果
def test_threshold_above_build_rejected_with_correction(patched_repo):
    script = [
        _FakeMessage(
            tool_calls=[_FakeToolCall("call_enc_1", "query_encounters", '{"max_distance_nm":5.0}')]
        ),
        _FakeMessage(
            tool_calls=[_FakeToolCall("call_enc_2", "query_encounters", '{"max_distance_nm":1.0}')]
        ),
        _FakeMessage(content=FINAL_ANSWER),
    ]
    client = _FakeClient(script)
    outcome = run_agent(None, client, question="5 海里内有哪些船相遇过？", trace=[])

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_encounters"]
    second_call_messages = client.chat.completions.calls[1]["messages"]
    correction = [
        m for m in second_call_messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert correction and "构建阈值" in correction[0]["content"]
    assert "超过构建阈值" in correction[0]["content"]


# ------------------------------------------------------------------ 6. 截断
def test_truncation_keeps_matched_count(patched_repo, monkeypatch):
    many = [dict(_encounter_row(100.0 * index + 50.0), id=index + 1) for index in range(60)]
    monkeypatch.setattr(enc_repo, "fetch_encounters", lambda db, s, e, m, limit: many)

    outcome = _run_encounters_question(
        _FakeClient(_encounters_script(arguments='{"limit":10}'))
    )
    enc = outcome["results"]["query_encounters"]

    assert enc["returned_count"] == 10
    assert enc["matched_count"] == 60
    assert enc["truncated"] is True
    assert len(enc["encounters"]) == 10


# ------------------------------------------------------------ 7. 模型选择工具
def test_model_can_select_query_encounters(patched_repo):
    assert "query_encounters" in TOOL_REGISTRY
    tool = TOOL_REGISTRY["query_encounters"]
    assert tool.windowed is False
    assert any(schema["function"]["name"] == "query_encounters" for schema in TOOL_SCHEMAS)

    client = _FakeClient(_encounters_script())
    trace = []
    outcome = run_agent(None, client, question="哪些船相遇过？", trace=trace)

    assert all(
        any(t["function"]["name"] == "query_encounters" for t in call["tools"])
        for call in client.chat.completions.calls
    )
    assert trace == [{"tool": "query_encounters", "arguments": "{}"}]
    assert outcome["tools_used"] == ["query_encounters"]


# ------------------------------------------------- 8. 工具结果进入最终响应
def test_tool_result_reaches_final_response(patched_repo):
    outcome = _run_encounters_question(_FakeClient(_encounters_script()))

    assert outcome["answer"] == FINAL_ANSWER
    enc = outcome["results"]["query_encounters"]
    assert enc["encounters"][0]["period_start"] == "2026-03-01T10:00:00+00:00"

    payload = runner._jsonable(outcome)
    payload["request_id"] = "req-ag04-test"
    response = AgentAnalyzeResponse(**payload)
    assert response.tools_used == ["query_encounters"]
    assert any("接近不等于实际交互" in item for item in response.limitations)


# ------------------------------------------------- 9. 全流程没有数据库写入
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
        raise AssertionError("query_encounters 全流程不得触发任何数据库写入")

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
            "FROM encounters e": [ENCOUNTER_ROW],
            "FROM track_build_manifest": [MANIFEST_ROW],
            "max(recorded_at) FROM ship_positions": [{"max": SOURCE_MAX}],
        }
    )

    outcome = _run_encounters_question(_FakeClient(_encounters_script()), db=session)

    assert outcome["status"] == "ok"
    # 适配层 manifest 阈值读取 + 服务层 manifest/行/源最大时间 = 4 条只读 SELECT
    assert len(session.executed_sql) == 4
    for sql in session.executed_sql:
        assert sql.lstrip().lower().startswith("select"), sql
        assert not _WRITE_RE.search(sql), sql

    enc = outcome["results"]["query_encounters"]
    assert enc["returned_count"] == 1
    assert enc["matched_count"] == 1
