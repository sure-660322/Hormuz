"""以历史 AIS 报位判定海峡虚拟双门线观测通行。

限定时间、来源和海峡区域后，在 PostgreSQL 内按船排序、筛出侧别变化；
应用只接收汇总和候选证据，不加载窗口内全部报位。SQL 固定且参数化。
"""
from dataclasses import dataclass, field
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.services.agent.config import (
    GATE_EAST_APPROACH_LON,
    GATE_EAST_LON,
    GATE_LOOKBACK,
    GATE_LAT_MAX,
    GATE_LAT_MIN,
    GATE_WEST_APPROACH_LON,
    GATE_WEST_LON,
    JUMP_SPEED_KN,
    LONG_GAP_THRESHOLD,
    MAX_GATE_FIXES_SCANNED,
    MAX_PASSAGE_CANDIDATES,
    MAX_WINDOW,
    SCHEMA_VERSION,
    SHIP_DATA_SOURCE,
)


@dataclass
class PositionFix:
    """一次报位的时间与经纬度。"""

    recorded_at: datetime
    longitude: float
    latitude: float


@dataclass
class PassageEvidence:
    """一条完整通行证据。uncertain 为 True 时表示不确定候选（不计入确定结果）。"""

    evidence_id: str  # P1/P2…（确定）或 U1/U2…（不确定候选）
    ship_id: int
    direction: str  # west_to_east / east_to_west
    start_fix: PositionFix  # 起始侧（变化前侧）最后一个报位
    completion_fix: PositionFix  # 完成侧首个报位（观测完成位置）
    observed_completion_at: datetime  # = completion_fix.recorded_at，观测完成时间，非精确越线时刻
    uncertain: bool = False
    uncertain_reason: str | None = None  # left_corridor / long_gap / jump


@dataclass
class ShipPassageSummary:
    ship_id: int
    name: str
    passage_count: int


@dataclass
class QuerySummary:
    position_count: int  # 数据库内参与判定的门线侧别报位数（含前置 24 小时）
    matched_ship_count: int
    passage_count: int  # 确定通行次数（同船多次穿越累计）
    uncertain_candidate_count: int
    coverage_start: datetime | None  # 判定范围内最早侧别报位时间
    coverage_end: datetime | None  # 判定范围内最晚侧别报位时间
    truncated: bool  # 恒为 False；读取超限直接报错，不截断


@dataclass
class StraitPassageResult:
    status: str  # ok（含零匹配）/ partial（存在不确定候选）/ no_data（窗口内无报位，不能解释成零结果）
    schema_version: str = SCHEMA_VERSION
    closure_at: datetime = None
    end_at: datetime = None
    ships: list[ShipPassageSummary] = field(default_factory=list)
    evidence: list[PassageEvidence] = field(default_factory=list)  # 仅确定通行
    uncertain_candidates: list[PassageEvidence] = field(default_factory=list)
    query_summary: QuerySummary = None
    limitations: list[str] = field(default_factory=list)


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius_km = 6371.0
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * radius_km * asin(sqrt(a))


def _validate(closure_at: datetime, end_at: datetime) -> None:
    if closure_at.tzinfo is None or closure_at.utcoffset() is None:
        raise ValueError("closure_at 必须包含显式时区（带时区的 ISO 8601 时间）")
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        raise ValueError("end_at 必须包含显式时区（带时区的 ISO 8601 时间）")
    if not closure_at < end_at:
        raise ValueError("closure_at 必须早于 end_at")
    if end_at - closure_at > MAX_WINDOW:
        raise ValueError(f"查询窗口不能超过 24 小时，请缩小范围（当前 {end_at - closure_at}）")


