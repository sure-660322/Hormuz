from backend.app.services.agent.map_actions import build_map_actions


QUESTION = "显示船 ID 360 在 2026-02-28T14:00:00Z 至 2026-02-28T15:00:00Z 的轨迹"
TRACK = {"tool_name": "get_ship_track", "status": "ok", "ship_id": 360, "fix_count": 28,
         "start_at": "2026-02-28T14:00:00Z", "end_at": "2026-02-28T15:00:00Z"}


def test_explicit_verified_track_is_automatic():
    assert build_map_actions(QUESTION, {"one": TRACK}) == [{
        "type": "ship_track", "trigger": "automatic", "ship_id": 360,
        "start_at": TRACK["start_at"], "end_at": TRACK["end_at"], "source": "nnu_ais",
    }]


def test_ambiguous_or_failed_tracks_do_not_move_map():
    assert build_map_actions(QUESTION, {"one": TRACK, "two": {**TRACK, "ship_id": 361}}) == []
    assert build_map_actions(QUESTION, {"one": {**TRACK, "status": "no_data", "fix_count": 0}}) == []
    assert build_map_actions(QUESTION, {"one": {**TRACK, "end_at": "2026-03-03T15:00:00Z"}}) == []
    assert build_map_actions("显示这艘船的轨迹", {"one": TRACK}) == []
    assert build_map_actions("不要显示轨迹", {"one": TRACK}, forced_window=True)[0]["trigger"] == "suggested"


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
