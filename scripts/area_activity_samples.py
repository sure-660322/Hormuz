"""区域船舶活动：独立样例场景 + 朴素期望值复算（不依赖后端实现）。

本文件的唯一事实来源是 `docs/area_activity.md` 的：
  * §1.1/§1.2  半开矩形包含规则与默认分析区域
  * §2.0–§2.6  报位/访问/进出/缺报跳点/时长与按日统计/快照/比较口径
  * §3         参数默认值
  * §4.3–§4.5  REST 契约字段名（期望值按这些字段名组织，便于逐字段比对）

2026-10-07 文档定版（`area_activity/1.0.1`）后同步的口径（本轮复验基准）：
  * §2.0 有界越界探测：对「待探测对」（间隔 > excursion_probe_seconds=480 s，或位移
    ≥ jump_min_distance_km 且推算速度 > jump_speed_kn）按 (ship_id, recorded_at, id) 探测
    两报位之间是否还有该船报位（允许越出 context_bbox），有则 left_returned；
    480 s 的来源：2 × 外扩距离 9.96 km ÷ max_plausible_speed_kn=40 kn ≈ 484 s，取 480 s；
  * §2.0/§3/§4.3 来源批次条件**同时**作用于观测上下文、越界探测与覆盖统计；带 batch_ids 请求时
    coverage.batch_ids 回显实际生效批次（样例 S21 复验三者的批次范围一致）；
  * §2.3 跳点需位移 ≥ 1.0 km **且** 推算速度 > 30 kn；unobserved_gap_seconds 含 gap 与 jump；
  * §2.3 行 2（left_returned）的 wide_bracket 口径已了结（2026-10-07 文档修正）：两侧事件
    **不**无条件置位，而是按 §2.3 统一规则 `wide = bracket_seconds > gap_seconds` 判定；
    短时外出（括号各只有数百秒）两侧均为 false。本文件只保留数值口径，不再登记「文档字面」
    备选值，验证脚本按该口径硬断言（原分歧记录见 verify 脚本的 doc_implementation_divergences）；
  * §2.4 每日 = 当日 ∩ 窗口 [start,end)；进入/离开只计事件时间落在窗口内的事件；
    status 优先级固定（truncated_start → truncated_end → interrupted → uncertain → complete）；
    flags 取值固定为 8 个；单报位访问 = 一条 0 长度 segment；
  * §2.5 window_days = 自然日个数（分桶用），window_length_days = 实际长度（日均分母），
    equal_length 按实际长度比较；
  * §2.6 partial 只由质量标记或明细截断触发，窗口边缘截断不触发；
  * §4.5 明细含 entry/exit.in_window、segment_count 与每段 fix_count。
这里**不 import backend.app.***，也不连接数据库；`scripts/verify_area_activity_samples.py`
负责把 `SCENARIOS` 里的合成报位写进独立测试库，再用 HTTP 接口结果与这里的期望值比对。

用法（工作树根目录）：
    python -X utf8 scripts/area_activity_samples.py            # 打印 self-check 与场景表
    python -X utf8 scripts/area_activity_samples.py --json     # 额外输出期望值 JSON

文档中未明确、需要实现侧确认的口径，统一记录在 `analysis["ambiguities"]`
（键为期望值字段路径，值为 {"reason": ..., "alternates": [...]}）；验证脚本遇到
这些字段不一致时按 WARN 处理，而不是 FAIL。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

UTC = timezone.utc

# --------------------------------------------------------------------------
# §1.2 默认分析区域（版本 hormuz_core_v1 / 1.0.0）
# --------------------------------------------------------------------------
DEFAULT_AREA_ID = "hormuz_core_v1"
DEFAULT_AREA_VERSION = "1.0.0"
DEFAULT_AREA = {"south": 25.8, "west": 55.8, "north": 27.1, "east": 57.1}

# --------------------------------------------------------------------------
# §3 参数与默认值（area_activity/1.0.1）
# --------------------------------------------------------------------------
ALGORITHM_VERSION = "area_activity/1.0.1"
DEFAULT_PARAMS: dict[str, Any] = {
    "freshness_seconds": 3600.0,
    "gap_seconds": 1800.0,
    "jump_speed_kn": 30.0,
    "jump_min_distance_km": 1.0,
    "state_lookback_seconds": 21600.0,
    "state_lookahead_seconds": 21600.0,
    "context_margin_deg": 0.05,
    # §3 v1.0.1：越界探测阈值与它依据的最大可信航速。
    "max_plausible_speed_kn": 40.0,
    "excursion_probe_seconds": 480.0,
    "boundary_band_m": 500.0,
    "day_bucket_time_zone": "UTC",
    "source": "nnu_ais",
    "max_window_days": 7,
    "max_rect_span_deg": 10.0,
    "max_visit_rows": 2000,
    "max_snapshot_ships": 5000,
}

# 验证脚本插入测试库 ais_import_batches 的批次行（S21 用 9001/9002 两个批次；
# coverage.batch_ids 回显的是该表的批次 id，不是报位上出现过的批次）。
SAMPLE_BATCH_IDS: tuple[int, ...] = (9001, 9002)

EARTH_RADIUS_M = 6371008.8
METERS_PER_NAUTICAL_MILE = 1852.0


# ==========================================================================
# 基础数据结构
# ==========================================================================
@dataclass(frozen=True)
class Rect:
    """轴对齐矩形（§1.1：west<=lon<east，south<=lat<north）。"""

    south: float
    west: float
    north: float
    east: float

    @property
    def lat_span(self) -> float:
        return self.north - self.south

    @property
    def lon_span(self) -> float:
        return self.east - self.west

    def as_query(self) -> dict[str, float]:
        return {"west": self.west, "south": self.south, "east": self.east, "north": self.north}


DEFAULT_RECT = Rect(**DEFAULT_AREA)


@dataclass(frozen=True)
class Ship:
    id: int
    mmsi: str
    name: str
    ship_type: str | None = None
    flag: str | None = None


@dataclass(frozen=True)
class Fix:
    """一条报位（ship_positions 一行，§2.0）。"""

    id: int
    ship_id: int
    recorded_at: datetime
    latitude: float
    longitude: float
    speed: float | None = None
    data_source: str = "nnu_ais"
    source_batch_id: int | None = 9001
    source_row: int | None = None


# ==========================================================================
# 几何与单位换算（§1.1 半开规则 / §2.3 haversine 推算速度）
# ==========================================================================
def _radians(deg: float) -> float:
    return deg * math.pi / 180.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """两点球面距离（米）。"""
    p1, p2 = _radians(lat1), _radians(lat2)
    dp = p2 - p1
    dl = _radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def inside_rect(latitude: float, longitude: float, rect: Rect) -> bool:
    """§1.1：经度西含东不含、纬度南含北不含。"""
    return (rect.west <= longitude < rect.east) and (rect.south <= latitude < rect.north)


def in_context(latitude: float, longitude: float, rect: Rect, margin_deg: float) -> bool:
    """§2.0：context_bbox = 分析矩形外扩 context_margin_deg，沿用同一半开规则。"""
    ctx = Rect(
        south=rect.south - margin_deg,
        west=rect.west - margin_deg,
        north=rect.north + margin_deg,
        east=rect.east + margin_deg,
    )
    return inside_rect(latitude, longitude, ctx)


def distance_to_rect_m(latitude: float, longitude: float, rect: Rect) -> float:
    """§2.3：haversine 到矩形最近边（区内为到最近边的距离，区外为到最近点的距离）。"""
    if inside_rect(latitude, longitude, rect):
        return min(
            haversine_m(latitude, longitude, latitude, rect.west),
            haversine_m(latitude, longitude, latitude, rect.east),
            haversine_m(latitude, longitude, rect.south, longitude),
            haversine_m(latitude, longitude, rect.north, longitude),
        )
    clat = min(max(latitude, rect.south), rect.north)
    clon = min(max(longitude, rect.west), rect.east)
    return haversine_m(latitude, longitude, clat, clon)


def implied_speed_kn(prev: Fix, cur: Fix) -> float:
    """§2.3：推算速度 = haversine(prev, cur) / 间隔小时数（节）。"""
    dt_h = (cur.recorded_at - prev.recorded_at).total_seconds() / 3600.0
    if dt_h <= 0:
        return float("inf")
    return haversine_m(prev.latitude, prev.longitude, cur.latitude, cur.longitude) / METERS_PER_NAUTICAL_MILE / dt_h


# ==========================================================================
# 朴素复算：时段出现与进出（§2.0–§2.4）
# ==========================================================================
def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _overlap_seconds(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> float:
    lo = max(a_start, b_start)
    hi = min(a_end, b_end)
    return max(0.0, (hi - lo).total_seconds())


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def _days_covered(start: datetime, end: datetime) -> list[date]:
    """[start, end) 覆盖的 UTC 自然日（§2.5 window_days / §2.4 按日分桶）。"""
    days: list[date] = []
    day = _as_utc(start).date()
    last = (_as_utc(end) - timedelta(microseconds=1)).date()
    while day <= last:
        days.append(day)
        day += timedelta(days=1)
    return days


def ship_type_matches(ship_type: str | None, wanted: Sequence[str] | None) -> bool:
    """§3 船型筛选：精确匹配 + 保留值 __missing__（NULL/空）与 __unknown__（未知）。"""
    if not wanted:
        return True
    raw = (ship_type or "").strip()
    for item in wanted:
        if item == "__missing__":
            if raw == "":
                return True
        elif item == "__unknown__":
            if raw == "未知":
                return True
        elif raw == item:
            return True
    return False


def _batch_ok(fix: Fix, p: dict[str, Any]) -> bool:
    """§3/§4.3 来源批次白名单；`batch_ids` 为 None 表示不筛批次。"""
    wanted = p.get("batch_ids")
    if not wanted:
        return True
    return fix.source_batch_id in wanted


def _coverage_batch_ids(batch_ids: Sequence[int] | None) -> list[int]:
    """§4.3：coverage.batch_ids = 实际生效批次，取自 ais_import_batches（验证脚本插入的批次行）。"""
    if batch_ids:
        return sorted({int(b) for b in batch_ids if int(b) in set(SAMPLE_BATCH_IDS)})
    return sorted(SAMPLE_BATCH_IDS)


def _fix_public(fix: Fix) -> dict[str, Any]:
    return {
        "id": fix.id,
        "recorded_at": _iso(fix.recorded_at),
        "latitude": fix.latitude,
        "longitude": fix.longitude,
    }


def naive_analyze(
    ships: Iterable[Ship],
    fixes: Iterable[Fix],
    rect: Rect,
    start: datetime,
    end: datetime,
    params: dict[str, Any] | None = None,
    ship_types: Sequence[str] | None = None,
    batch_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """按文档 §2.0–§2.4 朴素复算一个窗口的活动（不引用后端实现）。

    `fixes` 必须是**全部**样例报位：§2.0 的「有界越界探测」要用到 context_bbox 之外的
    报位来判断两条相邻区内报位之间是否还有该船报位（left_returned 的依据）。
    `batch_ids`（§3/§4.3）同时约束观测上下文、越界探测与覆盖统计，三处必须一致。

    返回 {"summary", "daily", "visits", "status_hint", "ambiguities", ...}。
    字段名对齐 §4.3/§4.5，便于与 HTTP 响应逐字段比对。
    """
    p = dict(DEFAULT_PARAMS)
    p.update(params or {})
    p["batch_ids"] = [int(b) for b in batch_ids] if batch_ids else None
    start = _as_utc(start)
    end = _as_utc(end)
    ships = list(ships)
    fixes = list(fixes)
    ship_by_id = {s.id: s for s in ships}

    # 0) §2.0 越界探测索引：全部同源报位按 (recorded_at, id) 排序，不受 scope / context_bbox
    #    限制，但同样受来源批次约束（探测与上下文批次范围必须一致）。
    probe_index: dict[int, list[Fix]] = {}
    for fix in fixes:
        if p["source"] and fix.data_source != p["source"]:
            continue
        if not _batch_ok(fix, p):
            continue
        probe_index.setdefault(fix.ship_id, []).append(fix)
    for probe_seq in probe_index.values():
        probe_seq.sort(key=lambda f: (f.recorded_at, f.id))

    # 1) 来源 / 批次 / 船型 / 状态序列范围 scope=[start-lookback, end+lookahead) ∩ context_bbox（§2.0）
    scope_start = start - timedelta(seconds=p["state_lookback_seconds"])
    scope_end = end + timedelta(seconds=p["state_lookahead_seconds"])
    scoped: dict[int, list[Fix]] = {}
    scope_fix_count = 0
    for fix in fixes:
        ship = ship_by_id.get(fix.ship_id)
        if ship is None or not ship_type_matches(ship.ship_type, ship_types):
            continue
        if p["source"] and fix.data_source != p["source"]:
            continue
        if not _batch_ok(fix, p):
            continue
        if not (scope_start <= fix.recorded_at < scope_end):
            continue
        if not in_context(fix.latitude, fix.longitude, rect, p["context_margin_deg"]):
            continue
        scoped.setdefault(fix.ship_id, []).append(fix)
        scope_fix_count += 1
    sequences = {sid: sorted(fs, key=lambda f: (f.recorded_at, f.id)) for sid, fs in scoped.items()}

    # 2) 访问：状态序列中的极大连续区内段；§2.0 探测到「期间还有该船报位」时切成两次访问
    visits: list[dict[str, Any]] = []
    ambiguities: dict[str, dict[str, Any]] = {}
    for sid in sorted(sequences):
        seq = sequences[sid]
        ship = ship_by_id[sid]
        all_fixes = probe_index.get(sid, [])
        for block in _inside_blocks(seq, rect, all_fixes, p):
            prev_fix = seq[block["first_idx"] - 1] if block["first_idx"] > 0 else None
            next_fix = seq[block["last_idx"] + 1] if block["last_idx"] + 1 < len(seq) else None
            visits.append(
                _build_visit(ship, block, prev_fix, next_fix, rect, start, end, p, ambiguities)
            )

    visits.sort(key=lambda v: (v["first_inside_at"], v["ship_id"], v["visit_key"]))
    # §2.4：只有与 [start,end) 相交的访问进入汇总与明细
    touching = [v for v in visits if v["touches_window"]]

    # 3) 汇总（§2.4 定版：与窗口相交的访问；进入/离开只计事件时间落在 [start,end) 的事件）
    candidate_ship_ids = sorted(
        {
            f.ship_id
            for sid, seq in sequences.items()
            for f in seq
            if inside_rect(f.latitude, f.longitude, rect) and start <= f.recorded_at < end
        }
    )
    ships_from_visits = len({v["ship_id"] for v in touching})
    window_seconds = sum(v["window_seconds"] for v in touching)

    summary = {
        "ships_observed": len(candidate_ship_ids),
        "observed_entry_count": sum(
            1 for v in touching if v["entry"]["observed"] and v["entry"]["in_window"]
        ),
        "observed_exit_count": sum(
            1 for v in touching if v["exit"]["observed"] and v["exit"]["in_window"]
        ),
        "observed_ship_seconds": window_seconds,
        "observed_ship_hours": window_seconds / 3600.0,
        "visit_count": len(touching),
        "complete_visit_count": sum(1 for v in touching if v["status"] == "complete"),
        "truncated_start_visit_count": sum(
            1 for v in touching if v["status"] == "truncated_start"
        ),
        "truncated_end_visit_count": sum(1 for v in touching if v["status"] == "truncated_end"),
        "interrupted_visit_count": sum(1 for v in touching if v["status"] == "interrupted"),
        "uncertain_visit_count": sum(1 for v in touching if v["status"] == "uncertain"),
        "prior_state_unknown_visit_count": sum(
            1 for v in touching if v["prior_state"] == "unknown"
        ),
        "unobserved_gap_seconds": sum(v["unobserved_gap_seconds"] for v in touching),
        "scope_fix_count": scope_fix_count,
    }
    # 仍属开放选择：「出现去重船数」按 §2.0 的候选船定义（窗口内至少一条区域内报位）
    # 还是按「与窗口相交的访问涉及的船」去重，文档未写；两者只在访问跨越窗口且窗口内
    # 没有报位时不同（当前样例两者一致）。
    _add_ambiguity(
        ambiguities,
        "summary.ships_observed",
        "§2.0 把「候选船」定义为窗口内至少有一条区域内报位，§2.4 只写「出现去重船数」；"
        "主口径取候选船数，备选为与窗口相交的访问涉及的船数",
        [ships_from_visits],
    )

    # 4) 按日统计（§2.4 定版：每日 = 当日 ∩ 窗口 [start,end)；事件计数同样只计落桶事件）
    daily: list[dict[str, Any]] = []
    day = start.date()
    last_day = (end - timedelta(microseconds=1)).date()
    while day <= last_day:
        d_start, d_end = _day_bounds(day)
        bucket_start = max(d_start, start)
        bucket_end = min(d_end, end)
        day_visits = [v for v in visits if _visit_touches(v, bucket_start, bucket_end)]
        ships_today = sorted(
            sid
            for sid in candidate_ship_ids
            if any(
                inside_rect(f.latitude, f.longitude, rect)
                and bucket_start <= f.recorded_at < bucket_end
                for f in sequences.get(sid, [])
            )
        )
        seconds_today = sum(
            _overlap_seconds(
                _parse(seg["start_at"]), _parse(seg["end_at"]), bucket_start, bucket_end
            )
            for v in visits
            for seg in v["segments"]
        )
        entries_today = sum(
            1
            for v in visits
            if v["entry"]["observed"]
            and bucket_start <= _parse(v["entry"]["observed_at"]) < bucket_end
        )
        exits_today = sum(
            1
            for v in visits
            if v["exit"]["observed"]
            and bucket_start <= _parse(v["exit"]["observed_at"]) < bucket_end
        )
        statuses = [v["status"] for v in day_visits]
        row = {
            "date": day.isoformat(),
            "ships_observed": len(ships_today),
            "observed_entry_count": entries_today,
            "observed_exit_count": exits_today,
            "observed_ship_seconds": seconds_today,
            "observed_ship_hours": seconds_today / 3600.0,
            "visits_touching_day": len(day_visits),
            "complete_visit_count": statuses.count("complete"),
            "truncated_visit_count": statuses.count("truncated_start")
            + statuses.count("truncated_end"),
            "interrupted_visit_count": statuses.count("interrupted"),
            "uncertain_visit_count": statuses.count("uncertain"),
        }
        daily.append(row)
        _add_ambiguity(
            ambiguities,
            f"daily[{day.isoformat()}].ships_observed",
            "§2.4 定版每日桶 = 当日 ∩ 窗口；「出现去重船数」按桶内区域内报位去重（主口径）"
            "还是按与桶相交的访问去重（实现侧）文档未写，两者只在访问跨越桶且桶内无报位时不同",
            [len({v["ship_id"] for v in day_visits})],
        )
        for field_name in (
            "complete_visit_count",
            "truncated_visit_count",
            "interrupted_visit_count",
            "uncertain_visit_count",
        ):
            _add_ambiguity(
                ambiguities,
                f"daily[{day.isoformat()}].{field_name}",
                "§5.3 给出每日状态计数，但未说明按「访问在当日桶内的状态」还是「访问在全窗口的"
                "状态」归类；主口径与 summary 一致（全窗口 status）",
                [],
            )
        day += timedelta(days=1)

    # 5) status（§2.6 定版：partial 只由质量标记或明细截断触发，窗口边缘截断不触发；
    #    本函数算的是未截断的情况，visit_limit 截断由验证脚本单独探针）
    if scope_fix_count == 0:
        status_hint = "no_data"
    elif any(v["flags"] or v["prior_state"] == "unknown" for v in touching):
        status_hint = "partial"
    else:
        status_hint = "ok"  # 含「有报位但窗口内区域内无船」的有效零结果

    return {
        "summary": summary,
        "daily": daily,
        "visits": touching,
        "all_visits": len(visits),
        "status_hint": status_hint,
        "scope_fix_count": scope_fix_count,
        "candidate_ship_ids": candidate_ship_ids,
        "ambiguities": ambiguities,
    }


def _add_ambiguity(
    store: dict[str, dict[str, Any]], path: str, reason: str, alternates: list[Any]
) -> None:
    store[path] = {"reason": reason, "alternates": alternates}


def _probe_between(
    all_fixes: Sequence[Fix], prev: Fix, cur: Fix, p: dict[str, Any]
) -> list[Fix]:
    """§2.0 有界越界探测：两条报位之间是否还有该船其它报位（允许越出 context_bbox）。

    只对「待探测对」调用；同样受来源批次约束（探测与上下文的批次范围必须一致）。
    结果按 (recorded_at, id) 排序，调用方只取首末报位的 id 与时间。
    """
    source = p["source"]
    between = [
        f
        for f in all_fixes
        if (not source or f.data_source == source)
        and _batch_ok(f, p)
        and (prev.recorded_at, prev.id) < (f.recorded_at, f.id) < (cur.recorded_at, cur.id)
    ]
    between.sort(key=lambda f: (f.recorded_at, f.id))
    return between


def _pair_break(
    prev: Fix, cur: Fix, all_fixes: Sequence[Fix], p: dict[str, Any]
) -> tuple[str, list[Fix]]:
    """§2.0/§2.3：相邻两条区域内报位的判定（none / gap / jump / left_returned）。"""
    dt = (cur.recorded_at - prev.recorded_at).total_seconds()
    if dt <= 0:
        return "none", []  # 同秒：区间长度为 0，不按缺报/跳点处理（§2.3 末条）
    dist_km = haversine_m(prev.latitude, prev.longitude, cur.latitude, cur.longitude) / 1000.0
    speed_kn = dist_km / (dt / 3600.0) / 1.852
    is_gap = dt > p["gap_seconds"]
    is_jump = dist_km >= p["jump_min_distance_km"] and speed_kn > p["jump_speed_kn"]
    # §2.0 v1.0.1：待探测对 = 间隔 > excursion_probe_seconds（默认 480 s）或满足跳点条件。
    if not (dt > p["excursion_probe_seconds"] or is_jump):
        return "none", []  # 间隔 ≤480 s：不可能完成一次外出往返，该区间计入停留时长
    between = _probe_between(all_fixes, prev, cur, p)
    if between:
        return "left_returned", between  # §2.3 行 2：有区外证据 -> 拆成两次访问
    if is_gap:
        return "gap", []
    if is_jump:
        return "jump", []
    return "none", []  # 间隔在 (probe_seconds, gap_seconds] 且无中间报位 -> 仍是连续观测


def _inside_blocks(
    seq: Sequence[Fix], rect: Rect, all_fixes: Sequence[Fix], p: dict[str, Any]
) -> list[dict[str, Any]]:
    """状态序列 → 访问块：极大连续区内段；§2.0 探测到中间有报位时断成两次访问。

    每块记录 first_idx/last_idx（取上下文中的前后相邻报位）、gap/jump 断点、以及
    left_returned 的探测证据（entry_lr / exit_lr = 中间报位的首末）。
    """
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for idx, fix in enumerate(seq):
        if not inside_rect(fix.latitude, fix.longitude, rect):
            current = None
            continue
        if current is None:
            current = {
                "first_idx": idx,
                "last_idx": idx,
                "fixes": [fix],
                "entry_lr": None,
                "exit_lr": None,
                "breaks": [],
            }
            blocks.append(current)
            continue
        kind, between = _pair_break(current["fixes"][-1], fix, all_fixes, p)
        if kind == "left_returned":
            # 该对经 §2.0 探测证明期间有同船报位：本段在此结束，当前报位开启下一次访问
            current["exit_lr"] = between
            current = {
                "first_idx": idx,
                "last_idx": idx,
                "fixes": [fix],
                "entry_lr": between,
                "exit_lr": None,
                "breaks": [],
            }
            blocks.append(current)
            continue
        if kind in ("gap", "jump"):
            current["breaks"].append({"at": len(current["fixes"]), "kind": kind})
        current["fixes"].append(fix)
        current["last_idx"] = idx
    return blocks


def _visit_touches(visit: dict[str, Any], lo: datetime, hi: datetime) -> bool:
    """segment 与区间的相交判定（含 0 长度 segment 落在区间起点）。"""
    return any(
        _parse(seg["end_at"]) >= lo and _parse(seg["start_at"]) < hi
        for seg in visit["segments"]
    )


def _probe_fix(fix: Fix) -> dict[str, Any]:
    """§2.0：越界证据只取 id 与时间，不读取该区间内报位的位置。"""
    return {
        "id": fix.id,
        "recorded_at": _iso(fix.recorded_at),
        "latitude": None,
        "longitude": None,
    }


def _build_visit(
    ship: Ship,
    block: dict[str, Any],
    prev_fix: Fix | None,
    next_fix: Fix | None,
    rect: Rect,
    start: datetime,
    end: datetime,
    p: dict[str, Any],
    ambiguities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    run: list[Fix] = block["fixes"]
    first, last = run[0], run[-1]
    lr_in: list[Fix] | None = block["entry_lr"]
    lr_out: list[Fix] | None = block["exit_lr"]

    # ---- 进入（§2.2.3；left_returned 的证据在上下文之外，见 §2.0/§2.3 行 2）----
    if lr_in is not None:
        prior_state = "outside"
        entry_observed = True
        entry_at = first.recorded_at
        entry_bracket = (first.recorded_at - lr_in[-1].recorded_at).total_seconds()
        entry_outside_fix = _probe_fix(lr_in[-1])
        entry_evidence_in_context = False
    elif prev_fix is None:
        prior_state = "unknown"
        entry_observed = False
        entry_at = None
        entry_bracket = None
        entry_outside_fix = None
        entry_evidence_in_context = True
    else:
        prior_state = "outside"
        entry_observed = True
        entry_at = first.recorded_at
        entry_bracket = (first.recorded_at - prev_fix.recorded_at).total_seconds()
        entry_outside_fix = _fix_public(prev_fix)
        entry_evidence_in_context = True
    entry_wide = bool(
        entry_observed and entry_bracket is not None and entry_bracket > p["gap_seconds"]
    )
    entry = {
        "observed": entry_observed,
        "observed_at": _iso(entry_at),
        "bracket_seconds": entry_bracket,
        "inside_fix": _fix_public(first),
        "outside_fix": entry_outside_fix,
        "outside_evidence_in_context": entry_evidence_in_context,
        "near_boundary": bool(
            entry_observed
            and distance_to_rect_m(first.latitude, first.longitude, rect) < p["boundary_band_m"]
        ),
        "wide_bracket": entry_wide,
        "same_second_conflict": bool(entry_observed and entry_bracket == 0),
        # §4.5 + §2.4：事件时间是否落在本查询窗口内；未观测 -> 不计数 -> false
        "in_window": bool(entry_observed and start <= entry_at < end),
    }

    # ---- 离开（§2.2.4；同上）----
    if lr_out is not None:
        exit_observed = True
        exit_at = last.recorded_at
        exit_bracket = (lr_out[0].recorded_at - last.recorded_at).total_seconds()
        exit_outside_fix = _probe_fix(lr_out[0])
        exit_evidence_in_context = False
    elif next_fix is not None:
        exit_observed = True
        exit_at = last.recorded_at
        exit_bracket = (next_fix.recorded_at - last.recorded_at).total_seconds()
        exit_outside_fix = _fix_public(next_fix)
        exit_evidence_in_context = True
    else:
        exit_observed = False
        exit_at = None
        exit_bracket = None
        exit_outside_fix = None
        exit_evidence_in_context = True
    exit_wide = bool(
        exit_observed and exit_bracket is not None and exit_bracket > p["gap_seconds"]
    )
    exit_ = {
        "observed": exit_observed,
        "observed_at": _iso(exit_at),
        "bracket_seconds": exit_bracket,
        "inside_fix": _fix_public(last),
        "outside_fix": exit_outside_fix,
        "outside_evidence_in_context": exit_evidence_in_context,
        "near_boundary": bool(
            exit_observed
            and distance_to_rect_m(last.latitude, last.longitude, rect) < p["boundary_band_m"]
        ),
        "wide_bracket": exit_wide,
        "same_second_conflict": bool(exit_observed and exit_bracket == 0),
        "in_window": bool(exit_observed and start <= exit_at < end),
    }

    # ---- 缺报 / 跳点（§2.3）：两类断点都拆 segment，且都计入 unobserved_gap_seconds ----
    breaks = {item["at"]: item["kind"] for item in block["breaks"]}
    segments: list[list[Fix]] = []
    current: list[Fix] = [first]
    for index in range(1, len(run)):
        if index in breaks:
            segments.append(current)
            current = [run[index]]
        else:
            current.append(run[index])
    segments.append(current)
    unobserved_gap = sum(
        (run[index].recorded_at - run[index - 1].recorded_at).total_seconds()
        for index in sorted(breaks)
    )

    # ---- flags（§2.4 定版：取值固定为 8 个）----
    flags: list[str] = []
    kinds = set(breaks.values())
    if "gap" in kinds:
        flags.append("gap_interrupted")
    if "jump" in kinds:
        flags.append("jump_break")
    if entry_wide:
        flags.append("wide_entry_bracket")
    if exit_wide:
        flags.append("wide_exit_bracket")
    if entry["near_boundary"]:
        flags.append("near_boundary_entry")
    if exit_["near_boundary"]:
        flags.append("near_boundary_exit")
    if entry["same_second_conflict"] or exit_["same_second_conflict"]:
        flags.append("same_second_conflict")
    if not entry_evidence_in_context or not exit_evidence_in_context:
        flags.append("outside_evidence_out_of_context")
    flags = sorted(set(flags))

    seg_rows: list[dict[str, Any]] = []
    for idx, seg in enumerate(segments, start=1):
        seg_rows.append(
            {
                "segment_no": idx,
                "start_at": _iso(seg[0].recorded_at),
                "end_at": _iso(seg[-1].recorded_at),
                "start_fix_id": seg[0].id,
                "end_fix_id": seg[-1].id,
                "seconds": (seg[-1].recorded_at - seg[0].recorded_at).total_seconds(),
                "in_window_seconds": _overlap_seconds(
                    seg[0].recorded_at, seg[-1].recorded_at, start, end
                ),
                "fix_count": len(seg),
                "fix_ids": [f.id for f in seg],
            }
        )
    observed_seconds = sum(s["seconds"] for s in seg_rows)
    window_seconds = sum(s["in_window_seconds"] for s in seg_rows)
    touches = any(
        _parse(s["end_at"]) >= start and _parse(s["start_at"]) < end for s in seg_rows
    )
    status = _status_of(first.recorded_at, prior_state, exit_observed, flags, start)

    visit_key = f"s{ship.id}:f{first.id}"
    visit = {
        "visit_key": visit_key,
        "ship_id": ship.id,
        "ship_name": ship.name,
        "mmsi": ship.mmsi,
        "ship_type": ship.ship_type,
        "entry": entry,
        "exit": exit_,
        "prior_state": prior_state,
        "first_inside_at": _iso(first.recorded_at),
        "last_inside_at": _iso(last.recorded_at),
        "fix_count": len(run),
        "segment_count": len(seg_rows),
        "segments": seg_rows,
        "observed_seconds": observed_seconds,
        "window_seconds": window_seconds,
        "unobserved_gap_seconds": unobserved_gap,
        "started_before_window": bool(first.recorded_at < start),
        "touches_window": bool(touches),
        "status": status,
        "flags": flags,
    }
    # 仍属开放选择：未观测事件没有括号区间，§4.5 未规定取值（主口径 null，备选 0.0）。
    for side, observed in (("entry", entry_observed), ("exit", exit_observed)):
        if not observed:
            _add_ambiguity(
                ambiguities,
                f"visits[{visit_key}].{side}.bracket_seconds",
                f"§4.5 未定义未观测{side}事件的 bracket_seconds；主口径 null（不存在括号区间），备选 0.0",
                [0.0],
            )
    # §2.3 行 2（left_returned）的 wide_bracket 口径：2026-10-07 文档已按实现口径修正为
    # 「两侧事件按 §2.3 统一规则判定，即 bracket_seconds > gap_seconds 才为 true，不是无条件置位」。
    # 因此这里不再登记「文档字面（true）」备选值 —— 短时外出两侧应为 false，属硬断言；
    # 分歧的解决记录保留在 scripts/verify_area_activity_samples.py 的
    # DOC_IMPLEMENTATION_DIVERGENCES（status=resolved），不删除以便追溯。
    return visit


def _status_of(
    first_inside_at: datetime,
    prior_state: str,
    exit_observed: bool,
    flags: Sequence[str],
    start: datetime,
) -> str:
    """§2.4 定版优先级：truncated_start → truncated_end → interrupted → uncertain → complete。"""
    if first_inside_at < start or prior_state == "unknown":
        return "truncated_start"
    if not exit_observed:
        return "truncated_end"
    if "gap_interrupted" in flags:
        return "interrupted"
    if flags:
        return "uncertain"
    return "complete"


# ==========================================================================
# 朴素复算：时刻在场（§2.1）
# ==========================================================================
def naive_snapshot(
    ships: Iterable[Ship],
    fixes: Iterable[Fix],
    rect: Rect,
    at: datetime,
    freshness_seconds: float = 3600.0,
    ship_types: Sequence[str] | None = None,
) -> dict[str, Any]:
    """§2.1：每船取 recorded_at <= at 的最新报位；过期不计入、不回退到更早的区内点。"""
    at = _as_utc(at)
    ships = [s for s in ships if ship_type_matches(s.ship_type, ship_types)]
    by_ship: dict[int, list[Fix]] = {}
    for fix in fixes:
        if fix.data_source != DEFAULT_PARAMS["source"]:
            continue
        if fix.recorded_at <= at:
            by_ship.setdefault(fix.ship_id, []).append(fix)

    in_area: list[dict[str, Any]] = []
    out_fresh = 0
    stale = 0
    for ship in sorted(ships, key=lambda s: s.id):
        seq = by_ship.get(ship.id)
        if not seq:
            continue  # 没有 <= at 的报位 -> 不参与评估
        latest = max(seq, key=lambda f: (f.recorded_at, f.id))
        age = (at - latest.recorded_at).total_seconds()
        if age > freshness_seconds:
            stale += 1
            continue
        if inside_rect(latest.latitude, latest.longitude, rect):
            in_area.append(
                {
                    "ship_id": ship.id,
                    "name": ship.name,
                    "mmsi": ship.mmsi,
                    "ship_type": ship.ship_type,
                    "latitude": latest.latitude,
                    "longitude": latest.longitude,
                    "speed": latest.speed,
                    "recorded_at": _iso(latest.recorded_at),
                    "age_seconds": age,
                    "fresh": True,
                    "inside": True,
                }
            )
        else:
            out_fresh += 1
    evaluated = len(in_area) + out_fresh + stale
    return {
        "status_hint": "ok" if (in_area or out_fresh or stale) else "no_data",
        "summary": {
            "in_area_count": len(in_area),
            "out_of_area_fresh_count": out_fresh,
            "stale_fix_count": stale,
            "evaluated_ship_count": evaluated,
        },
        "ships": in_area,
        "ambiguities": {
            "summary.evaluated_ship_count": {
                "reason": "§2.1 未定义「评估船数」是否包含没有任何报位、或最新报位在 at 之后的船；"
                "主口径 = 有 <= at 报位（被实际判定）的船",
                "alternates": [len(ships), len(by_ship)],
            },
        },
    }


# ==========================================================================
# 时间辅助
# ==========================================================================
def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("样例时间必须是带时区的 UTC datetime（§1.3）")
    return value.astimezone(UTC)


def _parse(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def U(month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    """2026 年的 UTC 时刻（样例统一使用 2026 年，避免与真实 AIS 批次时间重叠）。"""
    return datetime(2026, month, day, hour, minute, second, tzinfo=UTC)


# ==========================================================================
# 样例构造
# ==========================================================================
@dataclass
class Scenario:
    name: str
    title: str
    doc_ref: str
    start: datetime
    end: datetime
    ship_ids: list[int]
    rect: Rect = DEFAULT_RECT
    use_default_area: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    ship_types: list[str] | None = None
    # §3/§4.3 来源批次白名单（主请求）；None = 不筛批次。
    batch_ids: list[int] | None = None
    covers: list[str] = field(default_factory=list)
    notes: str = ""
    expected: dict[str, Any] | None = None
    filter_checks: list[dict[str, Any]] = field(default_factory=list)
    # 场景内的“移除报位”对照探针（例如 S22：删掉区外中间报位后必须仍是一次访问）。
    # {"fix_ids": [...], "note": "...", "expected": {...}}，由验证脚本在测试库里临时删除并恢复。
    removal_probe: dict[str, Any] | None = None
    soft_all_reason: str = ""

    def query_params(self, visit_limit: int | None = 500) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [
            ("start", _iso(self.start)),
            ("end", _iso(self.end)),
        ]
        if not self.use_default_area:
            out.extend((k, str(v)) for k, v in self.rect.as_query().items())
        for t in self.ship_types or []:
            out.append(("ship_type", t))
        for batch in self.batch_ids or []:
            out.append(("batch_ids", str(batch)))
        if visit_limit is not None:
            out.append(("visit_limit", str(visit_limit)))
        return out


@dataclass
class SnapshotScenario:
    name: str
    title: str
    at: datetime
    ship_ids: list[int]
    rect: Rect = DEFAULT_RECT
    use_default_area: bool = False
    freshness_seconds: float | None = None
    covers: list[str] = field(default_factory=list)
    notes: str = ""
    expected: dict[str, Any] | None = None

    def query_params(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [("at", _iso(self.at))]
        if not self.use_default_area:
            out.extend((k, str(v)) for k, v in self.rect.as_query().items())
        if self.freshness_seconds is not None:
            out.append(("freshness_seconds", str(self.freshness_seconds)))
        return out


@dataclass
class CompareScenario:
    name: str
    title: str
    start_a: datetime
    end_a: datetime
    start_b: datetime
    end_b: datetime
    ship_ids: list[int]
    rect: Rect = DEFAULT_RECT
    covers: list[str] = field(default_factory=list)
    notes: str = ""
    expected: dict[str, Any] | None = None

    def query_params(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [
            ("start_a", _iso(self.start_a)),
            ("end_a", _iso(self.end_a)),
            ("start_b", _iso(self.start_b)),
            ("end_b", _iso(self.end_b)),
        ]
        out.extend((k, str(v)) for k, v in self.rect.as_query().items())
        return out


@dataclass
class ValidationCase:
    """§1.3 参数校验 / §2.6 状态区分 / §3 上限。"""

    name: str
    endpoint: str  # activity | snapshot | compare
    params: list[tuple[str, str]]
    expect_http: int
    doc_ref: str
    soft: bool = False
    note: str = ""


class SampleBuilder:
    """集中登记样例船与报位，保证 id 稳定、唯一。"""

    def __init__(self) -> None:
        self.ships: list[Ship] = []
        self.fixes: list[Fix] = []
        self._fix_id = 0
        self._row = 0

    def ship(self, ship_id: int, name: str, ship_type: str | None, flag: str = "PA") -> Ship:
        ship = Ship(id=ship_id, mmsi=f"4190{ship_id:05d}", name=name, ship_type=ship_type, flag=flag)
        self.ships.append(ship)
        return ship

    def fix(
        self,
        ship_id: int,
        when: datetime,
        latitude: float,
        longitude: float,
        speed: float | None = None,
        data_source: str = "nnu_ais",
        source_batch_id: int | None = 9001,
    ) -> Fix:
        self._fix_id += 1
        self._row += 1
        fix = Fix(
            id=self._fix_id,
            ship_id=ship_id,
            recorded_at=_as_utc(when),
            latitude=latitude,
            longitude=longitude,
            speed=speed,
            data_source=data_source,
            source_batch_id=source_batch_id,
            source_row=self._row,
        )
        self.fixes.append(fix)
        return fix


def _seq(
    builder: SampleBuilder,
    ship_id: int,
    t0: datetime,
    t1: datetime,
    step_minutes: int,
    lat: float,
    lon: float,
    dlat: float = 0.0,
    dlon: float = 0.0,
) -> None:
    """按固定间隔生成一段区内报位序列（坐标单调微移，避免触发跳点判定）。"""
    step = timedelta(minutes=step_minutes)
    t, clat, clon = t0, lat, lon
    while t <= t1:
        builder.fix(ship_id, t, round(clat, 6), round(clon, 6))
        t += step
        clat += dlat
        clon += dlon


# --- 场景内常用的「区外/区内」坐标（区外点都在 context_bbox 内）-------------
# 默认矩形 south=25.8 west=55.8 north=27.1 east=57.1，context 外扩 0.05°
OUT_W = (26.400, 55.770)   # 矩形西侧外（55.75 <= 55.770 < 55.80）
OUT_E = (26.400, 57.120)   # 矩形东侧外（57.10 <= 57.120 < 57.15）
OUT_N = (27.130, 56.400)   # 矩形北侧外（27.10 <= 27.130 < 27.15）
OUT_S = (25.770, 56.400)   # 矩形南侧外（25.75 <= 25.770 < 25.80）
IN_1 = (26.400, 55.900)    # 区内，靠近西边（距任意边界 > 500 m）
IN_2 = (26.420, 55.950)
IN_3 = (26.440, 56.000)


def build_registry() -> dict[str, Any]:
    b = SampleBuilder()

    # ---------------- S01 正常进入 + 离开（§2.2.3/§2.2.4/§2.4）------------
    b.ship(101, "SAMPLE ENTER EXIT", "油轮")
    s01_start, s01_end = U(4, 1, 6), U(4, 1, 18)
    b.fix(101, U(4, 1, 5, 40), *OUT_W)
    b.fix(101, U(4, 1, 6, 0), *IN_1)
    b.fix(101, U(4, 1, 6, 20), *IN_2)
    b.fix(101, U(4, 1, 6, 40), *IN_3)
    b.fix(101, U(4, 1, 7, 0), *OUT_W)

    # ---------------- S02 同船多次往返（3 次访问）-------------------------
    b.ship(102, "SAMPLE ROUND TRIP", "油轮")
    s02_start, s02_end = U(4, 4, 6), U(4, 4, 18)
    b.fix(102, U(4, 4, 5, 50), *OUT_W)
    b.fix(102, U(4, 4, 6, 0), *IN_1)
    b.fix(102, U(4, 4, 6, 10), *IN_2)
    b.fix(102, U(4, 4, 6, 20), *OUT_W)
    b.fix(102, U(4, 4, 6, 40), *IN_1)
    b.fix(102, U(4, 4, 6, 50), *IN_2)
    b.fix(102, U(4, 4, 7, 0), *OUT_W)
    b.fix(102, U(4, 4, 7, 30), *OUT_W)
    b.fix(102, U(4, 4, 8, 0), *IN_1)
    b.fix(102, U(4, 4, 8, 30), *IN_3)
    b.fix(102, U(4, 4, 9, 0), *OUT_W)

    # ---------------- S03 两端均区外，不做插值（§2.2.7）-------------------
    b.ship(103, "SAMPLE NO INTERP", "货船")
    s03_start, s03_end = U(4, 7, 6), U(4, 7, 18)
    b.fix(103, U(4, 7, 6, 0), 26.400, 55.700)      # 矩形西侧外
    b.fix(103, U(4, 7, 8, 0), 26.400, 57.120)      # 矩形东侧外（中点穿越不插值）

    # ---------------- S04 边界点：半开规则（§1.1）-------------------------
    b.ship(104, "SAMPLE WEST EDGE", "油轮")
    b.ship(105, "SAMPLE SOUTH EDGE", "货船")
    b.ship(106, "SAMPLE EAST EDGE", "油轮")
    b.ship(107, "SAMPLE NORTH EDGE", None)
    s04_start, s04_end = U(4, 10, 6), U(4, 10, 18)
    # 104: lon = west 正好 -> 区内（西含）
    b.fix(104, U(4, 10, 6, 0), 26.400, 55.770)
    b.fix(104, U(4, 10, 6, 30), 26.400, 55.800)
    b.fix(104, U(4, 10, 7, 0), 26.400, 55.830)
    b.fix(104, U(4, 10, 7, 30), 26.400, 55.800)
    b.fix(104, U(4, 10, 8, 0), 26.400, 55.770)
    # 105: lat = south 正好 -> 区内（南含）
    b.fix(105, U(4, 10, 5, 30), 25.770, 56.400)
    b.fix(105, U(4, 10, 6, 0), 25.800, 56.400)
    b.fix(105, U(4, 10, 6, 30), 26.000, 56.400)
    b.fix(105, U(4, 10, 7, 0), 26.100, 56.400)
    b.fix(105, U(4, 10, 7, 30), 27.100, 56.400)     # lat = north 正好 -> 区外（北不含）
    # 106: lon = east 正好 -> 区外（东不含）
    b.fix(106, U(4, 10, 6, 0), *OUT_E)
    b.fix(106, U(4, 10, 6, 15), 26.400, 57.090)
    b.fix(106, U(4, 10, 6, 30), 26.400, 57.100)
    # 107: lat = north 正好 -> 区外（北不含）
    b.fix(107, U(4, 10, 6, 0), *OUT_N)
    b.fix(107, U(4, 10, 6, 15), 27.080, 56.400)
    b.fix(107, U(4, 10, 6, 30), 27.100, 56.400)

    # ---------------- S05 边界抖动（§2.3 末段 near_boundary）--------------
    b.ship(108, "SAMPLE JITTER", "未知")
    s05_start, s05_end = U(4, 13, 6), U(4, 13, 18)
    b.fix(108, U(4, 13, 6, 10), 26.400, 57.102)
    b.fix(108, U(4, 13, 6, 20), 26.400, 57.098)
    b.fix(108, U(4, 13, 6, 30), 26.400, 57.102)
    b.fix(108, U(4, 13, 6, 40), 26.400, 57.098)
    b.fix(108, U(4, 13, 6, 50), 26.400, 57.102)
    b.fix(108, U(4, 13, 7, 0), 26.400, 57.098)
    b.fix(108, U(4, 13, 7, 10), 26.400, 57.090)
    b.fix(108, U(4, 13, 7, 20), 26.400, 57.102)

    # ---------------- S06 窗口开始前已在区内（§2.2.5）---------------------
    b.ship(109, "SAMPLE STARTED BEFORE", "货船")
    s06_start, s06_end = U(4, 16, 6), U(4, 16, 18)
    _seq(b, 109, U(4, 16, 4, 0), U(4, 16, 7, 0), 20, 26.400, 55.900, dlat=0.001)
    b.fix(109, U(4, 16, 7, 20), *OUT_W)

    # ---------------- S07 窗口结束后仍在区内（§2.2.6）---------------------
    b.ship(110, "SAMPLE ONGOING A", "油轮")
    b.ship(111, "SAMPLE ONGOING B", "货船")
    s07_start, s07_end = U(4, 19, 6), U(4, 19, 18)
    b.fix(110, U(4, 19, 5, 40), *OUT_W)
    _seq(b, 110, U(4, 19, 6, 0), U(4, 19, 7, 0), 20, 26.400, 55.900)
    b.fix(111, U(4, 19, 16, 30), *OUT_W)
    _seq(b, 111, U(4, 19, 17, 0), U(4, 19, 18, 40), 20, 26.400, 55.900)

    # ---------------- S08 前置状态未知（§2.2.3 lookback 内无更早报位）-----
    b.ship(112, "SAMPLE UNKNOWN PRIOR", "油轮")
    s08_start, s08_end = U(4, 22, 6), U(4, 22, 18)
    b.fix(112, U(4, 22, 6, 30), *IN_1)
    b.fix(112, U(4, 22, 7, 0), *IN_2)
    b.fix(112, U(4, 22, 7, 30), *OUT_W)

    # ---------------- S09 长缺报中断（§2.3 行 3）--------------------------
    b.ship(113, "SAMPLE GAP", "货船")
    s09_start, s09_end = U(4, 25, 6), U(4, 25, 18)
    b.fix(113, U(4, 25, 5, 30), *OUT_W)
    b.fix(113, U(4, 25, 6, 0), 26.400, 55.900)
    b.fix(113, U(4, 25, 6, 10), 26.400, 55.950)
    b.fix(113, U(4, 25, 7, 30), 26.400, 55.980)  # 距上一条 4800 s > gap 1800 s
    b.fix(113, U(4, 25, 7, 40), 26.400, 56.000)
    b.fix(113, U(4, 25, 8, 0), *OUT_W)

    # ---------------- S10 跳点（§2.3 行 4）--------------------------------
    b.ship(114, "SAMPLE JUMP", "油轮")
    s10_start, s10_end = U(4, 28, 6), U(4, 28, 18)
    b.fix(114, U(4, 28, 5, 30), *OUT_W)
    b.fix(114, U(4, 28, 6, 0), 26.400, 55.900)
    b.fix(114, U(4, 28, 6, 10), 26.405, 55.910)
    b.fix(114, U(4, 28, 6, 20), 26.900, 56.900)  # 10 min 内约 113 km -> 约 365 kn
    b.fix(114, U(4, 28, 6, 30), 26.905, 56.910)
    b.fix(114, U(4, 28, 7, 0), *OUT_E)

    # ---------------- S20 跳点回归：位移 < 1 km 但推算航速 > 30 kn ----------
    # 200 m / 5 s ≈ 78 kn（位移 0.20 km < jump_min_distance_km=1.0）：
    # 两个阈值必须同时满足才算跳点（§2.3 行 4），该区间必须计入停留时长，
    # 访问不得出现 jump_break。与 S10（≥1 km 大位移）互为对照。
    b.ship(120, "SAMPLE FAST SMALL STEP", "油轮")
    s20_start, s20_end = U(5, 25, 6), U(5, 25, 18)
    b.fix(120, U(5, 25, 5, 45), *OUT_W)                # 进入括号 900 s（非宽括号）
    b.fix(120, U(5, 25, 6, 0, 0), 26.400, 55.900)      # 区内首点
    b.fix(120, U(5, 25, 6, 0, 5), 26.4018, 55.900)     # 5 s 后北移约 200 m -> 约 78 kn
    b.fix(120, U(5, 25, 6, 30, 0), 26.420, 55.950)     # 1795 s / 约 5.4 km -> 约 5.8 kn
    b.fix(120, U(5, 25, 6, 55), *OUT_W)                # 离开括号 1500 s（非宽括号）

    # ---------------- S11 同秒冲突（§2.3 末条 + §2.0 稳定排序）------------
    b.ship(115, "SAMPLE SAME SECOND", "油轮")
    s11_start, s11_end = U(5, 1, 6), U(5, 1, 18)
    b.fix(115, U(5, 1, 6, 0), *OUT_W)                  # id 小（区外）
    b.fix(115, U(5, 1, 6, 0), *IN_1)                   # 同秒、id 更大 -> 进入侧冲突
    b.fix(115, U(5, 1, 6, 10), 26.400, 55.950)
    b.fix(115, U(5, 1, 6, 20), 26.400, 56.000)         # 区内，id 较小
    b.fix(115, U(5, 1, 6, 20), *OUT_E)                 # 同秒、id 更大 -> 离开侧冲突

    # ---------------- S12 跨自然日裁剪（§2.4 按日交集）--------------------
    b.ship(116, "SAMPLE CROSS DAY", "货船")
    s12_start, s12_end = U(5, 10, 22), U(5, 11, 4)
    b.fix(116, U(5, 10, 21, 30), *OUT_W)
    _seq(b, 116, U(5, 10, 22, 30), U(5, 11, 1, 30), 30, 26.400, 55.900, dlon=0.005)
    b.fix(116, U(5, 11, 3, 30), *OUT_W)

    # ---------------- S13 窗口裁剪：进入发生在 start 之前（§2.4 交集）-----
    b.ship(117, "SAMPLE CLIP ENTRY", "油轮")
    s13_start, s13_end = U(5, 14, 6), U(5, 14, 18)
    b.fix(117, U(5, 14, 4, 40), *OUT_W)
    _seq(b, 117, U(5, 14, 5, 0), U(5, 14, 7, 0), 20, 26.400, 55.900, dlon=0.002)
    b.fix(117, U(5, 14, 7, 20), *OUT_W)

    # ---------------- S14 窗口两端都裁剪 ----------------------------------
    b.ship(118, "SAMPLE CLIP BOTH", "货船")
    s14_start, s14_end = U(5, 17, 6), U(5, 17, 18)
    # 05:00–19:00，30 min 间隔（正好等于 gap_seconds，属于「连续观测」）
    _seq(b, 118, U(5, 17, 5, 0), U(5, 17, 19, 0), 30, 26.400, 55.900, dlat=0.002)

    # ---------------- S15 left_returned 探针（§2.2.2 与 §2.3 行 2 的交界）-
    b.ship(119, "SAMPLE LEFT RETURNED", "油轮")
    s15_start, s15_end = U(5, 20, 6), U(5, 20, 18)
    b.fix(119, U(5, 20, 5, 30), *OUT_W)
    b.fix(119, U(5, 20, 6, 0), *IN_1)
    b.fix(119, U(5, 20, 6, 10), *IN_2)
    b.fix(119, U(5, 20, 7, 0), 24.000, 52.000)   # context_bbox 之外，scope 不读取
    b.fix(119, U(5, 20, 8, 0), *IN_1)
    b.fix(119, U(5, 20, 8, 10), *IN_2)
    b.fix(119, U(5, 20, 9, 0), *OUT_W)

    # ---------------- S16 no_data（scope 内没有任何报位）------------------
    s16_start, s16_end = U(6, 2, 6), U(6, 2, 18)

    # ---------------- S17 快照混合（§2.1）---------------------------------
    b.ship(201, "SNAP FRESH IN", "油轮")
    b.ship(202, "SNAP FRESH OUT", "货船")
    b.ship(203, "SNAP STALE", "油轮")
    b.ship(204, "SNAP FRESH OUT OLDER IN", "货船")
    b.ship(205, "SNAP STALE WITH OLDER IN", "油轮")
    b.ship(206, "SNAP ONLY AFTER", "货船")
    b.ship(207, "SNAP EXACT AT", "油轮")
    b.ship(208, "SNAP FOREIGN SOURCE", "货船")
    snap_at = U(6, 20, 12)
    b.fix(201, U(6, 20, 11, 50), *IN_1)
    b.fix(202, U(6, 20, 11, 50), *OUT_W)
    b.fix(203, U(6, 20, 10, 50), *IN_1)
    b.fix(204, U(6, 20, 11, 0), *IN_2)
    b.fix(204, U(6, 20, 11, 50), *OUT_W)
    b.fix(205, U(6, 20, 10, 0), *IN_3)
    b.fix(205, U(6, 20, 9, 0), *IN_2)
    b.fix(206, U(6, 20, 12, 30), *IN_1)
    b.fix(207, U(6, 20, 12, 0), *IN_2)
    b.fix(208, U(6, 20, 11, 55), *IN_1, data_source="legacy_source")

    # ---------------- S18/S19 A/B 比较（§2.5）-----------------------------
    b.ship(301, "COMPARE A", "油轮")
    b.ship(302, "COMPARE B1", "油轮")
    b.ship(303, "COMPARE B2", "货船")
    b.ship(304, "COMPARE ZERO BASE", "油轮")
    cmp1_a = (U(6, 5, 6), U(6, 5, 18))
    cmp1_b = (U(6, 8, 0), U(6, 9, 0))
    cmp0_a = (U(6, 11, 6), U(6, 11, 18))
    cmp0_b = (U(6, 14, 6), U(6, 14, 18))
    for sid, day in ((301, 5), (302, 8), (303, 8), (304, 14)):
        base_hour = 6 if day in (5, 14) else (6 if sid == 302 else 11)
        b.fix(sid, U(6, day, base_hour - 1, 30), *OUT_W)
        b.fix(sid, U(6, day, base_hour, 0), *IN_1)
        b.fix(sid, U(6, day, base_hour, 30), *IN_2)
        b.fix(sid, U(6, day, base_hour + 1, 0), *OUT_W)

    # ---------------- S21 批次范围一致性（§2.0 scope/探测/覆盖 三者同批次）-----
    # 同一艘船、同一段窗口里混入两个来源批次 9001 / 9002：
    #   * 06:10 -> 06:35 两条区内报位间隔 1500 s（> 480 s 且 < 1800 s，两端位移很小）；
    #   * 唯一夹在中间的报位 06:25 属于 9002，且远在 context_bbox 之外（24.0/52.0），
    #     所以它一定不在观测上下文的状态序列里，只能靠越界探测发现；
    #   * 另有 05:00 一条 9002 的区外报位（在外扩带内），用于区分「按批次筛过的扫描量」
    #     与「不筛批次的扫描量」（6 vs 7）。
    b.ship(121, "SAMPLE BATCH SCOPE", "油轮")
    s21_start, s21_end = U(7, 20, 6), U(7, 20, 18)
    b.fix(121, U(7, 20, 5, 0), *OUT_W, source_batch_id=9002)          # 9002，外扩带内、矩形外
    b.fix(121, U(7, 20, 5, 40), *OUT_W)                               # 9001
    b.fix(121, U(7, 20, 6, 0), *IN_1)                                 # 9001 区内
    b.fix(121, U(7, 20, 6, 10), *IN_2)                                # 9001 区内
    b.fix(121, U(7, 20, 6, 25), 24.000, 52.000, source_batch_id=9002)  # 9002，context 之外
    b.fix(121, U(7, 20, 6, 35), *IN_2)                                # 9001 区内（与 06:10 相隔 1500 s）
    b.fix(121, U(7, 20, 6, 50), *IN_3)                                # 9001 区内
    b.fix(121, U(7, 20, 7, 10), *OUT_W)                               # 9001 区外（离开括号 1200 s）

    # ---------------- S22 短时外出（用户场景，§2.0 v1.0.1 / §2.3 行 2）---------
    # 船在区内；10 min 后出现在外扩带之外（距矩形南边 0.5°，位置绝对值不重要，
    # 只要求它不在 context_bbox 内）；20 min 后回到区内相近位置。
    # 两条区内报位间隔 1200 s：< gap_seconds(1800) 且两端位移约 5.4 km（约 8.8 kn），
    # 不满足跳点条件 —— v1.0.0 会把它当连续停留，v1.0.1 因 1200 > 480 s 必须探测并拆分。
    b.ship(122, "SAMPLE SHORT EXCURSION", "油轮")
    s22_start, s22_end = U(7, 21, 6), U(7, 21, 18)
    b.fix(122, U(7, 21, 5, 40), *OUT_W)                            # 进入括号 1200 s（非宽括号）
    b.fix(122, U(7, 21, 6, 0), *IN_1)                              # 区内
    s22_outside = b.fix(122, U(7, 21, 6, 10), 25.300, 56.400)      # 外扩带之外（context 之外）
    b.fix(122, U(7, 21, 6, 20), *IN_2)                             # 回到区内相近位置
    b.fix(122, U(7, 21, 6, 50), *OUT_W)                            # 离开括号 1800 s（非宽括号）
    s22_removed_ids = [s22_outside.id]  # 负向对照要删掉的那条区外中间报位

    scenarios = [
        Scenario(
            name="S01_enter_exit",
            title="正常进入 + 离开",
            doc_ref="§2.2.3/§2.2.4/§2.4",
            start=s01_start,
            end=s01_end,
            ship_ids=[101],
            use_default_area=True,
            covers=["enter_exit"],
            notes="默认区域（不传矩形），用于核对 area_id=hormuz_core_v1 与 is_default=true",
        ),
        Scenario(
            name="S02_multi_round_trip",
            title="同船多次往返（3 次访问）",
            doc_ref="§2.2.2",
            start=s02_start,
            end=s02_end,
            ship_ids=[102],
            covers=["multi_round_trip"],
            filter_checks=[{"ship_type": ["油轮"], "note": "同一船型精确匹配"}],
        ),
        Scenario(
            name="S03_both_outside_no_interp",
            title="两端均区外，不做插值（有效零结果）",
            doc_ref="§2.2.7/§2.6",
            start=s03_start,
            end=s03_end,
            ship_ids=[103],
            use_default_area=True,
            covers=["both_outside_no_interp", "valid_zero"],
            notes="scope 内有报位但区域内无船 -> status 应为 ok + 零结果，不是 no_data",
        ),
        Scenario(
            name="S04_boundary_half_open",
            title="边界点：west/south 含，east/north 不含",
            doc_ref="§1.1",
            start=s04_start,
            end=s04_end,
            ship_ids=[104, 105, 106, 107],
            covers=["boundary_half_open"],
            filter_checks=[
                {"ship_type": ["油轮"], "note": "精确匹配（104/106）"},
                {"ship_type": ["__missing__"], "note": "NULL 船型（107）"},
                {"ship_type": ["__unknown__"], "note": "无「未知」船型 -> 有效零结果（软）", "soft": True},
            ],
        ),
        Scenario(
            name="S05_boundary_jitter",
            title="边界抖动（不做缓冲/滞回）",
            doc_ref="§2.3 末段",
            start=s05_start,
            end=s05_end,
            ship_ids=[108],
            covers=["boundary_jitter"],
            filter_checks=[{"ship_type": ["__unknown__"], "note": "保留值 __unknown__ = 未知（108）"}],
        ),
        Scenario(
            name="S06_started_before_window",
            title="窗口开始前已在区内（lookback 内全是区内点）",
            doc_ref="§2.2.5",
            start=s06_start,
            end=s06_end,
            ship_ids=[109],
            covers=["started_before_window", "window_clip"],
        ),
        Scenario(
            name="S07_ongoing_after_window",
            title="窗口结束后仍在区内（无更晚报位 / 更晚报位仍在内）",
            doc_ref="§2.2.6",
            start=s07_start,
            end=s07_end,
            ship_ids=[110, 111],
            covers=["ongoing_after_window", "window_clip"],
        ),
        Scenario(
            name="S08_prior_state_unknown",
            title="前置状态未知（lookback 内无更早报位，首点晚于 start）",
            doc_ref="§2.2.3",
            start=s08_start,
            end=s08_end,
            ship_ids=[112],
            covers=["prior_state_unknown"],
        ),
        Scenario(
            name="S09_long_gap_interrupted",
            title="长缺报中断（不拆分、不累计）",
            doc_ref="§2.3 行 3",
            start=s09_start,
            end=s09_end,
            ship_ids=[113],
            covers=["gap_interrupt"],
        ),
        Scenario(
            name="S10_jump_spike",
            title="跳点（位移 ≥1 km 且推算速度 >30 kn，两个阈值同时满足）",
            doc_ref="§2.3 行 4",
            start=s10_start,
            end=s10_end,
            ship_ids=[114],
            covers=["jump"],
            notes="10 min 内约 113 km -> 约 365 kn，位移与速度都超阈值 -> jump_break",
        ),
        Scenario(
            name="S20_fast_small_step_not_jump",
            title="跳点回归：位移 <1 km 但推算速度 >30 kn（不得判 jump）",
            doc_ref="§2.3 行 4 / §3 jump_min_distance_km=1.0",
            start=s20_start,
            end=s20_end,
            ship_ids=[120],
            covers=["jump_min_distance"],
            notes="200 m / 5 s ≈ 78 kn：位移 0.20 km 未达 jump_min_distance_km=1.0，"
            "该区间必须计入停留时长，flags 不得出现 jump_break",
        ),
        Scenario(
            name="S11_same_second_conflict",
            title="同秒冲突（按 id 稳定排序，区间长度 0）",
            doc_ref="§2.3 末条",
            start=s11_start,
            end=s11_end,
            ship_ids=[115],
            covers=["same_second_conflict"],
        ),
        Scenario(
            name="S12_cross_day_clip",
            title="跨自然日裁剪（22:00Z–04:00Z）",
            doc_ref="§2.4 按日交集",
            start=s12_start,
            end=s12_end,
            ship_ids=[116],
            covers=["cross_day_clip"],
        ),
        Scenario(
            name="S13_clip_entry_before_start",
            title="窗口裁剪：观测进入发生在 start 之前",
            doc_ref="§2.4 窗口裁剪",
            start=s13_start,
            end=s13_end,
            ship_ids=[117],
            covers=["window_clip"],
        ),
        Scenario(
            name="S14_clip_both_sides",
            title="窗口两端都裁剪（窗前已在区内 + 窗后仍在区内）",
            doc_ref="§2.2.5/§2.2.6/§2.4",
            start=s14_start,
            end=s14_end,
            ship_ids=[118],
            covers=["window_clip", "started_before_window", "ongoing_after_window"],
        ),
        Scenario(
            name="S15_left_returned_probe",
            title="left_returned 探针：两条区内报位之间存在同船区外报位（context 之外）",
            doc_ref="§2.0 有界越界探测 / §2.3 行 2",
            start=s15_start,
            end=s15_end,
            ship_ids=[119],
            covers=["left_returned_probe", "gap_interrupt"],
            notes="06:10 -> 08:00 间隔 6600 s > gap_seconds，属可疑对；越界探测在该区间内发现"
            "07:00 的区外报位（在 context_bbox 之外）-> 拆成两次访问，两侧事件 wide_bracket "
            "且 outside_evidence_out_of_context。§2.0 定版后按硬断言比对",
        ),
        Scenario(
            name="S16_no_data",
            title="no_data：scope 内没有任何可判定报位",
            doc_ref="§2.6",
            start=s16_start,
            end=s16_end,
            ship_ids=[],
            covers=["no_data"],
        ),
        Scenario(
            name="S21_batch_scope_consistency",
            title="批次范围一致性：scope / 越界探测 / coverage 都只看 batch_ids=[9001]",
            doc_ref="§2.0（观测上下文）/§2.3 行 2/§3 batch_ids/§4.3 coverage.batch_ids",
            start=s21_start,
            end=s21_end,
            ship_ids=[121],
            batch_ids=[9001],
            covers=["batch_scope_consistency"],
            notes="主请求 batch_ids=[9001]：06:10->06:35（1500 s）之间只有 9002 的区外报位，"
            "按批次探测不到 -> 不拆分（1 次访问、3000 s）；filter 请求分别验证不带批次"
            "（拆成两次访问，进入/离开各多 1 次）、油轮+9002（范围内只剩 1 条区外报位 -> 有效零结果）"
            "与货船+9001（船型与批次同时生效 -> no_data）",
            filter_checks=[
                {
                    "ship_type": None,
                    "batch_ids": None,
                    "note": "不带 batch_ids：9002 的中间报位成为越界证据 -> left_returned 两次访问",
                },
                {
                    "ship_type": ["油轮"],
                    "batch_ids": [9001, 9002],
                    "note": "显式列出两个批次：与不带批次等价（两次访问），coverage 回显 [9001, 9002]",
                },
                {
                    "ship_type": ["油轮"],
                    "batch_ids": [9002],
                    "note": "批次与船型可组合：9002 在范围内只有 1 条区外报位 -> 有效零结果（非 no_data）",
                },
                {
                    "ship_type": ["货船"],
                    "batch_ids": [9001],
                    "note": "批次与船型同时生效：该窗口内没有货船报位 -> no_data",
                },
            ],
        ),
        Scenario(
            name="S22_short_excursion",
            title="短时外出：间隔 1200 s（<gap 但 >480 s）驶出外扩带再返回",
            doc_ref="§2.0 有界越界探测（v1.0.1）/§2.3 行 2/§2.4",
            start=s22_start,
            end=s22_end,
            ship_ids=[122],
            covers=["short_excursion_probe"],
            notes="两条区内报位 06:00/06:20 间隔 1200 s、位移约 5.4 km（约 8.8 kn，不构成跳点）；"
            "06:10 的报位在 context_bbox 之外，只有越界探测能看到 -> 拆成两次访问，"
            "两侧事件标 outside_evidence_out_of_context，外出的 1200 s 不计入时长（observed_seconds=0）；"
            "removal_probe 删掉该报位后必须回到 1 次访问且该区间计入时长（无证据不拆分）",
            removal_probe={
                "fix_ids": s22_removed_ids,
                "note": "删掉区外中间报位后：无越界证据 -> 一次访问，1200 s 计入停留时长"
                        "（§2.3 行 1 / §2.0 残余限制：采样漏检）",
            },
        ),
    ]

    snapshots = [
        SnapshotScenario(
            name="S17_snapshot_mix",
            title="时刻在场：新鲜/过期/区外/无更早回退/仅 at 之后有报位",
            at=snap_at,
            ship_ids=[201, 202, 203, 204, 205, 206, 207, 208],
            covers=["snapshot_freshness"],
            notes="208 使用 data_source != nnu_ais，用于探测来源硬过滤（软比对）",
        ),
        SnapshotScenario(
            name="S17b_snapshot_freshness_override",
            title="同上，freshness_seconds=7200 覆盖默认值",
            at=snap_at,
            ship_ids=[201, 202, 203, 204, 205, 206, 207, 208],
            freshness_seconds=7200,
            covers=["snapshot_freshness"],
        ),
    ]

    compares = [
        CompareScenario(
            name="S18_compare_unequal_windows",
            title="A/B 不等长窗口（12 h vs 24 h）",
            start_a=cmp1_a[0],
            end_a=cmp1_a[1],
            start_b=cmp1_b[0],
            end_b=cmp1_b[1],
            ship_ids=[301, 302, 303],
            covers=["compare_ab"],
        ),
        CompareScenario(
            name="S19_compare_zero_base",
            title="A/B 零基期（A 无观测 -> change_rate 必须为 null）",
            start_a=cmp0_a[0],
            end_a=cmp0_a[1],
            start_b=cmp0_b[0],
            end_b=cmp0_b[1],
            ship_ids=[304],
            covers=["compare_ab", "no_data"],
        ),
    ]

    validations = [
        ValidationCase("V01_west_ge_east", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "57.1"), ("south", "25.8"), ("east", "55.8"), ("north", "27.1")],
                       422, "§1.3"),
        ValidationCase("V02_south_ge_north", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "55.8"), ("south", "27.1"), ("east", "57.1"), ("north", "25.8")],
                       422, "§1.3"),
        ValidationCase("V03_partial_rect", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "55.8"), ("south", "25.8")],
                       422, "§1.3 四边同时给出或同时省略"),
        ValidationCase("V04_lat_span_over", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "55.8"), ("south", "20.0"), ("east", "57.1"), ("north", "31.0")],
                       422, "§1.3 lat_span<=10"),
        ValidationCase("V05_lon_span_over", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "50.0"), ("south", "25.0"), ("east", "61.0"), ("north", "26.0")],
                       422, "§1.3 lon_span<=10"),
        ValidationCase("V06_lon_out_of_range", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "-181"), ("south", "25.8"), ("east", "57.1"), ("north", "27.1")],
                       422, "§1.3 [-180,180]"),
        ValidationCase("V07_cross_180", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("west", "170"), ("south", "25.8"), ("east", "-170"), ("north", "27.1")],
                       422, "§1.3 跨 180° 直接拒绝"),
        ValidationCase("V08_window_too_long", "activity",
                       [("start", _iso(U(6, 1, 0))), ("end", _iso(U(6, 9, 0)))],
                       422, "§1.3 end-start<=7 天"),
        ValidationCase("V09_start_ge_end", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_start))],
                       422, "§1.3 start<end"),
        ValidationCase("V10_missing_time", "activity",
                       [("west", "55.8"), ("south", "25.8"), ("east", "57.1"), ("north", "27.1")],
                       422, "§4.3 start/end 必填"),
        ValidationCase("V11_naive_datetime", "activity",
                       [("start", "2026-04-01T06:00:00"), ("end", _iso(s01_end))],
                       422, "§1.3 时间必须带显式时区"),
        ValidationCase("V12_lookback_over_limit", "activity",
                       [("start", _iso(s01_start)), ("end", _iso(s01_end)),
                        ("state_lookback_seconds", "90000")],
                       422, "§4.3 state_lookback_seconds 0–86400"),
        ValidationCase("V13_visit_limit_over_max", "activity",
                       [("start", _iso(s04_start)), ("end", _iso(s04_end)), ("visit_limit", "5000")],
                       422, "§4.3 visit_limit 最大 2000", soft=True),
        ValidationCase("V14_snapshot_missing_at", "snapshot", [], 422, "§4.2 at 必填"),
        ValidationCase("V15_snapshot_limit_over_max", "snapshot",
                       [("at", _iso(snap_at)), ("limit", "6000")],
                       422, "§4.2 limit 最大 5000", soft=True),
        ValidationCase("V16_window_exactly_7_days", "activity",
                       [("start", _iso(U(7, 1, 0))), ("end", _iso(U(7, 8, 0)))],
                       200, "§1.3 上限 + 边界包含（7 天整应通过，且该区间没有任何样例报位 -> no_data）"),
        ValidationCase("V17_compare_missing_window", "compare",
                       [("start_a", _iso(cmp1_a[0])), ("end_a", _iso(cmp1_a[1]))],
                       422, "§4.4 四个时间参数必填"),
    ]

    return {
        "ships": b.ships,
        "fixes": b.fixes,
        "scenarios": scenarios,
        "snapshots": snapshots,
        "compares": compares,
        "validations": validations,
        "snapshot_at": snap_at,
    }


# ==========================================================================
# 期望值计算（对全量样例数据计算，与接口看到的行集一致）
# ==========================================================================
# ==========================================================================
# 模块级导出：供验证脚本插入测试库使用
# ==========================================================================
_BOOTSTRAP = build_registry()
ALL_SHIPS: list[Ship] = _BOOTSTRAP["ships"]
ALL_FIXES: list[Fix] = _BOOTSTRAP["fixes"]
ALL_SNAPSHOT_AT: datetime = _BOOTSTRAP["snapshot_at"]


def sample_registry() -> dict[str, Any]:
    """构造注册表并计算期望值（每次调用返回独立对象；id 与时间完全确定）。"""
    registry = build_registry()
    compute_expectations(registry)
    return registry


def _expected_bundle(analysis: dict[str, Any], batch_ids: Sequence[int] | None) -> dict[str, Any]:
    """朴素复算结果 → 期望值（含 §4.3 coverage.batch_ids 与 limits.scanned_fix_count）。"""
    return {
        "summary": analysis["summary"],
        "daily": {row["date"]: row for row in analysis["daily"]},
        "daily_order": [row["date"] for row in analysis["daily"]],
        "visits": {v["visit_key"]: v for v in analysis["visits"]},
        "status_hint": analysis["status_hint"],
        "ambiguities": analysis["ambiguities"],
        # §4.3：批次条件同时作用于统计、上下文与越界探测；coverage.batch_ids 回显实际生效批次。
        "coverage_batch_ids": _coverage_batch_ids(batch_ids),
        # §2.0 scope = [start-lookback, end+lookahead) ∩ context_bbox ∩ 来源 ∩ 批次（∩ 船型）。
        "scanned_fix_count": analysis["scope_fix_count"],
    }


def compute_expectations(registry: dict[str, Any]) -> None:
    ships = registry["ships"]
    fixes = registry["fixes"]

    for sc in registry["scenarios"]:
        analysis = naive_analyze(
            ships, fixes, sc.rect, sc.start, sc.end, sc.params, sc.ship_types, sc.batch_ids
        )
        sc.expected = _expected_bundle(analysis, sc.batch_ids)
        if "left_returned_probe" in sc.covers:
            # §2.0 定版后该场景是硬断言：两条区内报位之间的区外报位（在 context_bbox 之外）
            # 经越界探测证明后把访问切成两次，两侧事件都算 wide_bracket 并标
            # outside_evidence_out_of_context；预期值已由 _inside_blocks 直接算出。
            sc.notes = (
                sc.notes + " / " if sc.notes else ""
            ) + "§2.0 定版：越界探测命中 -> left_returned 两次访问（硬断言）"
        sc.filter_checks = list(sc.filter_checks)
        for check in sc.filter_checks:
            check_batches = check.get("batch_ids", sc.batch_ids)
            sub = naive_analyze(
                ships, fixes, sc.rect, sc.start, sc.end, sc.params,
                check.get("ship_type"), check_batches,
            )
            check["expected"] = _expected_bundle(sub, check_batches)
        if sc.removal_probe is not None:
            removed = set(sc.removal_probe["fix_ids"])
            remaining = [f for f in fixes if f.id not in removed]
            after = naive_analyze(
                ships, remaining, sc.rect, sc.start, sc.end, sc.params, sc.ship_types, sc.batch_ids
            )
            sc.removal_probe["expected"] = _expected_bundle(after, sc.batch_ids)
            sc.removal_probe["removed_fix_count"] = len(removed)
            sc.removal_probe["remaining_fix_count"] = len(remaining)

    for snap in registry["snapshots"]:
        snap.expected = naive_snapshot(
            ships, fixes, snap.rect, snap.at,
            snap.freshness_seconds if snap.freshness_seconds is not None else DEFAULT_PARAMS["freshness_seconds"],
        )

    for cmp_ in registry["compares"]:
        a = naive_analyze(ships, fixes, cmp_.rect, cmp_.start_a, cmp_.end_a)
        b_ = naive_analyze(ships, fixes, cmp_.rect, cmp_.start_b, cmp_.end_b)
        # §2.5 定版：window_days = 窗口覆盖的 UTC 自然日个数（daily 分桶用），
        #            window_length_days = 窗口实际长度（含小数天，日均分母），
        #            equal_length 比较实际长度（12 h 与 24 h 判为不等长）。
        days_a = len(_days_covered(cmp_.start_a, cmp_.end_a))
        days_b = len(_days_covered(cmp_.start_b, cmp_.end_b))
        length_a = (cmp_.end_a - cmp_.start_a).total_seconds() / 86400.0
        length_b = (cmp_.end_b - cmp_.start_b).total_seconds() / 86400.0
        metrics: dict[str, dict[str, Any]] = {}
        for key, label in (
            ("ships_observed", "ships_observed"),
            ("observed_entry_count", "observed_entry_count"),
            ("observed_exit_count", "observed_exit_count"),
            ("observed_ship_hours", "observed_ship_hours"),
        ):
            va = float(a["summary"][key])
            vb = float(b_["summary"][key])
            metrics[label] = {
                "a": va,
                "b": vb,
                "delta": vb - va,
                "change_rate": None if va == 0 else (vb - va) / va,
                "daily_mean_a": va / length_a if length_a else None,
                "daily_mean_b": vb / length_b if length_b else None,
            }
        # 日均指标：分母 = 窗口实际长度，不是自然日个数（§2.5）
        for key, source in (
            ("ships_observed_per_day", "ships_observed"),
            ("observed_entry_count_per_day", "observed_entry_count"),
            ("observed_ship_hours_per_day", "observed_ship_hours"),
        ):
            va = float(a["summary"][source]) / length_a if length_a else 0.0
            vb = float(b_["summary"][source]) / length_b if length_b else 0.0
            metrics[key] = {
                "a": va,
                "b": vb,
                "delta": vb - va,
                "change_rate": None if va == 0 else (vb - va) / va,
            }
        cmp_.expected = {
            "a": a["summary"],
            "b": b_["summary"],
            "window_days_a": days_a,
            "window_days_b": days_b,
            "window_length_days_a": length_a,
            "window_length_days_b": length_b,
            "equal_length": length_a == length_b,
            "metrics": metrics,
            "status_a": a["status_hint"],
            "status_b": b_["status_hint"],
            # §2.5 定版后，比较口径（自然日 vs 实际长度、等长判定、日均分母）均已确定，
            # 不再保留备选口径。
            "ambiguities": {},
        }


# ==========================================================================
# self-check：内存内自洽性检查（单位、半开规则、裁剪恒等式、覆盖度）
# ==========================================================================
REQUIRED_COVERAGE = {
    "enter_exit": "正常进入 + 离开",
    "multi_round_trip": "同船多次往返",
    "both_outside_no_interp": "两端均区外（不做插值）",
    "boundary_half_open": "边界点（半开规则：west/south 含，east/north 不含）",
    "boundary_jitter": "边界抖动",
    "started_before_window": "窗口开始前已在区内",
    "ongoing_after_window": "窗口结束后仍在区内",
    "prior_state_unknown": "前置状态未知",
    "gap_interrupt": "长缺报中断",
    "jump": "跳点",
    "jump_min_distance": "跳点最小位移（<1 km 高航速不判 jump）",
    "same_second_conflict": "同秒冲突",
    "cross_day_clip": "跨自然日裁剪",
    "window_clip": "窗口裁剪",
    "valid_zero": "有效零结果",
    "no_data": "no_data",
    "left_returned_probe": "left_returned 探针",
    "short_excursion_probe": "短时外出探测（间隔 >480 s 且 <gap_seconds）",
    "batch_scope_consistency": "批次范围一致性（scope/探测/覆盖同批次）",
    "snapshot_freshness": "快照新鲜度/过期/无回退",
    "compare_ab": "A/B 比较（含零基期）",
}

# 手算期望值（脱离朴素实现独立写出，用于交叉校验朴素实现本身）
HAND_CHECKED = {
    "S01_enter_exit": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 2400.0},
    "S02_multi_round_trip": {"ships_observed": 1, "entries": 3, "exits": 3, "window_seconds": 3000.0},
    "S03_both_outside_no_interp": {"ships_observed": 0, "entries": 0, "exits": 0, "window_seconds": 0.0},
    "S04_boundary_half_open": {"ships_observed": 4, "entries": 4, "exits": 4, "window_seconds": 7200.0},
    "S05_boundary_jitter": {"ships_observed": 1, "entries": 3, "exits": 3, "window_seconds": 600.0},
    "S06_started_before_window": {"ships_observed": 1, "entries": 0, "exits": 1, "window_seconds": 3600.0},
    "S07_ongoing_after_window": {"ships_observed": 2, "entries": 2, "exits": 0, "window_seconds": 7200.0},
    "S08_prior_state_unknown": {"ships_observed": 1, "entries": 0, "exits": 1, "window_seconds": 1800.0},
    "S09_long_gap_interrupted": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 1200.0},
    "S10_jump_spike": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 1200.0},
    "S11_same_second_conflict": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 1200.0},
    "S12_cross_day_clip": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 10800.0},
    "S13_clip_entry_before_start": {"ships_observed": 1, "entries": 0, "exits": 1, "window_seconds": 3600.0},
    "S14_clip_both_sides": {"ships_observed": 1, "entries": 0, "exits": 0, "window_seconds": 43200.0},
    "S15_left_returned_probe": {"ships_observed": 1, "entries": 2, "exits": 2, "window_seconds": 1200.0},
    "S16_no_data": {"ships_observed": 0, "entries": 0, "exits": 0, "window_seconds": 0.0},
    "S20_fast_small_step_not_jump": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 1800.0},
    # S21（batch_ids=[9001]）：9002 的中间报位不算证据 -> 仍然是一次连续停留 06:00–06:50。
    "S21_batch_scope_consistency": {"ships_observed": 1, "entries": 1, "exits": 1, "window_seconds": 3000.0},
    # S22：06:00/06:20 两条单报位访问（各自 0 长度 segment），外出的 1200 s 不计入时长；
    # 进入/离开各 2 次（相对“无证据”对照各多 1 次，且都落在窗口内）。
    "S22_short_excursion": {"ships_observed": 1, "entries": 2, "exits": 2, "window_seconds": 0.0},
}


def self_check(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """返回 [{"name", "ok", "detail"}]；全部与实现无关，纯内存复算。"""
    results: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        results.append({"name": name, "ok": bool(ok), "detail": detail})

    # 1) haversine 单位
    one_deg_lat = haversine_m(26.0, 56.0, 27.0, 56.0)
    add(
        "haversine_units",
        abs(one_deg_lat - 111195.0) < 600.0,
        f"1° 纬度 = {one_deg_lat:.1f} m（期望约 111.2 km）",
    )
    add(
        "haversine_zero",
        haversine_m(26.4, 56.4, 26.4, 56.4) == 0.0,
        "同一点距离为 0",
    )

    # 2) 节与 km/h 换算
    f1 = Fix(1, 1, U(4, 1, 0), 26.0, 56.0)
    f2 = Fix(2, 1, U(4, 1, 1), 26.0 + 1852.0 / 111195.0, 56.0)
    sp = implied_speed_kn(f1, f2)
    add("knots_unit", abs(sp - 1.0) < 0.02, f"1 海里/小时 -> {sp:.4f} kn")

    # 3) 半开边界
    r = DEFAULT_RECT
    cases = {
        "west 含": inside_rect(26.4, r.west, r),
        "south 含": inside_rect(r.south, 56.4, r),
        "east 不含": not inside_rect(26.4, r.east, r),
        "north 不含": not inside_rect(r.north, 56.4, r),
        "east-1e-9 含": inside_rect(26.4, r.east - 1e-9, r),
        "north-1e-9 含": inside_rect(r.north - 1e-9, 56.4, r),
        "west-1e-9 不含": not inside_rect(26.4, r.west - 1e-9, r),
        "south-1e-9 不含": not inside_rect(r.south - 1e-9, 56.4, r),
    }
    bad = [k for k, v in cases.items() if not v]
    add("half_open_rect", not bad, "全部通过" if not bad else f"失败项：{bad}")

    # 4) 相邻矩形不重不漏
    left = Rect(25.8, 55.8, 27.1, 56.5)
    right = Rect(25.8, 56.5, 27.1, 57.1)
    on_edge = inside_rect(26.4, 56.5, left), inside_rect(26.4, 56.5, right)
    add(
        "adjacent_rects_partition",
        on_edge[0] is False and on_edge[1] is True,
        f"共享边上的点 (26.4,56.5) 命中 left={on_edge[0]}, right={on_edge[1]}",
    )

    # 5) context 外扩
    add(
        "context_margin",
        in_context(26.4, 55.79, r, 0.05) and not in_context(26.4, 55.70, r, 0.05),
        "0.01° 外扩内为 True，0.10° 外为 False",
    )

    # 6) 到边界距离
    d_east_in = distance_to_rect_m(26.4, 57.09, r)
    d_west_edge = distance_to_rect_m(26.4, 55.8, r)
    add(
        "boundary_distance",
        abs(d_west_edge) < 1e-6 and 900.0 < d_east_in < 1100.0,
        f"west 边上的点距离 {d_west_edge:.3f} m；57.09°E 处约 {d_east_in:.1f} m",
    )

    # 7) 场景时间隔离：别的场景报位不得落在本场景 scope（时间 ∩ context_bbox）内
    leaks: list[str] = []
    for sc in registry["scenarios"]:
        scope_start = sc.start - timedelta(seconds=DEFAULT_PARAMS["state_lookback_seconds"])
        scope_end = sc.end + timedelta(seconds=DEFAULT_PARAMS["state_lookahead_seconds"])
        own = set(sc.ship_ids)
        for fx in registry["fixes"]:
            if fx.ship_id in own:
                continue
            if scope_start <= fx.recorded_at < scope_end and in_context(
                fx.latitude, fx.longitude, sc.rect, DEFAULT_PARAMS["context_margin_deg"]
            ):
                leaks.append(f"{sc.name}<-ship{fx.ship_id}@{_iso(fx.recorded_at)}")
    add("scenario_isolation", not leaks, "无跨场景污染" if not leaks else f"{len(leaks)} 处：{leaks[:6]}")

    # 8) 手算期望值与朴素实现一致
    mismatches: list[str] = []
    for sc in registry["scenarios"]:
        want = HAND_CHECKED.get(sc.name)
        if not want or not sc.expected:
            continue
        got = sc.expected["summary"]
        for key, value in (
            ("ships_observed", want["ships_observed"]),
            ("observed_entry_count", want["entries"]),
            ("observed_exit_count", want["exits"]),
            ("observed_ship_seconds", want["window_seconds"]),
        ):
            if abs(float(got[key]) - float(value)) > 1e-6:
                mismatches.append(f"{sc.name}.{key}: 朴素={got[key]} 手算={value}")
    add("hand_checked_expectations", not mismatches, "全部一致" if not mismatches else "; ".join(mismatches))

    # 9) 每日交集之和 == 窗口裁剪时长
    daily_bad: list[str] = []
    for sc in registry["scenarios"]:
        if not sc.expected:
            continue
        total = sum(row["observed_ship_seconds"] for row in sc.expected["daily"].values())
        if abs(total - sc.expected["summary"]["observed_ship_seconds"]) > 1e-6:
            daily_bad.append(f"{sc.name}: daily={total} vs window={sc.expected['summary']['observed_ship_seconds']}")
    add("daily_partition_identity", not daily_bad, "全部一致" if not daily_bad else "; ".join(daily_bad))

    # 10) segment 之和 == 访问时长 / 窗口裁剪时长
    seg_bad: list[str] = []
    for sc in registry["scenarios"]:
        if not sc.expected:
            continue
        for vk, visit in sc.expected["visits"].items():
            s_obs = sum(s["seconds"] for s in visit["segments"])
            s_win = sum(s["in_window_seconds"] for s in visit["segments"])
            if abs(s_obs - visit["observed_seconds"]) > 1e-6 or abs(s_win - visit["window_seconds"]) > 1e-6:
                seg_bad.append(f"{sc.name}/{vk}")
    add("segment_identity", not seg_bad, "全部一致" if not seg_bad else f"不一致：{seg_bad}")

    # 11) 快照三分类恒等式
    snap_ok = True
    snap_detail = []
    for snap in registry["snapshots"]:
        s = snap.expected["summary"]
        ok = s["in_area_count"] + s["out_of_area_fresh_count"] + s["stale_fix_count"] == s["evaluated_ship_count"]
        snap_ok = snap_ok and ok
        snap_detail.append(f"{snap.name}: {s}")
    add("snapshot_partition_identity", snap_ok, "; ".join(snap_detail))

    # 12) 覆盖度
    tokens: set[str] = set()
    for sc in registry["scenarios"]:
        tokens.update(sc.covers)
    for snap in registry["snapshots"]:
        tokens.update(snap.covers)
    for cmp_ in registry["compares"]:
        tokens.update(cmp_.covers)
    missing = sorted(set(REQUIRED_COVERAGE) - tokens)
    add(
        "coverage_tokens",
        not missing,
        "覆盖齐全" if not missing else f"缺少：{[REQUIRED_COVERAGE[m] for m in missing]}",
    )

    # 13) 进入/离开计数与访问明细一致（不是恒等式，仅提示差额来源）
    diffs = []
    for sc in registry["scenarios"]:
        s = sc.expected["summary"]
        diffs.append(
            f"{sc.name}: 进入{s['observed_entry_count']} 离开{s['observed_exit_count']} 访问{s['visit_count']}"
        )
    add("entry_exit_are_not_required_equal", True, "§2.4 明确不要求相等；" + " | ".join(diffs[:4]) + " ...")

    # 14) 朴素实现的样例数据不含自身跳点（除跳点场景外）
    jump_scenarios = []
    for sc in registry["scenarios"]:
        if not sc.expected:
            continue
        if any("jump_break" in v["flags"] for v in sc.expected["visits"].values()):
            jump_scenarios.append(sc.name)
    add(
        "jump_only_where_intended",
        jump_scenarios == ["S10_jump_spike"],
        f"含 jump 标记的场景：{jump_scenarios}",
    )

    # 15) 跳点回归（§2.3 行 4）：位移 <1 km 且推算速度 >30 kn 的相邻对不得判 jump，
    #     且该区间必须计入停留时长。
    reg = next((sc for sc in registry["scenarios"] if sc.name == "S20_fast_small_step_not_jump"), None)
    if reg is None or not reg.expected:
        add("jump_min_distance_regression", False, "缺少 S20 回归样例")
    else:
        own = sorted(
            (f for f in registry["fixes"] if f.ship_id in set(reg.ship_ids)),
            key=lambda f: (f.recorded_at, f.id),
        )
        pair = next(
            (
                (a, b)
                for a, b in zip(own, own[1:])
                if a.recorded_at < b.recorded_at
                and inside_rect(a.latitude, a.longitude, reg.rect)
                and inside_rect(b.latitude, b.longitude, reg.rect)
            ),
            None,
        )
        detail = "缺少相邻区内对"
        ok = False
        if pair is not None:
            a, b = pair
            dist_km = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude) / 1000.0
            speed_kn = implied_speed_kn(a, b)
            visits = list(reg.expected["visits"].values())
            visit = visits[0] if visits else {}
            ok = (
                dist_km < DEFAULT_PARAMS["jump_min_distance_km"]
                and speed_kn > DEFAULT_PARAMS["jump_speed_kn"]
                and len(visits) == 1
                and visit.get("flags") == []
                and visit.get("segment_count") == 1
                and abs(visit.get("observed_seconds", 0.0) - 1800.0) < 1e-6
                and abs(visit.get("unobserved_gap_seconds", -1.0)) < 1e-6
            )
            detail = (
                f"相邻对位移 {dist_km:.3f} km（<1.0）、推算速度 {speed_kn:.1f} kn（>30）、"
                f"访问数 {len(visits)}、flags={visit.get('flags')}、"
                f"segment_count={visit.get('segment_count')}、"
                f"observed_seconds={visit.get('observed_seconds')}、"
                f"unobserved_gap_seconds={visit.get('unobserved_gap_seconds')}"
            )
        add("jump_min_distance_regression", ok, detail)

    # 16) 开放选择提示：两种「出现去重船数」口径在当前样例上是否一致
    drift = []
    for sc in registry["scenarios"]:
        if not sc.expected:
            continue
        info = sc.expected["ambiguities"].get("summary.ships_observed")
        if info and info["alternates"] and info["alternates"][0] != sc.expected["summary"]["ships_observed"]:
            drift.append(f"{sc.name}(候选船={sc.expected['summary']['ships_observed']} "
                         f"访问船={info['alternates'][0]})")
    add(
        "ships_observed_readings_agree",
        not drift,
        "两种口径在当前样例上一致" if not drift else f"存在差异（按 WARN 记录）：{drift}",
    )

    # 17) 批次范围一致性（§2.0/§3/§4.3）：同一对区内报位之间只有 9002 的区外报位时，
    #     batch_ids=[9001] 必须不拆分，且扫描量/覆盖批次都按 9001 计；不筛批次才拆。
    s21 = next((sc for sc in registry["scenarios"] if sc.name == "S21_batch_scope_consistency"), None)
    if s21 is None or not s21.expected or len(s21.filter_checks) < 4:
        add("batch_scope_consistency", False, "缺少 S21 批次样例或其 filter 变体")
    else:
        own = sorted(
            (f for f in registry["fixes"] if f.ship_id in set(s21.ship_ids)),
            key=lambda f: (f.recorded_at, f.id),
        )
        inside = [f for f in own if inside_rect(f.latitude, f.longitude, s21.rect)]
        pairs = list(zip(inside, inside[1:]))
        mid = [
            (a, b, f)
            for a, b in pairs
            for f in own
            if a.recorded_at < f.recorded_at < b.recorded_at
        ]
        mid_outside = [item for item in mid if not inside_rect(item[2].latitude, item[2].longitude, s21.rect)]
        main, no_filter, only_9002, wrong_type = (
            s21.expected, s21.filter_checks[0]["expected"],
            s21.filter_checks[2]["expected"], s21.filter_checks[3]["expected"],
        )
        pair_seconds = (
            (mid_outside[0][1].recorded_at - mid_outside[0][0].recorded_at).total_seconds()
            if mid_outside else None
        )
        checks = {
            "中间区外报位只有一个且属于 9002": len(mid_outside) == 1
            and mid_outside[0][2].source_batch_id == 9002,
            "该对间隔在 (480, 1800) 内": pair_seconds is not None
            and DEFAULT_PARAMS["excursion_probe_seconds"] < pair_seconds < DEFAULT_PARAMS["gap_seconds"],
            "中间报位在 context 之外（只有探测能看到）": bool(mid_outside)
            and not in_context(
                mid_outside[0][2].latitude, mid_outside[0][2].longitude,
                s21.rect, DEFAULT_PARAMS["context_margin_deg"],
            ),
            "batch_ids=[9001] 不拆分（1 次访问 3000 s）": len(main["visits"]) == 1
            and abs(main["summary"]["observed_ship_seconds"] - 3000.0) < 1e-6
            and main["coverage_batch_ids"] == [9001],
            "不带批次拆成两次访问（+1 离开 +1 进入）": len(no_filter["visits"]) == 2
            and no_filter["summary"]["observed_entry_count"] == main["summary"]["observed_entry_count"] + 1
            and no_filter["summary"]["observed_exit_count"] == main["summary"]["observed_exit_count"] + 1
            and no_filter["coverage_batch_ids"] == [9001, 9002],
            "扫描量随批次变化（6 -> 7）": main["scanned_fix_count"] == 6
            and no_filter["scanned_fix_count"] == 7
            and only_9002["scanned_fix_count"] == 1,
            "批次与船型组合都生效": len(only_9002["visits"]) == 0
            and only_9002["status_hint"] == "ok"
            and wrong_type["status_hint"] == "no_data"
            and wrong_type["scanned_fix_count"] == 0,
        }
        bad = [name for name, ok in checks.items() if not ok]
        detail = (
            f"该对间隔 {pair_seconds}s；batch9001: 访问{len(main['visits'])}/扫描{main['scanned_fix_count']}；"
            f"不带批次: 访问{len(no_filter['visits'])}/扫描{no_filter['scanned_fix_count']}；"
            f"仅9002: 扫描{only_9002['scanned_fix_count']}；货船+9001: {wrong_type['status_hint']}"
        )
        add("batch_scope_consistency", not bad, detail if not bad else f"失败项：{bad} / {detail}")

    # 18) 短时外出（§2.0 v1.0.1）：间隔 1200 s（>480、<1800）且位移小，唯一中间报位在
    #     context 之外；有证据 -> 两次访问且该区间不计时长；删掉证据 -> 一次访问且计入时长。
    s22 = next((sc for sc in registry["scenarios"] if sc.name == "S22_short_excursion"), None)
    if s22 is None or not s22.expected or s22.removal_probe is None:
        add("short_excursion_probe", False, "缺少 S22 短时外出样例或其负向对照")
    else:
        own = sorted(
            (f for f in registry["fixes"] if f.ship_id in set(s22.ship_ids)),
            key=lambda f: (f.recorded_at, f.id),
        )
        inside = [f for f in own if inside_rect(f.latitude, f.longitude, s22.rect)]
        prev, cur = inside[0], inside[1]
        between = [f for f in own if prev.recorded_at < f.recorded_at < cur.recorded_at]
        gap_s = (cur.recorded_at - prev.recorded_at).total_seconds()
        dist_km = haversine_m(prev.latitude, prev.longitude, cur.latitude, cur.longitude) / 1000.0
        speed_kn = implied_speed_kn(prev, cur)
        visits = list(s22.expected["visits"].values())
        after = list(s22.removal_probe["expected"]["visits"].values())
        checks = {
            "间隔 1200 s 落在 (480, 1800)": abs(gap_s - 1200.0) < 1e-6
            and DEFAULT_PARAMS["excursion_probe_seconds"] < gap_s <= DEFAULT_PARAMS["gap_seconds"],
            "两端位移不足以判跳点": not (
                dist_km >= DEFAULT_PARAMS["jump_min_distance_km"]
                and speed_kn > DEFAULT_PARAMS["jump_speed_kn"]
            ),
            "唯一中间报位在 context 之外": len(between) == 1
            and not in_context(
                between[0].latitude, between[0].longitude,
                s22.rect, DEFAULT_PARAMS["context_margin_deg"],
            ),
            "有证据 -> 两次访问、进出各 2（对照各多 1 次）": len(visits) == 2
            and s22.expected["summary"]["observed_entry_count"] == 2
            and s22.expected["summary"]["observed_exit_count"] == 2,
            "外出的 1200 s 不计入时长": all(abs(v["observed_seconds"]) < 1e-6 for v in visits),
            "拆分两侧（前段离开/后段进入）证据在上下文之外": len(visits) == 2
            and all(v["flags"] == ["outside_evidence_out_of_context"] for v in visits)
            and visits[0]["exit"]["outside_evidence_in_context"] is False
            and visits[1]["entry"]["outside_evidence_in_context"] is False,
            "无证据对照 -> 一次访问且 1200 s 计入时长": len(after) == 1
            and abs(after[0]["observed_seconds"] - 1200.0) < 1e-6
            and after[0]["flags"] == []
            and s22.removal_probe["expected"]["summary"]["observed_entry_count"] == 1,
            "§2.3 行 2 已按文档修正：wide = bracket_seconds > gap_seconds（两侧不无条件置位）": all(
                v[side]["wide_bracket"]
                == (
                    v[side]["bracket_seconds"] is not None
                    and v[side]["bracket_seconds"] > DEFAULT_PARAMS["gap_seconds"]
                )
                for v in visits
                for side in ("entry", "exit")
            )
            and not any(
                key.endswith((".wide_bracket", ".flags"))
                for key in s22.expected["ambiguities"]
            ),
        }
        # 反事实：把探测阈值退回 v1.0.0 的 gap_seconds(1800 s)，同一场景必须回到
        # 「一次访问 + 1200 s」——说明本样例对「阈值 1800 s -> 480 s」这一修复有区分度。
        legacy_params = dict(s22.params or {})
        legacy_params["excursion_probe_seconds"] = DEFAULT_PARAMS["gap_seconds"]
        legacy = naive_analyze(
            registry["ships"], registry["fixes"], s22.rect, s22.start, s22.end,
            legacy_params, s22.ship_types, s22.batch_ids,
        )
        checks["反事实（阈值退回 gap_seconds）-> 一次访问 1200 s"] = (
            len(legacy["visits"]) == 1
            and abs(legacy["summary"]["observed_ship_seconds"] - 1200.0) < 1e-6
        )
        bad = [name for name, ok in checks.items() if not ok]
        detail = (
            f"该对间隔 {gap_s:.0f}s、位移 {dist_km:.2f} km（{speed_kn:.1f} kn）；"
            f"有证据: 访问{len(visits)} 进入{s22.expected['summary']['observed_entry_count']} "
            f"离开{s22.expected['summary']['observed_exit_count']} 时长{s22.expected['summary']['observed_ship_seconds']}s "
            f"宽括号={[v['entry']['wide_bracket'] or v['exit']['wide_bracket'] for v in visits]}（§2.3 行 2 "
            f"2026-10-07 已改为按 bracket_seconds > gap_seconds 判定，两侧括号 600 s -> false，"
            f"与实现一致，不再登记备选口径）；"
            f"无证据对照: 访问{len(after)} 时长{s22.removal_probe['expected']['summary']['observed_ship_seconds']}s"
        )
        add("short_excursion_probe", not bad, detail if not bad else f"失败项：{bad} / {detail}")

    return results


# ==========================================================================
# CLI
# ==========================================================================
def _coverage_table(registry: dict[str, Any]) -> str:
    lines = [
        f"{'scene':32s} {'window(UTC)':31s} {'fixes':>5s} {'ships':>5s} {'in':>3s} {'out':>4s} {'whours':>8s} status"
    ]
    for sc in registry["scenarios"]:
        fixes = [f for f in registry["fixes"] if f.ship_id in set(sc.ship_ids)]
        fixes = [f for f in fixes if sc.start - timedelta(hours=6) <= f.recorded_at < sc.end + timedelta(hours=6)]
        s = sc.expected["summary"]
        lines.append(
            f"{sc.name:32s} {_iso(sc.start)[:16]}~{_iso(sc.end)[11:16]:>5s}     "
            f"{len(fixes):5d} {s['ships_observed']:5d} {s['observed_entry_count']:3d} "
            f"{s['observed_exit_count']:4d} {s['observed_ship_hours']:8.3f} {sc.expected['status_hint']}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="区域活动独立样例与朴素期望值")
    parser.add_argument("--json", action="store_true", help="输出完整期望值 JSON")
    args = parser.parse_args(argv)

    registry = sample_registry()
    checks = self_check(registry)

    print("== self-check（内存内朴素复算自查，不经接口）==")
    failed = 0
    for item in checks:
        mark = "PASS" if item["ok"] else "FAIL"
        if not item["ok"]:
            failed += 1
        print(f"[{mark}] {item['name']}: {item['detail']}")
    print(f"self-check: {len(checks) - failed}/{len(checks)} 通过")

    print()
    print(f"== 场景清单（{len(registry['scenarios'])} 个窗口样例 / "
          f"{len(registry['snapshots'])} 个快照样例 / {len(registry['compares'])} 个 A/B 样例 / "
          f"{len(registry['validations'])} 个校验样例）==")
    print(_coverage_table(registry))
    print()
    print(f"样例船 {len(registry['ships'])} 艘，合成报位 {len(registry['fixes'])} 条")

    if args.json:
        payload = {
            "self_check": checks,
            "scenarios": [
                {
                    "name": sc.name,
                    "title": sc.title,
                    "doc_ref": sc.doc_ref,
                    "window": [_iso(sc.start), _iso(sc.end)],
                    "rect": sc.rect.as_query(),
                    "use_default_area": sc.use_default_area,
                    "ship_ids": sc.ship_ids,
                    "covers": sc.covers,
                    "expected": sc.expected,
                }
                for sc in registry["scenarios"]
            ],
            "snapshots": [
                {"name": s.name, "at": _iso(s.at), "expected": s.expected} for s in registry["snapshots"]
            ],
            "compares": [
                {
                    "name": c.name,
                    "windows": [[_iso(c.start_a), _iso(c.end_a)], [_iso(c.start_b), _iso(c.end_b)]],
                    "expected": c.expected,
                }
                for c in registry["compares"]
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
