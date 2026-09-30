"""Bounded map requests derived from current, successful AIS tool evidence."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import select

from backend.app.models import ShipPosition
from backend.app.services.agent.config import SHIP_DATA_SOURCE

_DISPLAY = re.compile(r"显示|高亮|打开|定位|画出|绘制|标出|地图上看|地图中看")
_NEGATED = re.compile(r"不要|(?<![识分区])别|无需|不用|不需要|不必|取消")
_PRONOUN = re.compile(r"这[条艘]船|那[条艘]船|刚才.*船|它")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})")
_RELATIVE = re.compile(r"(?:最近|过去|前|近)\s*(\d+|一|两|二)\s*(?:个)?\s*(小时|天)")


def display_intent(question: str) -> bool:
    return bool(_DISPLAY.search(question)) and not _NEGATED.search(question)


def resolve_map_window(db, question, playback_at, start, end):
    """Explicit UTC > bounded relative time > replay-adjacent 24h; verify DB coverage."""
    stamps = _ISO.findall(question)
    if start is not None or end is not None:
        return start, end, "用户输入"
    if len(stamps) == 2:
        return tuple(datetime.fromisoformat(s.replace("Z", "+00:00")) for s in stamps) + ("用户输入 UTC 时间窗",)
    if stamps or re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}月\d{1,2}日|\d{1,2}[:：]\d{2}|\d+点", question):
        raise ValueError("请给出两个完整、带时区的 ISO 8601 起止时间，避免日期或时区歧义")
    if playback_at is None or not re.search(r"船|轨迹|位置|移动|定位|高亮", question):
        return start, end, None
    relative = _RELATIVE.search(question)
    if re.search(r"最近|过去|前.*(?:小时|天)", question) and not relative:
        raise ValueError("请使用“最近 N 小时”（N 为 1–24 的整数）或带时区的起止时间")
    if re.search(r"昨天|今天|明天|上周|本周|前天|刚才的时间", question):
        raise ValueError("请给出带时区的起止时间，或使用“最近 N 小时”；历史 AIS 不按现实今天推定日期")
    hours = 24
    if relative:
        number = relative[1]
        hours = {"一": 1, "两": 2, "二": 2}.get(number) or int(number)
        if relative[2] == "天":
            hours *= 24
        if not 0 < hours <= 24:
            raise ValueError("相对时间窗口须大于 0 且不超过 24 小时")
    query = select(ShipPosition.recorded_at).where(ShipPosition.data_source == SHIP_DATA_SOURCE)
    first = db.scalar(query.order_by(ShipPosition.recorded_at).limit(1))
    last = db.scalar(query.order_by(ShipPosition.recorded_at.desc()).limit(1))
    if first is None or last is None:
        raise ValueError("当前没有可用的 nnu_ais 报位覆盖")
    if not first <= playback_at <= last:
        raise ValueError("地图回放时刻超出当前 AIS 覆盖，请刷新回放数据")
    until = playback_at
    since = max(first, until - timedelta(hours=hours))
    if since == until:
        until = min(last, first + timedelta(hours=hours))
    if since >= until:
        raise ValueError("当前 AIS 覆盖不足以建立时间窗口")
    source = f"地图回放时刻附近 {'最近 ' + str(hours) + ' 小时' if relative else '默认 24 小时'}（按 AIS 覆盖裁剪）"
    return since, until, source


def _valid_window(start: object, end: object) -> bool:
    try:
        a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        return a.tzinfo is not None and b.tzinfo is not None and 0 < (b - a).total_seconds() <= 86400
    except (TypeError, ValueError):
        return False


def build_map_actions(question: str, results: dict, *, forced_window: bool = False,
                      target_ship_id: int | None = None, window_source: str | None = None) -> list[dict]:
    if _NEGATED.search(question):
        return []
    tracks = [item for item in results.values() if item.get("tool_name") == "get_ship_track"]
    actions: list[dict] = []
    ambiguous = any(item.get("tool_name") == "search_ships" and
                    (item.get("matched_count", 0) > 1 or item.get("truncated"))
                    for item in results.values())
    if len(tracks) == 1:
        track = tracks[0]
        ship_id = track.get("ship_id")
        named = any(item.get("tool_name") == "search_ships" and item.get("status") == "ok"
                    and item.get("matched_count") == 1 and any(
                        match.get("ship_id") == ship_id and any(str(match.get(key) or "").strip() and
                            str(match[key]).casefold() in question.casefold() for key in ("name", "mmsi", "imo"))
                        for match in item.get("matches", [])) for item in results.values())
        explicit_id = bool(re.search(rf"(?:ship[_ ]?id|船(?:舶)?\s*(?:ID|编号)?|ID)\s*[:：#]?\s*{ship_id}(?!\d)", question, re.I))
        if ambiguous and not (explicit_id or (_PRONOUN.search(question) and target_ship_id == ship_id)):
            return []
        referent_ok = not _PRONOUN.search(question) or target_ship_id == ship_id or named or explicit_id
        position = "轨迹" not in question and bool(re.search(r"定位|高亮|位置|标出", question))
        minimum = 1 if position else 2
        if (referent_ok and track.get("status") == "ok" and isinstance(ship_id, int)
                and not isinstance(ship_id, bool) and ship_id > 0 and not track.get("truncated")
                and track.get("fix_count", 0) >= minimum
                and _valid_window(track.get("start_at"), track.get("end_at"))):
            action = {"type": "ship_position" if position else "ship_track",
                      "trigger": "automatic" if display_intent(question) else "suggested",
                      "ship_id": ship_id, "start_at": track["start_at"], "end_at": track["end_at"],
                      "source": "nnu_ais", "window_source": window_source or "工具核实时间窗"}
            if position:
                fixes = track.get("fixes", [])
                if not fixes:
                    return []
                action["recorded_at"] = fixes[-1]["recorded_at"]
            actions.append(action)
    events = [event for item in results.values()
              if item.get("tool_name") == "get_event_context" and item.get("status") == "ok"
              for event in item.get("events", []) if isinstance(event.get("event_id"), str)
              and event.get("event_datetime") is not None
              and event.get("event_lat") is not None and event.get("event_lng") is not None]
    if len(events) == 1:
        actions.append({"type": "event", "trigger": "suggested",
                        "event_id": events[0]["event_id"], "source": "news"})
    return actions
