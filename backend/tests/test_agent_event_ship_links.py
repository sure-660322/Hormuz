"""AG-05：query_event_ship_links 智能体工具的离线自动测试。

不连接真实数据库、不调用真实模型：
- repository 层用 monkeypatch 打桩（events / links / manifest / ships / observed 反查）；
- 模型响应用脚本化假客户端模拟 Tool Calling（含未知 ID 纠正场景）。

覆盖（对应 AG-05 验收边界）：
1. 正查 observed（事件方向：证据、置信度、投影误差限制）；
2. 正查 mentioned（原文船名文本证据，ship_id 恒为空，不按名称关联模拟船）；
3. 反查 by_ship（observed 反查，mentioned 不参与反向）；
4. 未知 event_id → 纠正循环（提示先用 get_event_context 检索）；
5. 未知 ship_id → 纠正循环（提示先用 search_ships 检索）；
6. 空结果 = 有效零结果；
7. 非法参数（双 ID / mentioned+ship_id / 事件方向带窗口 / 非法 link_type / 单侧窗口）；
8. 模型可选择并调用该工具；
9. 工具结果进入最终响应且符合 schemas_agent 契约；
10. 全流程无任何数据库写入。
"""
import re
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.repositories import event_links as links_repo
from backend.app.repositories import tracks as tracks_repo
from backend.app.schemas_agent import AgentAnalyzeResponse
from backend.app.services.agent import runner
from backend.app.services.agent.event_ship_links_query import run_event_ship_links_query
from backend.app.services.agent.runner import TOOL_REGISTRY, TOOL_SCHEMAS, run_agent

UTC = timezone.utc

EVENT_ROW = {
    "id": 1,
    "event_id": "evt_001",
    "title_zh": "霍尔木兹海峡局势事件",
    "event_datetime": datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC),
    "event_time_text": "3 月 1 日上午",
    "publish_date_min": date(2026, 3, 1),
    "publish_date_max": date(2026, 3, 2),
}

OBSERVED_LINK = {
    "id": 1,
    "link_type": "observed",
    "vessel_name": None,
    "confidence": 0.812,
    "evidence": {
        "min_distance_m": 12340.5,
        "window": ["2026-03-01 02:00:00+00", "2026-03-01 14:00:00+00"],
        "radius_km": 50.0,
    },
    "ship_id": 4,
    "mmsi": "999900004",
    "ship_name": "SIM V2 油轮 004",
    "ship_type": "Tanker",
}

MENTIONED_LINK = {
    "id": 2,
    "link_type": "mentioned",
    "vessel_name": "某真实油轮",
    "confidence": None,
    "evidence": {"source": "events.mentioned_vessels", "vessel_name": "某真实油轮"},
    "ship_id": None,
    "mmsi": None,
    "ship_name": None,
    "ship_type": None,
}

MANIFEST_ROW = {
    "row_count": 8,
    "built_at": datetime(2026, 9, 20, 12, 15, 0, tzinfo=UTC),
    "params": {"radius_km": 50.0, "half_window_hours": 12, "srid": 32640,
               "mentioned": 5, "observed": 3, "geolocated_events": 4},
}

SHIP_ROW = {"id": 4, "mmsi": "999900004", "name": "SIM V2 油轮 004",
            "ship_type": "Tanker", "flag": "SIM"}

SHIP_EVENT_ROW = {
    "id": 1,
    "confidence": 0.812,
    "evidence": {"min_distance_m": 12340.5,
                 "window": ["2026-03-01 02:00:00+00", "2026-03-01 14:00:00+00"]},
    "event_id": "evt_001",
    "title_zh": "霍尔木兹海峡局势事件",
    "event_type": "tension",
    "event_datetime": datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC),
    "event_time_text": "3 月 1 日上午",
    "publish_date_min": date(2026, 3, 1),
    "publish_date_max": date(2026, 3, 2),
    "event_lat": 26.6,
    "event_lng": 56.4,
}