def query_strait_passages(
    db: Session,
    closure_at: datetime,
    end_at: datetime,
    ship_id: int | None = None,
) -> StraitPassageResult:
    """按海峡虚拟双门线查询观测通行，不把源报位集加载到应用内存。"""
    _validate(closure_at, end_at)
    if ship_id is not None and (isinstance(ship_id, bool) or not isinstance(ship_id, int) or ship_id <= 0):
        raise ValueError("ship_id 必须为正整数")
    lookback_at = closure_at - GATE_LOOKBACK
    params = {
        "source": SHIP_DATA_SOURCE,
        "lookback_at": lookback_at,
        "closure_at": closure_at,
        "end_at": end_at,
        "lat_min": GATE_LAT_MIN,
        "lat_max": GATE_LAT_MAX,
        "west_approach": GATE_WEST_APPROACH_LON,
        "east_approach": GATE_EAST_APPROACH_LON,
        "west_gate": GATE_WEST_LON,
        "east_gate": GATE_EAST_LON,
        "ship_id": ship_id,
    }
    # 限定 48 小时内的门线侧别报位；中间带不改变已观测到的侧别。
    scope = """
        FROM ship_positions AS p
        WHERE p.data_source = :source
          AND p.recorded_at >= :lookback_at AND p.recorded_at < :end_at
          AND p.latitude BETWEEN :lat_min AND :lat_max
          AND p.longitude BETWEEN :west_approach AND :east_approach
          AND (p.longitude < :west_gate OR p.longitude > :east_gate)
    """
    if ship_id is not None:
        scope += " AND p.ship_id = :ship_id"
    summary = db.execute(text("""
        SELECT count(*) AS position_count, min(p.recorded_at) AS coverage_start,
               max(p.recorded_at) AS coverage_end,
               count(*) FILTER (WHERE p.recorded_at >= :closure_at) AS window_position_count
    """ + scope), params).mappings().one()
    position_count = summary["position_count"]
    if position_count > MAX_GATE_FIXES_SCANNED:
        raise ValueError(
            f"海峡门线附近报位数 {position_count} 超过上限 {MAX_GATE_FIXES_SCANNED}，"
            "请缩小查询窗口；结果没有被截断"
        )
    if not position_count:
        return StraitPassageResult(
            status="no_data", closure_at=closure_at, end_at=end_at,
            query_summary=QuerySummary(0, 0, 0, 0, None, None, False),
            limitations=["所选窗口及前置 24 小时内无海峡虚拟门线侧别报位，无法判定通行"],
        )

    # PostgreSQL 在库内排序并只返回侧别变化的证据行。id 让同秒多报位稳定排序；
    # 同秒跨侧会被判作疑似跳点，绝不静默去重。
    transitions_sql = text("""
        WITH scoped AS MATERIALIZED (
            SELECT p.id, p.ship_id, p.recorded_at, p.longitude, p.latitude,
                   CASE WHEN p.longitude < :west_gate THEN 'west' ELSE 'east' END AS side
    """ + scope + """
        ), ordered AS (
            SELECT scoped.*,
                   lag(side) OVER ship_time AS previous_side,
                   lag(id) OVER ship_time AS previous_id,
                   lag(recorded_at) OVER ship_time AS previous_at,
                   lag(longitude) OVER ship_time AS previous_lon,
                   lag(latitude) OVER ship_time AS previous_lat
            FROM scoped
            WINDOW ship_time AS (PARTITION BY ship_id ORDER BY recorded_at, id)
        )
        SELECT o.ship_id, s.name, o.side, o.previous_side,
               o.recorded_at, o.longitude, o.latitude,
               o.previous_at, o.previous_lon, o.previous_lat,
               EXISTS (
                   SELECT 1 FROM ship_positions AS between_fix
                   WHERE between_fix.ship_id = o.ship_id
                     AND between_fix.data_source = :source
                     AND (between_fix.recorded_at, between_fix.id)
                         > (o.previous_at, o.previous_id)
                     AND (between_fix.recorded_at, between_fix.id)
                         < (o.recorded_at, o.id)
                     AND (
                         between_fix.latitude NOT BETWEEN :lat_min AND :lat_max
                         OR between_fix.longitude NOT BETWEEN :west_approach AND :east_approach
                     )
               ) AS left_corridor
        FROM ordered AS o JOIN ships AS s ON s.id = o.ship_id
        WHERE o.previous_side IS NOT NULL AND o.previous_side <> o.side
          AND o.recorded_at >= :closure_at
        ORDER BY o.recorded_at, o.ship_id, o.id
        LIMIT :candidate_limit
    """)
    rows = db.execute(transitions_sql, {
        **params, "candidate_limit": MAX_PASSAGE_CANDIDATES + 1,
    }).mappings().all()
    if len(rows) > MAX_PASSAGE_CANDIDATES:
        raise ValueError(
            f"侧别变化候选超过上限 {MAX_PASSAGE_CANDIDATES}，请缩小查询窗口；"
            "结果没有被截断"
        )

    confirmed: list[PassageEvidence] = []
    uncertain: list[PassageEvidence] = []
    ship_names: dict[int, str] = {}
    for row in rows:
        previous = PositionFix(row["previous_at"], row["previous_lon"], row["previous_lat"])
        current = PositionFix(row["recorded_at"], row["longitude"], row["latitude"])
        gap = current.recorded_at - previous.recorded_at
        distance_km = _haversine_km(
            previous.longitude, previous.latitude, current.longitude, current.latitude
        )
        implied_speed_kn = (
            distance_km / 1.852 / (gap.total_seconds() / 3600)
            if gap.total_seconds() > 0 else float("inf")
        )
        reason = (
            "left_corridor" if row["left_corridor"] else
            "long_gap" if gap > LONG_GAP_THRESHOLD else
            "jump" if implied_speed_kn > JUMP_SPEED_KN else None
        )
        item = PassageEvidence(
            evidence_id="", ship_id=row["ship_id"],
            direction=f"{row['previous_side']}_to_{row['side']}",
            start_fix=previous, completion_fix=current,
            observed_completion_at=current.recorded_at,
            uncertain=reason is not None, uncertain_reason=reason,
        )
        ship_names[row["ship_id"]] = row["name"]
        (uncertain if reason else confirmed).append(item)

    for index, item in enumerate(confirmed, start=1):
        item.evidence_id = f"P{index}"
    for index, item in enumerate(uncertain, start=1):
        item.evidence_id = f"U{index}"
    passages_by_ship: dict[int, int] = {}
    first_completion: dict[int, datetime] = {}
    for item in confirmed:
        passages_by_ship[item.ship_id] = passages_by_ship.get(item.ship_id, 0) + 1
        first_completion.setdefault(item.ship_id, item.observed_completion_at)
    ships = [
        ShipPassageSummary(ship_id, ship_names[ship_id], count)
        for ship_id, count in passages_by_ship.items()
    ]
    ships.sort(key=lambda ship: (first_completion[ship.ship_id], ship.ship_id))

    limitations = [
        "虚拟双门线为纬度 25.8–27.1°N 内的 56.2°E 西侧与 56.7°E 东侧；"
        "仅使用经度 55.8–57.1°E 范围内、来源 nnu_ais 的实测报位",
        "完成时间是完成侧首次报位时间，不是精确越线时刻；前置侧别最多回看 24 小时，"
        "未观测到通行不证明船舶未通过",
        "AIS 来源授权和覆盖尚未核实；侧别变化只证明符合本虚拟门线口径，"
        "不能单凭它认定新闻事件因果或实际航道",
    ]
    if ship_id is not None:
        limitations.append(f"本次仅核对 ship_id={ship_id}；无门线证据不等于该船未通过")
    if uncertain:
        limitations.append(
            f"存在 {len(uncertain)} 条离开判定区域、长间隔或疑似跳点候选，未计入确定结果"
        )
    if not confirmed and summary["window_position_count"]:
        limitations.append("窗口内未观测到满足门线与连续性规则的通行；不能推断海峡实际无船通行")
    if not summary["window_position_count"]:
        limitations.append("窗口内没有门线侧别报位，无法判定该窗口的通行")
    return StraitPassageResult(
        status="no_data" if not summary["window_position_count"] else (
            "partial" if uncertain else "ok"
        ),
        closure_at=closure_at, end_at=end_at, ships=ships,
        evidence=confirmed, uncertain_candidates=uncertain,
        query_summary=QuerySummary(
            position_count=position_count, matched_ship_count=len(ships),
            passage_count=len(confirmed), uncertain_candidate_count=len(uncertain),
            coverage_start=summary["coverage_start"], coverage_end=summary["coverage_end"],
            truncated=False,
        ),
        limitations=limitations,
    )
