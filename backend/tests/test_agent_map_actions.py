from backend.app.services.agent.map_actions import build_map_actions


QUESTION = "显示船 ID 360 在 2026-02-28T14:00:00Z 至 2026-02-28T15:00:00Z 的轨迹"
TRACK = {"tool_name": "get_ship_track", "status": "ok", "ship_id": 360, "fix_count": 28,
         "start_at": "2026-02-28T14:00:00Z", "end_at": "2026-02-28T15:00:00Z"}


def test_explicit_verified_track_is_automatic():
    assert build_map_actions(QUESTION, {"one": TRACK}) == [{
        "type": "ship_track", "trigger": "automatic", "ship_id": 360,
        "start_at": TRACK["start_at"], "end_at": TRACK["end_at"], "source": "nnu_ais", "window_source": "工具核实时间窗",
    }]


def test_ambiguous_or_failed_tracks_do_not_move_map():
    assert build_map_actions(QUESTION, {"one": TRACK, "two": {**TRACK, "ship_id": 361}}) == []
    assert build_map_actions(QUESTION, {"one": {**TRACK, "status": "no_data", "fix_count": 0}}) == []
    assert build_map_actions(QUESTION, {"one": {**TRACK, "end_at": "2026-03-03T15:00:00Z"}}) == []
    assert build_map_actions("显示这艘船的轨迹", {"one": TRACK}) == []
    assert build_map_actions("不要显示轨迹", {"one": TRACK}, forced_window=True) == []


def test_one_located_event_is_suggested_only():
    result = {"tool_name": "get_event_context", "status": "ok", "events": [
        {"event_id": "evt_004", "event_datetime": "2026-02-26T00:00:00Z",
         "event_lat": 26.0, "event_lng": 56.0},
    ]}
    assert build_map_actions("看看新闻事件", {"one": result}) == [{
        "type": "event", "trigger": "suggested", "event_id": "evt_004", "source": "news",
    }]
    result["events"][0]["event_lat"] = None
    assert build_map_actions("看看新闻事件", {"one": result}) == []


import pytest
from datetime import datetime, timezone
from backend.app.services.agent.map_actions import resolve_map_window
from backend.app.schemas_agent import AgentAnalyzeRequest, AgentAnalyzeResponse


def test_natural_language_default_window_and_position_followup():
    search = {"tool_name": "search_ships", "status": "ok", "matched_count": 1,
              "matches": [{"ship_id": 360, "name": "STALLION"}]}
    actions = build_map_actions("STALLION 显示这条船的轨迹", {"search": search, "track": TRACK})
    assert actions[0]["trigger"] == "automatic"
    fixes = [{"recorded_at": TRACK["end_at"], "longitude": 56.2, "latitude": 26.2}]
    position = build_map_actions("帮我在地图中定位它", {"track": {**TRACK, "fixes": fixes}}, target_ship_id=360)
    assert position[0]["type"] == "ship_position"
    assert position[0]["recorded_at"] == fixes[0]["recorded_at"]
    assert position[0]["trigger"] == "automatic"
    assert build_map_actions("帮我定位它", {"track": {**TRACK, "fixes": fixes}}, target_ship_id=361) == []
    assert build_map_actions("显示它 2026-02-28T14:00Z 至 2026-02-28T15:00Z 的轨迹", {"track": TRACK}) == []


@pytest.mark.parametrize("change", [{"fix_count": 1}, {"fix_count": 0}, {"status": "error"}, {"truncated": True}])
def test_invalid_tracks_do_not_generate_actions(change):
    assert build_map_actions("显示船 ID 360 的轨迹", {"one": {**TRACK, **change}}) == []


def test_ambiguous_search_does_not_choose_one_candidate():
    assert build_map_actions("STALLION 显示轨迹", {"track": TRACK, "search": {
        "tool_name": "search_ships", "status": "ok", "matched_count": 2}}) == []
    assert build_map_actions("船 ID 360 移动了吗", {"track": TRACK})[0]["trigger"] == "suggested"
    assert build_map_actions("画出船 ID 360 的轨迹", {"track": TRACK})[0]["trigger"] == "automatic"
    assert build_map_actions("识别并显示船 ID 360 的轨迹", {"track": TRACK})[0]["trigger"] == "automatic"
    assert build_map_actions("显示它的轨迹", {"track": TRACK, "search": {
        "tool_name": "search_ships", "status": "ok", "matched_count": 3}}, target_ship_id=360)[0]["ship_id"] == 360