FINAL_ANSWER_OBSERVED = (
    "evt_001 在派生层内 observed 关联到模拟船 SIM V2 油轮 004（ship_id=4），"
    "最小距离约 12.3 公里，仅为模拟时空邻近演示，不构成真实因果。"
)
FINAL_ANSWER_MENTIONED = (
    "evt_001 的报道原文提及真实船名「某真实油轮」；这是文本证据，"
    "未与数据库中的模拟船认定为同一实体。"
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


def _links_script(arguments, final_answer):
    return [
        _FakeMessage(
            tool_calls=[_FakeToolCall("call_links_1", "query_event_ship_links", arguments)]
        ),
        _FakeMessage(content=final_answer),
    ]


@pytest.fixture
def patched_repo(monkeypatch):
    """打桩 event_links / tracks repository 的只读查询。"""
    seen = {}

    def _fetch_links(db, event_pk, event_id):
        seen["event_id"] = event_id
        return [dict(OBSERVED_LINK), dict(MENTIONED_LINK)]

    def _fetch_observed(db, ship_id, from_raw, to_raw):
        seen["ship_id"] = ship_id
        seen["window"] = (from_raw, to_raw)
        return [dict(SHIP_EVENT_ROW)]

    monkeypatch.setattr(links_repo, "fetch_event_by_id", lambda db, eid: dict(EVENT_ROW))
    monkeypatch.setattr(links_repo, "fetch_links_for_event", _fetch_links)
    monkeypatch.setattr(links_repo, "fetch_manifest", lambda db: dict(MANIFEST_ROW))
    monkeypatch.setattr(links_repo, "fetch_observed_for_ship", _fetch_observed)
    monkeypatch.setattr(tracks_repo, "fetch_ship", lambda db, sid: dict(SHIP_ROW))
    return seen


# ------------------------------------------------------- 1. 正查 observed
def test_observed_by_event(patched_repo):
    args = '{"event_id":"evt_001","link_type":"observed"}'
    outcome = run_agent(None, _FakeClient(_links_script(args, FINAL_ANSWER_OBSERVED)),
                        question="evt_001 事件时空上邻近哪些模拟船？", trace=[])

    assert outcome["status"] == "ok"
    assert outcome["tools_used"] == ["query_event_ship_links"]
    result = outcome["results"]["query_event_ship_links"]
    assert result["direction"] == "by_event"
    assert result["event_id"] == "evt_001"
    assert result["link_type"] == "observed"
    assert result["returned_count"] == 1

    link = result["links"][0]
    assert link["link_type"] == "observed"
    assert link["ship"]["id"] == 4
    assert link["confidence"] == 0.812
    assert link["min_distance_m"] == 12340.5
    assert link["is_simulated"] is True
    # 构建参数快照（50 km 半径 / 12 h 半窗 / EPSG:32640）
    assert result["params"]["radius_km"] == 50.0
    assert result["built_at"] == "2026-09-20T12:15:00+00:00"
    # 保留证据与投影误差限制
    assert any("EPSG:32640" in item for item in result["limitations"])
    assert any("不构成真实因果" in item for item in result["limitations"])


# ------------------------------------------------------- 2. 正查 mentioned
def test_mentioned_by_event(patched_repo):
    args = '{"event_id":"evt_001","link_type":"mentioned"}'
    outcome = run_agent(None, _FakeClient(_links_script(args, FINAL_ANSWER_MENTIONED)),
                        question="evt_001 事件被哪些报道提到过船名？", trace=[])

    result = outcome["results"]["query_event_ship_links"]
    assert result["link_type"] == "mentioned"
    assert result["returned_count"] == 1
    link = result["links"][0]
    # mentioned 是原文船名文本证据，ship_id 恒为空
    assert link["vessel_name"] == "某真实油轮"
    assert link["ship"] is None
    assert any("不按名称关联" in item for item in result["limitations"])


# ------------------------------------------------------- 3. 反查 by_ship
def test_reverse_by_ship(patched_repo):
    args = (
        '{"ship_id":4,'
        '"start_at":"2026-03-01T00:00:00+00:00","end_at":"2026-03-02T00:00:00+00:00"}'
    )
    outcome = run_agent(None, _FakeClient(_links_script(args, FINAL_ANSWER_OBSERVED)),
                        question="SIM V2 油轮 004 被哪些事件 observed 关联？", trace=[])

    result = outcome["results"]["query_event_ship_links"]
    assert result["direction"] == "by_ship"
    assert result["ship_id"] == 4
    assert result["ship_name"] == "SIM V2 油轮 004"
    assert result["link_type"] == "observed"
    # 窗口原样下推到 repository（ISO 字符串）
    assert patched_repo["window"] == ("2026-03-01T00:00:00+00:00", "2026-03-02T00:00:00+00:00")

    assert result["returned_count"] == 1
    event = result["events"][0]
    assert event["event_id"] == "evt_001"
    assert event["confidence"] == 0.812
    assert event["representative_point"] == {"lng": 56.4, "lat": 26.6}
    assert any("不参与按船反查" in item for item in result["limitations"])


# --------------------------------------------- 4. 未知 event_id → 纠正循环
def test_unknown_event_id_triggers_correction(patched_repo, monkeypatch):
    # 只有 evt_001 存在；evt_404 必须走纠正分支而不是返回结果
    monkeypatch.setattr(
        links_repo, "fetch_event_by_id",
        lambda db, eid: dict(EVENT_ROW) if eid == "evt_001" else None,
    )
    script = [
        _FakeMessage(
            tool_calls=[_FakeToolCall(
                "call_links_1", "query_event_ship_links", '{"event_id":"evt_404"}'
            )]
        ),
        _FakeMessage(
            tool_calls=[_FakeToolCall(
                "call_links_2", "query_event_ship_links",
                '{"event_id":"evt_001","link_type":"observed"}'
            )]
        ),
        _FakeMessage(content=FINAL_ANSWER_OBSERVED),
    ]
    client = _FakeClient(script)
    outcome = run_agent(None, client, question="evt_404 附近有哪些模拟船？", trace=[])

    assert outcome["status"] == "ok"
    second_call_messages = client.chat.completions.calls[1]["messages"]
    correction = [
        m for m in second_call_messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    # 未知 ID 是纠正分支：提示先用 get_event_context 检索，不得当成零结果
    assert correction and "evt_404 不存在" in correction[0]["content"]
    assert "get_event_context" in correction[0]["content"]


# ---------------------------------------------- 5. 未知 ship_id → 纠正循环
def test_unknown_ship_id_triggers_correction(patched_repo, monkeypatch):
    # 只有 ship_id=4 存在；999 必须走纠正分支而不是返回空结果
    monkeypatch.setattr(
        tracks_repo, "fetch_ship",
        lambda db, sid: dict(SHIP_ROW) if sid == 4 else None,
    )
    script = [
        _FakeMessage(
            tool_calls=[_FakeToolCall(
                "call_links_1", "query_event_ship_links", '{"ship_id":999}'
            )]
        ),
        _FakeMessage(
            tool_calls=[_FakeToolCall(
                "call_links_2", "query_event_ship_links", '{"ship_id":4}'
            )]
        ),
        _FakeMessage(content=FINAL_ANSWER_OBSERVED),
    ]
    client = _FakeClient(script)
    outcome = run_agent(None, client, question="999 号船被哪些事件关联？", trace=[])

    assert outcome["status"] == "ok"
    second_call_messages = client.chat.completions.calls[1]["messages"]
    correction = [
        m for m in second_call_messages
        if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert correction and "不存在" in correction[0]["content"]
    assert "search_ships" in correction[0]["content"]


# ------------------------------------------------------- 6. 空结果有效零
def test_empty_result_is_valid_zero(patched_repo, monkeypatch):
    monkeypatch.setattr(links_repo, "fetch_links_for_event", lambda db, pk, eid: [])

    outcome = run_agent(
        None,
        _FakeClient(_links_script('{"event_id":"evt_001","link_type":"observed"}',
                                  "该事件在派生层内没有 observed 关联。")),
        question="evt_001 附近有哪些模拟船？", trace=[],
    )
    result = outcome["results"]["query_event_ship_links"]
    assert result["status"] == "no_data"
    assert result["links"] == []
    assert result["built_at"] is not None  # 零条≠未构建


# ------------------------------------------------------- 7. 非法参数
def test_invalid_params_rejected(patched_repo):
    with pytest.raises(ValueError, match="必须且只能提供一个"):
        run_event_ship_links_query(None, {"event_id": "evt_001", "ship_id": 4})
    with pytest.raises(ValueError, match="必须且只能提供一个"):
        run_event_ship_links_query(None, {})

    with pytest.raises(ValueError, match="不能按 ship_id 反查"):
        run_event_ship_links_query(None, {"ship_id": 4, "link_type": "mentioned"})

    with pytest.raises(ValueError, match="仅用于按船反查"):
        run_event_ship_links_query(
            None,
            {"event_id": "evt_001",
             "start_at": "2026-03-01T00:00:00+00:00", "end_at": "2026-03-02T00:00:00+00:00"},
        )

    with pytest.raises(ValueError, match="observed/mentioned"):
        run_event_ship_links_query(None, {"event_id": "evt_001", "link_type": "nearby"})

    with pytest.raises(ValueError, match="同时提供或同时省略"):
        run_event_ship_links_query(None, {"ship_id": 4, "start_at": "2026-03-01T00:00:00+00:00"})

    with pytest.raises(ValueError, match="必须带时区"):
        run_event_ship_links_query(
            None, {"ship_id": 4, "start_at": "2026-03-01T00:00:00", "end_at": "2026-03-02T00:00:00"}
        )


# ------------------------------------------------------- 8. 模型选择工具
def test_model_can_select_query_event_ship_links(patched_repo):
    assert "query_event_ship_links" in TOOL_REGISTRY
    tool = TOOL_REGISTRY["query_event_ship_links"]
    assert tool.windowed is False
    assert any(
        schema["function"]["name"] == "query_event_ship_links" for schema in TOOL_SCHEMAS
    )

    client = _FakeClient(_links_script('{"event_id":"evt_001"}', FINAL_ANSWER_OBSERVED))
    trace = []
    outcome = run_agent(None, client, question="evt_001 附近有哪些模拟船？", trace=trace)

    assert all(
        any(t["function"]["name"] == "query_event_ship_links" for t in call["tools"])
        for call in client.chat.completions.calls
    )
    assert trace == [{"tool": "query_event_ship_links", "arguments": '{"event_id":"evt_001"}'}]
    assert outcome["tools_used"] == ["query_event_ship_links"]


# ------------------------------------------------- 9. 工具结果进入最终响应
def test_tool_result_reaches_final_response(patched_repo):
    outcome = run_agent(None, _FakeClient(_links_script('{"event_id":"evt_001"}', FINAL_ANSWER_OBSERVED)),
                        question="evt_001 附近有哪些模拟船？", trace=[])

    assert outcome["answer"] == FINAL_ANSWER_OBSERVED
    result = outcome["results"]["query_event_ship_links"]
    assert result["links"][0]["ship"]["name"] == "SIM V2 油轮 004"

    payload = runner._jsonable(outcome)
    payload["request_id"] = "req-ag05-test"
    response = AgentAnalyzeResponse(**payload)
    assert response.tools_used == ["query_event_ship_links"]
    assert any("EPSG:32640" in item for item in response.limitations)
    assert any("不构成真实因果" in item for item in response.limitations)


# ------------------------------------------------- 10. 全流程没有数据库写入
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
        raise AssertionError("query_event_ship_links 全流程不得触发任何数据库写入")

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
            # 注意：LINKS 查询内嵌「FROM events WHERE event_id」子查询，
            # 事件查询必须用更靠前的 SELECT 列名作标记，且 links 标记优先匹配
            "FROM event_ship_links l": [OBSERVED_LINK, MENTIONED_LINK],
            "SELECT id, event_id, title_zh, event_datetime": [EVENT_ROW],
            "FROM track_build_manifest": [MANIFEST_ROW],
        }
    )

    outcome = run_agent(
        session,
        _FakeClient(_links_script('{"event_id":"evt_001"}', FINAL_ANSWER_OBSERVED)),
        question="evt_001 附近有哪些模拟船？", trace=[],
    )

    assert outcome["status"] == "ok"
    # 适配层事件存在性查询 + 服务层事件查询 + 关联查询 + manifest = 4 条只读 SELECT
    assert len(session.executed_sql) == 4
    for sql in session.executed_sql:
        assert sql.lstrip().lower().startswith("select"), sql
        assert not _WRITE_RE.search(sql), sql

    result = outcome["results"]["query_event_ship_links"]
    assert result["returned_count"] == 1
