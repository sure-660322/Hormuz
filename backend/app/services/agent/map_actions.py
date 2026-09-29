"""Create map suggestions only from successful, identified tool results."""
from __future__ import annotations

import re
from datetime import datetime


_TRACK_WORDS = re.compile(r"显示|高亮|查看|打开|定位")
_NEGATED = re.compile(r"不要|别|无需|不用")
_EXPLICIT_WINDOW = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})")


def _valid_window(start: object, end: object) -> bool:
    try:
        a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return a.tzinfo is not None and b.tzinfo is not None and 0 < (b - a).total_seconds() <= 86400
    except (TypeError, ValueError):
        return False


def build_map_actions(question: str, results: dict, *, forced_window: bool = False) -> list[dict]:
    tracks = [item for item in results.values()
              if item.get("tool_name") == "get_ship_track" and item.get("status") == "ok"
              and isinstance(item.get("ship_id"), int) and item.get("fix_count", 0) > 0
              and _valid_window(item.get("start_at"), item.get("end_at"))]
    events = [event for item in results.values()
              if item.get("tool_name") == "get_event_context" and item.get("status") == "ok"
              for event in item.get("events", []) if isinstance(event.get("event_id"), str)
              and event.get("event_datetime") is not None
              and event.get("event_lat") is not None and event.get("event_lng") is not None]
    actions: list[dict] = []
    window_explicit = forced_window or len(_EXPLICIT_WINDOW.findall(question)) >= 2
    if len(tracks) == 1 and window_explicit:
        track = tracks[0]
        explicit = ("轨迹" in question and bool(_TRACK_WORDS.search(question))
                    and not _NEGATED.search(question)
                    and window_explicit)
        actions.append({"type": "ship_track", "trigger": "automatic" if explicit else "suggested",
                        "ship_id": track["ship_id"], "start_at": track["start_at"],
                        "end_at": track["end_at"], "source": "nnu_ais"})
    if len(events) == 1:
        actions.append({"type": "event", "trigger": "suggested",
                        "event_id": events[0]["event_id"], "source": "news"})
    return actions