class CoverageDB:
    def __init__(self, first, last):
        self.values = iter([first, last])
    def scalar(self, query):
        return next(self.values)


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_replay_default_relative_and_first_frame_window():
    first, last = dt("2026-02-25T00:00Z"), dt("2026-03-03T15:00Z")
    at = dt("2026-02-28T15:00Z")
    start, end, source = resolve_map_window(CoverageDB(first, last), "显示船的轨迹", at, None, None)
    assert start == dt("2026-02-27T15:00Z") and end == at and "默认" in source
    start, end, source = resolve_map_window(CoverageDB(first, last), "显示船最近6小时的轨迹", at, None, None)
    assert start == dt("2026-02-28T09:00Z") and end == at and "最近 6" in source
    start, end, _ = resolve_map_window(CoverageDB(first, last), "定位船", first, None, None)
    assert start == first and end == dt("2026-02-26T00:00Z")
    start, end, source = resolve_map_window(None, QUESTION, at, None, None)
    assert start == dt(TRACK["start_at"]) and end == dt(TRACK["end_at"])
    assert "用户" in source


@pytest.mark.parametrize("question", ["显示昨天的船舶轨迹", "显示船最近25小时轨迹", "显示船最近0小时轨迹"])
def test_unsupported_or_unbounded_relative_window_rejected(question):
    with pytest.raises(ValueError):
        resolve_map_window(None, question, dt("2026-02-28T15:00Z"), None, None)


def test_stale_replay_and_empty_coverage_rejected():
    first, last = dt("2026-02-25T00:00Z"), dt("2026-03-03T15:00Z")
    for db in [CoverageDB(first, last), CoverageDB(None, None)]:
        with pytest.raises(ValueError):
            resolve_map_window(db, "显示船轨迹", dt("2026-09-30T00:00Z"), None, None)
    with pytest.raises(ValueError):
        AgentAnalyzeRequest(question="定位船", map_context={"playback_at": "2026-02-28T15:00:00"})


def test_runner_forces_replay_window_and_rechecks_instead_of_reusing_history(monkeypatch):
    from backend.app.services.agent import business_tools
    from backend.app.services.agent.langchain_runner import run_lc_agent
    from backend.app.services.agent.ship_tracks import ShipTrackResult
    from backend.tests.fake_llm import ScriptedFakeLLM, tool_call
    at = dt("2026-02-28T15:00Z")
    captured = []
    def query(db, ship_id, start_at, end_at):
        captured.append((ship_id, start_at, end_at))
        return ShipTrackResult(status="ok", ship_id=ship_id, start_at=start_at, end_at=end_at, fix_count=3)
    monkeypatch.setattr(business_tools, "get_ship_track", query)
    llm = ScriptedFakeLLM(script=[tool_call("get_ship_track", {
        "ship_id": 360, "start_at": "2026-03-02T15:00Z", "end_at": "2026-03-03T15:00Z"}), "工具已核实"])
    result = run_lc_agent(CoverageDB(dt("2026-02-25T00:00Z"), dt("2026-03-03T15:00Z")),
        "显示它的轨迹", history=[{"role": "assistant", "content": "旧窗口无数据"}],
        map_context={"playback_at": at, "target_ship_id": 360}, llm=llm, sql_enabled=False)
    assert captured == [(360, dt("2026-02-27T15:00Z"), at)]
    assert result["map_actions"][0]["trigger"] == "automatic"
    assert "默认 24" in result["map_actions"][0]["window_source"]
    assert not any(message.content == "旧窗口无数据" for message in llm.received[0])
    AgentAnalyzeResponse(**{**result, "request_id": "test-map"})


def test_map_command_without_current_tools_cannot_claim_success():
    from backend.app.services.agent.langchain_runner import run_lc_agent
    from backend.tests.fake_llm import ScriptedFakeLLM
    result = run_lc_agent(CoverageDB(dt("2026-02-25T00:00Z"), dt("2026-03-03T15:00Z")),
        "帮我定位它", map_context={"playback_at": dt("2026-02-28T15:00Z"), "target_ship_id": None},
        llm=ScriptedFakeLLM(script=["已在地图显示"]), sql_enabled=False)
    assert result["status"] == "needs_clarification"
    assert result["map_actions"] == []
    assert "尚未执行" in result["answer"]


@pytest.mark.parametrize("question", ["显示船最近半小时轨迹", "显示船2月28日的轨迹", "定位船2026-02-28T15:00Z"])
def test_incomplete_time_not_silently_defaulted(question):
    with pytest.raises(ValueError):
        resolve_map_window(None, question, dt("2026-02-28T15:00Z"), None, None)
