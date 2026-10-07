"""区域活动的纯算法层：segment 装配、访问状态机、时长裁剪、按日汇总与 A/B 比较。

输入是仓库层返回的 segment 边界报位行（有界），输出是可序列化的访问记录与汇总；
本模块不接触数据库，全部规则见 docs/area_activity.md §2。
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite

from backend.app.services.area_activity import params
from backend.app.services.area_activity.boundaries import AreaBounds

UTC = timezone.utc
ZERO = timedelta(0)


@dataclass
class Segment:
    """访问内被缺报/跳点/往返断开的连续观测段。"""

    ship_id: int
    seg_no: int
    start_at: datetime = None
    start_fix_id: int | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    end_at: datetime = None
    end_fix_id: int | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None
    fix_seq_start: int | None = None
    fix_seq_end: int | None = None
    start_break_kind: str | None = None
    prev_inside: bool | None = None
    prev_at: datetime | None = None
    prev_fix_id: int | None = None
    prev_latitude: float | None = None
    prev_longitude: float | None = None
    between_first_fix_id: int | None = None
    between_first_at: datetime | None = None
    between_last_fix_id: int | None = None
    between_last_at: datetime | None = None
    next_inside: bool | None = None
    next_at: datetime | None = None
    next_fix_id: int | None = None
    next_latitude: float | None = None
    next_longitude: float | None = None

    @property
    def seconds(self) -> float:
        """观测支持的停留秒数：段内相邻报位区间全部计入。"""
        return max(0.0, (self.end_at - self.start_at).total_seconds())

    @property
    def fix_count(self) -> int:
        if self.fix_seq_start is None or self.fix_seq_end is None:
            return 1
        return max(1, self.fix_seq_end - self.fix_seq_start + 1)


@dataclass
class Event:
    """一次观测到的进入或离开。时间取区内首点/末点，不宣称精确越界时刻。"""

    observed: bool = False
    observed_at: datetime | None = None
    bracket_seconds: float | None = None
    inside_fix: dict | None = None
    outside_fix: dict | None = None
    outside_evidence_in_context: bool = True
    near_boundary: bool = False
    wide_bracket: bool = False
    same_second_conflict: bool = False

    def as_dict(self) -> dict:
        return {
            "observed": self.observed,
            "observed_at": self.observed_at,
            "bracket_seconds": self.bracket_seconds,
            "inside_fix": self.inside_fix,
            "outside_fix": self.outside_fix,
            "outside_evidence_in_context": self.outside_evidence_in_context,
            "near_boundary": self.near_boundary,
            "wide_bracket": self.wide_bracket,
            "same_second_conflict": self.same_second_conflict,
        }


@dataclass
class Visit:
    ship_id: int
    ship_name: str | None
    mmsi: str | None
    ship_type: str | None
    visit_key: str
    prior_state: str
    segments: list[Segment] = field(default_factory=list)
    entry: Event = field(default_factory=Event)
    exit: Event = field(default_factory=Event)
    unobserved_gap_seconds: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def first_inside_at(self) -> datetime:
        return self.segments[0].start_at

    @property
    def last_inside_at(self) -> datetime:
        return self.segments[-1].end_at

    @property
    def observed_seconds(self) -> float:
        return sum(segment.seconds for segment in self.segments)

    @property
    def fix_count(self) -> int:
        return sum(segment.fix_count for segment in self.segments)


def _fix(identifier, at, latitude, longitude) -> dict | None:
    if identifier is None and at is None:
        return None
    return {
        "id": identifier,
        "recorded_at": at,
        "latitude": latitude,
        "longitude": longitude,
    }


def _seconds_between(left: datetime | None, right: datetime | None) -> float | None:
    if left is None or right is None:
        return None
    value = (right - left).total_seconds()
    return value if isfinite(value) else None


def build_segments(rows) -> tuple[dict[int, list[Segment]], dict[int, dict]]:
    """把边界报位行装配为每船 segment 列表与船属性表（行序 ship_id, recorded_at, id）。"""
    by_ship: dict[int, list[Segment]] = {}
    meta: dict[int, dict] = {}
    pending: dict[int, Segment] = {}
    for row in rows:
        ship_id = row["ship_id"]
        segments = by_ship.setdefault(ship_id, [])
        meta.setdefault(ship_id, {
            "ship_name": row["ship_name"],
            "mmsi": row["mmsi"],
            "ship_type": row["ship_type"],
        })
        if row["is_seg_start"]:
            segment = Segment(
                ship_id=ship_id,
                seg_no=row["seg_no"],
                start_at=row["recorded_at"],
                start_fix_id=row["fix_id"],
                start_latitude=row["latitude"],
                start_longitude=row["longitude"],
                fix_seq_start=row["ship_fix_seq"],
                start_break_kind=row["start_break_kind"],
                prev_inside=row["prev_inside"],
                prev_at=row["prev_at"],
                prev_fix_id=row["prev_fix_id"],
                prev_latitude=row["prev_lat"],
                prev_longitude=row["prev_lon"],
                between_first_fix_id=row["between_first_fix_id"],
                between_first_at=row["between_first_at"],
                between_last_fix_id=row["between_last_fix_id"],
                between_last_at=row["between_last_at"],
            )
            segments.append(segment)
            pending[ship_id] = segment
        if row["is_seg_end"]:
            segment = pending.get(ship_id)
            if segment is None:
                # 只有收尾标记的单行段：直接构造。
                segment = Segment(
                    ship_id=ship_id, seg_no=row["seg_no"],
                    start_at=row["recorded_at"], start_fix_id=row["fix_id"],
                    start_latitude=row["latitude"], start_longitude=row["longitude"],
                    fix_seq_start=row["ship_fix_seq"],
                    start_break_kind=row["start_break_kind"],
                    prev_inside=row["prev_inside"], prev_at=row["prev_at"],
                    prev_fix_id=row["prev_fix_id"], prev_latitude=row["prev_lat"],
                    prev_longitude=row["prev_lon"],
                    between_first_fix_id=row["between_first_fix_id"],
                    between_first_at=row["between_first_at"],
                    between_last_fix_id=row["between_last_fix_id"],
                    between_last_at=row["between_last_at"],
                )
                segments.append(segment)
            segment.end_at = row["recorded_at"]
            segment.end_fix_id = row["fix_id"]
            segment.end_latitude = row["latitude"]
            segment.end_longitude = row["longitude"]
            segment.fix_seq_end = row["ship_fix_seq"]
            segment.next_inside = row["next_inside"]
            segment.next_at = row["next_at"]
            segment.next_fix_id = row["next_fix_id"]
            segment.next_latitude = row["next_lat"]
            segment.next_longitude = row["next_lon"]
    for segments in by_ship.values():
        segments.sort(key=lambda item: (item.start_at, item.seg_no))
    # LIMIT 截断等异常情况下可能出现缺 end 的半条 segment，直接丢弃而不是当作完整段。
    for ship_id, segments in list(by_ship.items()):
        complete = [segment for segment in segments if segment.end_at is not None]
        if complete:
            by_ship[ship_id] = complete
        else:
            by_ship.pop(ship_id)
            meta.pop(ship_id, None)
    return by_ship, meta


def _entry_event(segment: Segment, bounds: AreaBounds, gap_seconds: int) -> tuple[Event, str]:
    """访问首段的前置状态与进入事件。"""
    event = Event()
    if segment.start_break_kind == "left_returned":
        prior_state = "outside"
        event.outside_fix = {
            "id": segment.between_last_fix_id,
            "recorded_at": segment.between_last_at,
            "latitude": None,
            "longitude": None,
        }
        event.outside_evidence_in_context = False
    elif segment.prev_inside is None:
        prior_state = "unknown"
    elif segment.prev_inside:
        prior_state = "inside"
    else:
        prior_state = "outside"
        event.outside_fix = _fix(
            segment.prev_fix_id, segment.prev_at,
            segment.prev_latitude, segment.prev_longitude,
        )
    event.inside_fix = _fix(
        segment.start_fix_id, segment.start_at,
        segment.start_latitude, segment.start_longitude,
    )
    if prior_state == "outside":
        event.observed = True
        event.observed_at = segment.start_at
        event.bracket_seconds = _seconds_between(
            segment.between_last_at if segment.start_break_kind == "left_returned" else segment.prev_at,
            segment.start_at,
        )
        event.wide_bracket = (
            event.bracket_seconds is not None and event.bracket_seconds > gap_seconds
        )
        event.same_second_conflict = event.bracket_seconds == 0
        event.near_boundary = (
            bounds.distance_to_boundary_m(segment.start_latitude, segment.start_longitude)
            < params.BOUNDARY_BAND_M
        )
    return event, prior_state


def _exit_event(
    segment: Segment,
    next_segment: Segment | None,
    bounds: AreaBounds,
    gap_seconds: int,
) -> Event:
    event = Event()
    event.inside_fix = _fix(
        segment.end_fix_id, segment.end_at,
        segment.end_latitude, segment.end_longitude,
    )
    if segment.next_inside is False:
        event.observed = True
        event.observed_at = segment.end_at
        event.outside_fix = _fix(
            segment.next_fix_id, segment.next_at,
            segment.next_latitude, segment.next_longitude,
        )
        event.bracket_seconds = _seconds_between(segment.end_at, segment.next_at)
    elif next_segment is not None and next_segment.start_break_kind == "left_returned":
        # 下一次访问通过「期间存在区外报位」被拆开：本次离开有证据，但区外报位在上下文之外。
        event.observed = True
        event.observed_at = segment.end_at
        event.outside_fix = {
            "id": next_segment.between_first_fix_id,
            "recorded_at": next_segment.between_first_at,
            "latitude": None,
            "longitude": None,
        }
        event.outside_evidence_in_context = False
        event.bracket_seconds = _seconds_between(segment.end_at, next_segment.between_first_at)
    else:
        return event
    event.wide_bracket = (
        event.bracket_seconds is not None and event.bracket_seconds > gap_seconds
    )
    event.same_second_conflict = event.bracket_seconds == 0
    event.near_boundary = (
        bounds.distance_to_boundary_m(segment.end_latitude, segment.end_longitude)
        < params.BOUNDARY_BAND_M
    )
    return event


def assemble_visits(rows, bounds: AreaBounds, gap_seconds: int) -> list[Visit]:
    """边界报位行 → 访问记录；gap/jump 保持同一访问，left_returned 拆成两次。"""
    visits: list[Visit] = []
    by_ship, meta = build_segments(rows)
    for ship_id, segments in by_ship.items():
        ship_meta = meta.get(ship_id, {})
        ship_visits: list[Visit] = []
        current: Visit | None = None
        for segment in segments:
            if current is None or segment.start_break_kind in (None, "left_returned"):
                if current is not None:
                    ship_visits.append(current)
                current = Visit(
                    ship_id=ship_id,
                    ship_name=ship_meta.get("ship_name"),
                    mmsi=ship_meta.get("mmsi"),
                    ship_type=ship_meta.get("ship_type"),
                    visit_key=f"s{ship_id}:f{segment.start_fix_id}",
                    prior_state="unknown",
                )
            else:
                gap = _seconds_between(current.segments[-1].end_at, segment.start_at)
                if gap is not None:
                    current.unobserved_gap_seconds += max(0.0, gap)
                if segment.start_break_kind == "gap":
                    current.flags.append("gap_interrupted")
                elif segment.start_break_kind == "jump":
                    current.flags.append("jump_break")
            current.segments.append(segment)
        if current is not None:
            ship_visits.append(current)

        for index, visit in enumerate(ship_visits):
            entry, prior_state = _entry_event(visit.segments[0], bounds, gap_seconds)
            visit.entry = entry
            visit.prior_state = prior_state
            next_segment = (
                ship_visits[index + 1].segments[0] if index + 1 < len(ship_visits) else None
            )
            visit.exit = _exit_event(visit.segments[-1], next_segment, bounds, gap_seconds)
            visit.flags = sorted(set(visit.flags) | set(_visit_flags(visit)))
        visits.extend(ship_visits)

    visits.sort(key=lambda item: (item.entry.observed_at or item.first_inside_at, item.ship_id))
    return visits


def _visit_flags(visit: Visit) -> list[str]:
    flags: list[str] = []
    if visit.entry.wide_bracket:
        flags.append("wide_entry_bracket")
    if visit.exit.wide_bracket:
        flags.append("wide_exit_bracket")
    if visit.entry.near_boundary:
        flags.append("near_boundary_entry")
    if visit.exit.near_boundary:
        flags.append("near_boundary_exit")
    if visit.entry.same_second_conflict or visit.exit.same_second_conflict:
        flags.append("same_second_conflict")
    if not visit.entry.outside_evidence_in_context or not visit.exit.outside_evidence_in_context:
        flags.append("outside_evidence_out_of_context")
    return sorted(set(flags))


def visit_status(visit: Visit, window_start: datetime, window_end: datetime) -> str:
    """访问主状态（优先级固定：截断 → 缺报 → 不确定 → 完整）。"""
    started_before_window = visit.first_inside_at < window_start
    if started_before_window or visit.prior_state == "unknown":
        return "truncated_start"
    if not visit.exit.observed:
        return "truncated_end"
    if "gap_interrupted" in visit.flags:
        return "interrupted"
    if visit.flags:
        return "uncertain"
    return "complete"


def clip_seconds(segment: Segment, start: datetime, end: datetime) -> float:
    """segment 与 [start, end) 的交集秒数。"""
    left = max(segment.start_at, start)
    right = min(segment.end_at, end)
    if right <= left:
        return 0.0
    return (right - left).total_seconds()


def touches(segment: Segment, start: datetime, end: datetime) -> bool:
    return segment.end_at >= start and segment.start_at < end


def visit_window_seconds(visit: Visit, start: datetime, end: datetime) -> float:
    return sum(clip_seconds(segment, start, end) for segment in visit.segments)


def visits_touching(visits: list[Visit], start: datetime, end: datetime) -> list[Visit]:
    return [
        visit for visit in visits
        if any(touches(segment, start, end) for segment in visit.segments)
    ]


def _in_window(moment: datetime | None, start: datetime, end: datetime) -> bool:
    return moment is not None and start <= moment < end


def summarize(visits: list[Visit], start: datetime, end: datetime) -> dict:
    """全窗汇总。窗口内没有访问时返回有效零结果（由调用方区分 no_data）。"""
    touching = visits_touching(visits, start, end)
    statuses = [visit_status(visit, start, end) for visit in touching]
    ship_seconds = sum(visit_window_seconds(visit, start, end) for visit in touching)
    near_boundary = sum(
        1 for visit in touching
        if visit.entry.near_boundary or visit.exit.near_boundary
    )
    return {
        "ships_observed": len({visit.ship_id for visit in touching}),
        "observed_entry_count": sum(
            1 for visit in touching if _in_window(visit.entry.observed_at, start, end)
        ),
        "observed_exit_count": sum(
            1 for visit in touching if _in_window(visit.exit.observed_at, start, end)
        ),
        "observed_ship_seconds": round(ship_seconds, 3),
        "observed_ship_hours": round(ship_seconds / 3600.0, 3),
        "visit_count": len(touching),
        "complete_visit_count": statuses.count("complete"),
        "truncated_start_visit_count": statuses.count("truncated_start"),
        "truncated_end_visit_count": statuses.count("truncated_end"),
        "interrupted_visit_count": statuses.count("interrupted"),
        "uncertain_visit_count": statuses.count("uncertain"),
        "prior_state_unknown_visit_count": sum(
            1 for visit in touching if visit.prior_state == "unknown"
        ),
        "near_boundary_event_count": near_boundary,
        "unobserved_gap_seconds": round(
            sum(visit.unobserved_gap_seconds for visit in touching), 3
        ),
    }


def day_starts(start: datetime, end: datetime) -> list[date]:
    """[start, end) 覆盖的 UTC 自然日。"""
    first = start.astimezone(UTC).date()
    last = (end - timedelta(microseconds=1)).astimezone(UTC).date()
    days = []
    current = first
    while current <= last:
        days.append(current)
        current += timedelta(days=1)
    return days


def daily_breakdown(visits: list[Visit], start: datetime, end: datetime) -> list[dict]:
    """按 UTC 自然日汇总；每日去重船数不累加，船时按当日交集裁剪。"""
    rows = []
    for day in day_starts(start, end):
        day_start = datetime.combine(day, time(0, 0), tzinfo=UTC)
        day_end = day_start + timedelta(days=1)
        window_start = max(day_start, start)
        window_end = min(day_end, end)
        touching = [
            visit for visit in visits
            if any(touches(segment, window_start, window_end) for segment in visit.segments)
        ]
        statuses = [visit_status(visit, start, end) for visit in touching]
        ship_seconds = sum(
            clip_seconds(segment, window_start, window_end)
            for visit in touching for segment in visit.segments
        )
        rows.append({
            "date": day.isoformat(),
            "ships_observed": len({visit.ship_id for visit in touching}),
            "observed_entry_count": sum(
                1 for visit in touching
                if _in_window(visit.entry.observed_at, window_start, window_end)
            ),
            "observed_exit_count": sum(
                1 for visit in touching
                if _in_window(visit.exit.observed_at, window_start, window_end)
            ),
            "observed_ship_seconds": round(ship_seconds, 3),
            "observed_ship_hours": round(ship_seconds / 3600.0, 3),
            "visits_touching_day": len(touching),
            "complete_visit_count": statuses.count("complete"),
            "truncated_visit_count": statuses.count("truncated_start") + statuses.count("truncated_end"),
            "interrupted_visit_count": statuses.count("interrupted"),
            "uncertain_visit_count": statuses.count("uncertain"),
        })
    return rows


def visit_payload(visit: Visit, start: datetime, end: datetime) -> dict:
    window_seconds = visit_window_seconds(visit, start, end)
    status = visit_status(visit, start, end)
    entry = visit.entry.as_dict()
    exit_ = visit.exit.as_dict()
    # 事件时间是否落在本查询窗口内：决定它是否计入 summary/daily 的次数
    entry["in_window"] = _in_window(visit.entry.observed_at, start, end)
    exit_["in_window"] = _in_window(visit.exit.observed_at, start, end)
    return {
        "visit_key": visit.visit_key,
        "ship_id": visit.ship_id,
        "ship_name": visit.ship_name,
        "mmsi": visit.mmsi,
        "ship_type": visit.ship_type,
        "entry": entry,
        "exit": exit_,
        "prior_state": visit.prior_state,
        "first_inside_at": visit.first_inside_at,
        "last_inside_at": visit.last_inside_at,
        "fix_count": visit.fix_count,
        "segment_count": len(visit.segments),
        "segments": [
            {
                "segment_no": index + 1,
                "start_at": segment.start_at,
                "end_at": segment.end_at,
                "start_fix_id": segment.start_fix_id,
                "end_fix_id": segment.end_fix_id,
                "seconds": round(segment.seconds, 3),
                "in_window_seconds": round(clip_seconds(segment, start, end), 3),
                "fix_count": segment.fix_count,
            }
            for index, segment in enumerate(visit.segments)
        ],
        "observed_seconds": round(visit.observed_seconds, 3),
        "window_seconds": round(window_seconds, 3),
        "unobserved_gap_seconds": round(visit.unobserved_gap_seconds, 3),
        "started_before_window": visit.first_inside_at < start,
        "touches_window": any(touches(segment, start, end) for segment in visit.segments),
        "status": status,
        "flags": visit.flags,
    }


def compare_metrics(
    summary_a: dict, summary_b: dict, length_days_a: float, length_days_b: float
) -> list[dict]:
    """A/B 指标：绝对差与变化率；基期为 0 时变化率为 null。

    日均指标按窗口实际长度（含小数天）计算，短窗口不会被整天数放大或压低。
    """
    definitions = [
        ("ships_observed", "出现去重船数", "艘", 1),
        ("observed_entry_count", "观测进入次数", "次", 1),
        ("observed_exit_count", "观测离开次数", "次", 1),
        ("observed_ship_hours", "累计船时", "小时", 0),
    ]
    metrics = []
    for key, label, unit, digits in definitions:
        value_a = float(summary_a.get(key) or 0)
        value_b = float(summary_b.get(key) or 0)
        delta = value_b - value_a
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "a": round(value_a, 3), "b": round(value_b, 3),
            "delta": round(delta, 3),
            "change_rate": None if value_a == 0 else round(delta / value_a, 4),
        })
    for key, source, label, unit in (
        ("ships_observed_per_day", "ships_observed", "出现去重船数日均", "艘/日"),
        ("observed_entry_count_per_day", "observed_entry_count", "观测进入次数日均", "次/日"),
        ("observed_ship_hours_per_day", "observed_ship_hours", "累计船时日均", "小时/日"),
    ):
        value_a = float(summary_a.get(source) or 0) / length_days_a if length_days_a else 0.0
        value_b = float(summary_b.get(source) or 0) / length_days_b if length_days_b else 0.0
        delta = value_b - value_a
        metrics.append({
            "key": key, "label": label, "unit": unit,
            "a": round(value_a, 3), "b": round(value_b, 3),
            "delta": round(delta, 3),
            "change_rate": None if value_a == 0 else round(delta / value_a, 4),
        })
    return metrics
