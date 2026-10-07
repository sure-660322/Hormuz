"""动态海峡通行统计与 A/B 比较（issue #40）。

手动分析面板（/api/strait-passages/*）与智能体工具
（query_strait_passage_statistics / compare_strait_passage_statistics）共用本服务：
路由/工具只负责校验与参数归一，分窗编排、去重、汇总与比较全部在这里完成，
前端与模型不得重新判断通行。

口径（与 strait_passages.py 完全一致）：
- 逐日拆分：UTC 自然日子窗 [day, day+1)，每个子窗 ≤24h，复用单窗判定并保留
  24 小时前置侧别回看；跨日通行由完成观测时间归入唯一一天，稳定证据键
  ship_id:start_fix_id:completion_fix_id 消除任何分窗重复。
- 归日：按完成侧首次报位（观测完成时间）的 UTC 日期，不称为精确越线时刻。
- 候选（离开走廊/长间隔/跳点）不计入确定量，逐日保留数量与原因。
- 全部船型与互斥船型（含未知/缺失）分组共用同一 SQL 过滤口径。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import hashlib

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.agent.config import (
    GATE_EAST_LON,
    GATE_LAT_MAX,
    GATE_LAT_MIN,
    GATE_LOOKBACK,
    GATE_WEST_LON,
    JUMP_SPEED_KN,
    LONG_GAP_THRESHOLD,
    MAX_STATS_PERIOD,
    SCHEMA_VERSION,
    SHIP_DATA_SOURCE,
    UNKNOWN_SHIP_TYPE_OPTION,
)
from backend.app.services.agent.strait_passages import (
    PassageEvidence,
    _gate_transition_rows,
    _classify_evidence,
)

# 判定版本：判定参数变化时必须递增，随结果返回供对照。
DETERMINATION_VERSION = "strait-gates-v1+stats-2026-10-07"
# 方向常量（API 语义层）：入湾 = 东→西，出湾 = 西→东（与门线侧别口径一致）。
DIRECTION_INBOUND = "inbound"    # east_to_west
DIRECTION_OUTBOUND = "outbound"  # west_to_east
_DIRECTION_MAP = {
    None: None,
    "all": None,
    DIRECTION_INBOUND: "east_to_west",
    DIRECTION_OUTBOUND: "west_to_east",
    "east_to_west": "east_to_west",
    "west_to_east": "west_to_east",
}
MAX_EVIDENCE_PAGE_SIZE = 200
CASE_BATCH_IDS = (8,)  # 独立单船案例补充批次（source_batch_id），与七日全船批次区分


def evidence_stable_key(item: PassageEvidence) -> str:
    """稳定证据键：源报位 id 不随调用/分窗变化，同秒冲突由 id 区分。"""
    return f"{item.ship_id}:{item.start_fix_id}:{item.completion_fix_id}"


@dataclass
class DailyStats:
    day: date
    status: str  # ok / zero（有观测无确定通行）/ partial（含不确定候选）/ no_observation
    passage_count: int
    unique_ship_count: int
    inbound_count: int
    outbound_count: int
    uncertain_candidate_count: int
    position_count: int  # 当日窗口（含 24h 回看）内经船型过滤的门线侧别报位数
    window_position_count: int  # 仅当日窗口内的报位数
    coverage_start: datetime | None
    coverage_end: datetime | None


@dataclass
class WindowStats:
    passage_count: int
    unique_ship_count: int
    inbound_count: int
    outbound_count: int
    uncertain_candidate_count: int
    position_count: int


@dataclass
class StatisticsResult:
    status: str  # ok / partial / no_data（全部子窗无观测）
    start_at: datetime
    end_at: datetime
    requested_days: float  # 请求窗口折算天数的分母（日均口径）
    ship_types: list[str] | None  # None=全部；含 UNKNOWN_SHIP_TYPE_OPTION 表示含未知/缺失
    direction: str | None  # inbound / outbound / None=全部
    daily: list[DailyStats] = field(default_factory=list)
    window: WindowStats | None = None
    determination_version: str = DETERMINATION_VERSION
    schema_version: str = SCHEMA_VERSION
    data_source: str = SHIP_DATA_SOURCE
    limitations: list[str] = field(default_factory=list)


@dataclass
class MetricComparison:
    metric: str
    a_value: int
    b_value: int
    delta: int  # B - A
    change_rate: float | None  # (B-A)/A；A=0 时为 None（不生成 Infinity/NaN）

@dataclass
class CompareResult:
    status: str
    ship_types: list[str] | None
    direction: str | None
    a: StatisticsResult
    b: StatisticsResult
    metrics: list[MetricComparison]
    a_period_days: float
    b_period_days: float
    a_avg_passages_per_day: float
    b_avg_passages_per_day: float
    windows_overlap: bool
    comparability_notes: list[str]
    determination_version: str = DETERMINATION_VERSION


def _normalize_ship_types(ship_types) -> list[str] | None:
    """归一船型参数：None/空列表=全部；去重并校验非空字符串。"""
    if ship_types is None:
        return None
    if isinstance(ship_types, str):
        ship_types = [ship_types]
    selected: list[str] = []
    for item in ship_types:
        value = str(item).strip()
        if not value:
            raise ValueError("船型参数包含空值")
        if value not in selected:
            selected.append(value)
    return selected or None


def _normalize_direction(direction) -> str | None:
    if direction not in _DIRECTION_MAP:
        raise ValueError("direction 必须是 inbound / outbound / all 或省略")
    return _DIRECTION_MAP[direction]


def _validate_period(start_at: datetime, end_at: datetime) -> None:
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at 必须包含显式时区（带时区的 ISO 8601 时间，统一 UTC）")
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        raise ValueError("end_at 必须包含显式时区（带时区的 ISO 8601 时间，统一 UTC）")
    if not start_at < end_at:
        raise ValueError("start_at 必须早于 end_at")
    if end_at - start_at > MAX_STATS_PERIOD:
        raise ValueError(
            f"统计时段不能超过 {MAX_STATS_PERIOD.days} 天（当前 {end_at - start_at}），"
            "请缩小范围；结果没有被截断"
        )


def _split_utc_days(start_at: datetime, end_at: datetime) -> list[tuple[datetime, datetime]]:
    """把 [start_at, end_at) 拆成 UTC 自然日子窗，每窗 ≤24h。"""
    days: list[tuple[datetime, datetime]] = []
    cursor = start_at
    while cursor < end_at:
        next_midnight = (cursor + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = min(next_midnight, end_at)
        days.append((cursor, day_end))
        cursor = day_end
    return days


def _run_period(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    ship_types: list[str] | None,
    side_direction: str | None,
) -> StatisticsResult:
    """单时段统计：服务端逐日编排，同一请求会话内完成（只读）。"""
    _validate_period(start_at, end_at)
    days = _split_utc_days(start_at, end_at)

    daily: list[DailyStats] = []
    seen_keys: set[str] = set()
    window_ships: set[int] = set()
    totals = {
        "passage_count": 0, "inbound_count": 0, "outbound_count": 0,
        "uncertain_candidate_count": 0, "position_count": 0,
    }
    any_observation = False
    any_uncertain = False

    for day_start, day_end in days:
        rows, summary = _gate_transition_rows(
            db, day_start, day_end, ship_types=ship_types, direction=side_direction,
        )
        position_count = summary["position_count"]
        window_position_count = summary["window_position_count"]
        if position_count:
            any_observation = True
        confirmed: list[PassageEvidence] = []
        uncertain: list[PassageEvidence] = []
        day_ships: set[int] = set()
        for row in rows:
            item = _classify_evidence(row)
            # 稳定证据键去重：不依赖每次调用重置的 P1/P2 编号，跨子窗同一通行只计一次。
            key = evidence_stable_key(item)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if item.uncertain:
                uncertain.append(item)
            else:
                confirmed.append(item)
                day_ships.add(item.ship_id)
                window_ships.add(item.ship_id)
        inbound = sum(1 for item in confirmed if item.direction == "east_to_west")
        outbound = sum(1 for item in confirmed if item.direction == "west_to_east")
        if not position_count:
            day_status = "no_observation"
        elif uncertain:
            day_status = "partial"
        elif confirmed:
            day_status = "ok"
        else:
            day_status = "zero"
        any_uncertain = any_uncertain or bool(uncertain)
        totals["passage_count"] += len(confirmed)
        totals["inbound_count"] += inbound
        totals["outbound_count"] += outbound
        totals["uncertain_candidate_count"] += len(uncertain)
        totals["position_count"] += position_count
        daily.append(DailyStats(
            day=day_start.date(), status=day_status,
            passage_count=len(confirmed), unique_ship_count=len(day_ships),
            inbound_count=inbound, outbound_count=outbound,
            uncertain_candidate_count=len(uncertain),
            position_count=position_count, window_position_count=window_position_count,
            coverage_start=summary["coverage_start"], coverage_end=summary["coverage_end"],
        ))

    requested_days = (end_at - start_at).total_seconds() / 86400
    result = StatisticsResult(
        status=("no_data" if not any_observation else ("partial" if any_uncertain else "ok")),
        start_at=start_at, end_at=end_at, requested_days=requested_days,
        ship_types=ship_types,
        direction=side_direction,
        daily=daily,
        window=WindowStats(
            passage_count=totals["passage_count"],
            unique_ship_count=len(window_ships),
            inbound_count=totals["inbound_count"],
            outbound_count=totals["outbound_count"],
            uncertain_candidate_count=totals["uncertain_candidate_count"],
            position_count=totals["position_count"],
        ),
    )
    result.limitations.extend(_period_limitations(result, side_direction))
    return result


def _period_limitations(result: StatisticsResult, side_direction: str | None) -> list[str]:
    limitations = [
        "虚拟双门线为纬度 25.8–27.1°N 内的 56.2°E 西侧与 56.7°E 东侧；"
        "仅使用经度 55.8–57.1°E、来源 nnu_ais 的历史报位",
        "按完成侧首次报位的观测完成时间（UTC）归日，不是精确越线时刻；"
        "前置侧别最多回看 24 小时，未观测到通行不证明船舶未通过",
        f"判定版本 {DETERMINATION_VERSION}；长间隔阈值 {LONG_GAP_THRESHOLD}、"
        f"跳点阈值 {JUMP_SPEED_KN} kn 尚未用真实 AIS 独立校准",
        "AIS 来源授权和覆盖尚未核实；统计只反映本口径下的观测，"
        "不能解释为实际全部交通变化或新闻因果",
        "ships.ship_type 为当前快照属性，未知/缺失按原始字段保留，不按船名推断历史船型",
    ]
    if result.status == "no_data":
        limitations.append("所选时段内没有门线侧别报位，无法判定通行；这不是「真实零通行」")
    if side_direction == "east_to_west":
        limitations.append("本次仅统计入湾（东→西）方向；方向去重艘数与全方向口径不同，不能互推")
    elif side_direction == "west_to_east":
        limitations.append("本次仅统计出湾（西→东）方向；方向去重艘数与全方向口径不同，不能互推")
    return limitations


def query_strait_passage_statistics(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    ship_types=None,
    direction=None,
) -> StatisticsResult:
    """一个时段的按日统计与全窗汇总（手动 API 与智能体工具共用入口）。"""
    selected_types = _normalize_ship_types(ship_types)
    side_direction = _normalize_direction(direction)
    return _run_period(db, start_at, end_at, selected_types, side_direction)


def _compare_metric(metric: str, a_value: int, b_value: int) -> MetricComparison:
    return MetricComparison(
        metric=metric, a_value=a_value, b_value=b_value, delta=b_value - a_value,
        change_rate=((b_value - a_value) / a_value) if a_value > 0 else None,
    )


def compare_strait_passage_statistics(
    db: Session,
    a_start_at: datetime,
    a_end_at: datetime,
    b_start_at: datetime,
    b_end_at: datetime,
    ship_types=None,
    direction=None,
) -> CompareResult:
    """A/B 两期比较：共享筛选，返回两期统计、差值、(B-A)/A 变化率与覆盖可比性。"""
    selected_types = _normalize_ship_types(ship_types)
    side_direction = _normalize_direction(direction)
    a = _run_period(db, a_start_at, a_end_at, selected_types, side_direction)
    b = _run_period(db, b_start_at, b_end_at, selected_types, side_direction)
    metrics = [
        _compare_metric("passage_count", a.window.passage_count, b.window.passage_count),
        _compare_metric("unique_ship_count", a.window.unique_ship_count, b.window.unique_ship_count),
        _compare_metric("inbound_count", a.window.inbound_count, b.window.inbound_count),
        _compare_metric("outbound_count", a.window.outbound_count, b.window.outbound_count),
        _compare_metric("uncertain_candidate_count", a.window.uncertain_candidate_count, b.window.uncertain_candidate_count),
    ]
    windows_overlap = a_start_at < b_end_at and b_start_at < a_end_at
    a_days = (a_end_at - a_start_at).total_seconds() / 86400
    b_days = (b_end_at - b_start_at).total_seconds() / 86400
    a_no_obs = sum(1 for day in a.daily if day.status == "no_observation")
    b_no_obs = sum(1 for day in b.daily if day.status == "no_observation")

    notes: list[str] = []
    if a_days != b_days:
        notes.append(
            f"A/B 窗口长度不同（A {a_days:.2f} 天、B {b_days:.2f} 天）；"
            "日均次数按各窗口请求天数为分母，仅作可比参考"
        )
    if a_no_obs or b_no_obs:
        notes.append(
            f"存在无观测日（A {a_no_obs} 天、B {b_no_obs} 天），"
            "日均与变化率不代表完整有效覆盖，不能当作无条件结论"
        )
    if windows_overlap:
        notes.append("A/B 两期时间重叠，两期统计不独立，差值不代表相互独立的交通变化")
    if any(m.change_rate is None for m in metrics[:4]):
        notes.append("A 期为 0 的指标变化率为 null（不生成 Infinity/NaN），"
                     "B 期非零只能说明「从无到有」，不能给出倍数")
    if a.status == "no_data" or b.status == "no_data":
        notes.append("至少一期完全无观测，两期比较差值无统计意义")

    return CompareResult(
        status=("no_data" if a.status == "no_data" and b.status == "no_data"
                else "partial" if "partial" in (a.status, b.status) else "ok"),
        ship_types=selected_types, direction=side_direction,
        a=a, b=b, metrics=metrics,
        a_period_days=a_days, b_period_days=b_days,
        a_avg_passages_per_day=a.window.passage_count / a_days,
        b_avg_passages_per_day=b.window.passage_count / b_days,
        windows_overlap=windows_overlap,
        comparability_notes=notes,
    )


def query_strait_passage_evidence(
    db: Session,
    start_at: datetime,
    end_at: datetime,
    *,
    day: date | None = None,
    ship_types=None,
    direction=None,
    include_uncertain: bool = False,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """单时段证据明细分页：只重跑该时段逐日判定并切片，汇总完整性不依赖分页。"""
    _validate_period(start_at, end_at)
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("page 必须是正整数")
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= MAX_EVIDENCE_PAGE_SIZE:
        raise ValueError(f"page_size 必须是 1–{MAX_EVIDENCE_PAGE_SIZE} 的整数")
    selected_types = _normalize_ship_types(ship_types)
    side_direction = _normalize_direction(direction)

    days = _split_utc_days(start_at, end_at)
    if day is not None:
        days = [(d0, d1) for d0, d1 in days if d0.date() == day]
        if not days:
            raise ValueError("day 必须落在 [start_at, end_at) 的 UTC 日期范围内")

    items: list[PassageEvidence] = []
    seen_keys: set[str] = set()
    uncertain_total = 0
    confirmed_total = 0
    for day_start, day_end in days:
        rows, _ = _gate_transition_rows(
            db, day_start, day_end, ship_types=selected_types, direction=side_direction,
        )
        for row in rows:
            item = _classify_evidence(row)
            key = evidence_stable_key(item)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if item.uncertain:
                uncertain_total += 1
                if include_uncertain:
                    items.append(item)
            else:
                confirmed_total += 1
                items.append(item)

    total = len(items)
    start_index = (page - 1) * page_size
    if start_index >= total and total > 0:
        raise ValueError(f"page 超出范围：共 {total} 条，page_size={page_size}")
    page_items = items[start_index:start_index + page_size]
    return {
        "status": "ok",
        "page": page,
        "page_size": page_size,
        "returned_count": len(page_items),
        "matched_count": total,
        "confirmed_count": confirmed_total,
        "uncertain_candidate_count": uncertain_total,
        "page_count": (total + page_size - 1) // page_size,
        "determination_version": DETERMINATION_VERSION,
        "items": [
            {
                # 确定性证据展示 ID（md5 稳定，跨进程/重启不变）；稳定键为权威去重依据。
                "evidence_id": "E-" + hashlib.md5(evidence_stable_key(item).encode("utf-8")).hexdigest()[:10],
                "stable_key": evidence_stable_key(item),
                "ship_id": item.ship_id,
                "ship_name": item.ship_name,
                "direction": item.direction,
                "start_fix": item.start_fix,
                "completion_fix": item.completion_fix,
                "observed_completion_at": item.observed_completion_at,
                "uncertain": item.uncertain,
                "uncertain_reason": item.uncertain_reason,
                "ship_type": item.ship_type,
            }
            for item in page_items
        ],
        "limitations": [
            "证据明细为确定通行；include_uncertain=true 时附不确定候选（含原因），均不计入确定量",
            "分页只影响本页条数，matched_count/confirmed_count 为完整统计，不受分页影响",
        ],
    }


@dataclass
class PassageMeta:
    ship_type_options: list[dict]  # [{value, label, ship_count}]，含未知/缺失桶
    coverage: list[dict]  # 按 source_batch_id：批次范围与归类（七日全船/案例补充/其他）
    coverage_start: datetime | None
    coverage_end: datetime | None
    determination: dict
    schema_version: str = SCHEMA_VERSION


def get_strait_passage_meta(db: Session) -> PassageMeta:
    """范围/船型元数据：核验后的来源批次覆盖 + 船型清单（含未知/缺失），不硬编码历史数量。"""
    type_rows = db.execute(text("""
        SELECT s.ship_type AS ship_type, count(DISTINCT s.id) AS ship_count
        FROM ships AS s
        WHERE EXISTS (
            SELECT 1 FROM ship_positions AS p
            WHERE p.ship_id = s.id AND p.data_source = :source
        )
        GROUP BY s.ship_type
        ORDER BY ship_count DESC, ship_type NULLS LAST
    """), {"source": SHIP_DATA_SOURCE}).mappings().all()
    options: list[dict] = []
    unknown_count = 0
    for row in type_rows:
        raw = row["ship_type"]
        if raw is None or raw in ("未知",):
            unknown_count += row["ship_count"]
        else:
            options.append({"value": raw, "label": raw, "ship_count": row["ship_count"]})
    options.append({
        "value": UNKNOWN_SHIP_TYPE_OPTION,
        "label": "未知/缺失",
        "ship_count": unknown_count,
    })

    # 两级聚合避免 17.9M 行排序去重：先按（批次, 船）分组，再按批次汇总。
    # 本机应用库实测约 0.9s（单级 count(DISTINCT) 约 5.5s，超出元数据预算）。
    batch_rows = db.execute(text("""
        SELECT batch_id, sum(position_count) AS position_count,
               count(*) AS ship_count,
               min(coverage_start) AS coverage_start,
               max(coverage_end) AS coverage_end
        FROM (
            SELECT p.source_batch_id AS batch_id, p.ship_id,
                   count(*) AS position_count,
                   min(p.recorded_at) AS coverage_start,
                   max(p.recorded_at) AS coverage_end
            FROM ship_positions AS p
            WHERE p.data_source = :source
            GROUP BY p.source_batch_id, p.ship_id
        ) AS per_ship
        GROUP BY batch_id
        ORDER BY batch_id
    """), {"source": SHIP_DATA_SOURCE}).mappings().all()
    coverage: list[dict] = []
    starts: list[datetime] = []
    ends: list[datetime] = []
    for row in batch_rows:
        batch_id = row["batch_id"]
        if batch_id in CASE_BATCH_IDS:
            kind = "case_supplement"
            kind_label = "独立单船案例补充（非海峡全量覆盖）"
        elif batch_id is not None:
            kind = "seven_day_batch"
            kind_label = "七日全船批次（UTC+8 文件日，逐批覆盖）"
        else:
            kind = "unclassified"
            kind_label = "未标注批次"
        coverage.append({
            "batch_id": batch_id, "kind": kind, "kind_label": kind_label,
            "position_count": row["position_count"], "ship_count": row["ship_count"],
            "coverage_start": row["coverage_start"], "coverage_end": row["coverage_end"],
        })
        if row["coverage_start"]:
            starts.append(row["coverage_start"])
        if row["coverage_end"]:
            ends.append(row["coverage_end"])

    determination = {
        "version": DETERMINATION_VERSION,
        "schema_version": SCHEMA_VERSION,
        "data_source": SHIP_DATA_SOURCE,
        "gate": {
            "lat_min": GATE_LAT_MIN, "lat_max": GATE_LAT_MAX,
            "west_gate_lon": GATE_WEST_LON, "east_gate_lon": GATE_EAST_LON,
            "lookback": str(GATE_LOOKBACK),
        },
        "thresholds": {
            "long_gap": str(LONG_GAP_THRESHOLD),
            "jump_speed_kn": JUMP_SPEED_KN,
        },
        "stats_period_limit_days": MAX_STATS_PERIOD.days,
    }
    return PassageMeta(
        ship_type_options=options,
        coverage=coverage,
        coverage_start=min(starts) if starts else None,
        coverage_end=max(ends) if ends else None,
        determination=determination,
    )
