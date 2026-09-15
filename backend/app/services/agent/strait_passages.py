"""海峡完整通行查询服务（智能体工具 query_strait_passages 的后端实现）。

判定口径与 sim_ais_demo/tools/verify_news_alignment.py 一致：
在纬度 25.8–27.1°N 带内，按经度与 56.2°E / 56.7°E 两门线比较定侧别，
保留门线之间的状态；观测到侧别变化记为一次完整穿越候选，
完成侧首个报位时间落在 [closure_at, end_at) 内才计入。

纯只读、参数化查询；不执行模型生成的 SQL。
"""
from dataclasses import dataclass, field
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.models import ShipPosition
from backend.app.services.agent.config import (
    GATE_EAST_LON,
    GATE_LAT_MAX,
    GATE_LAT_MIN,
    GATE_WEST_LON,
    JUMP_SPEED_KN,
    LONG_GAP_THRESHOLD,
    MAX_POSITIONS_READ,
    MAX_WINDOW,
)

# 契约版本（docs/agent_integration.md v2）
SCHEMA_VERSION = "2"


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
    uncertain_reason: str | None = None  # long_gap / jump


@dataclass
class ShipPassageSummary:
    ship_id: int
    name: str
    passage_count: int


@dataclass
class QuerySummary:
    position_count: int  # 实际读取的报位数（含窗口前用于确定初始状态的历史报位）
    matched_ship_count: int
    passage_count: int  # 确定通行次数（同船多次穿越累计）
    uncertain_candidate_count: int
    coverage_start: datetime | None  # 读取报位的最早时间
    coverage_end: datetime | None  # 读取报位的最晚时间
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


def _side_of(longitude: float, latitude: float) -> str | None:
    """侧别判定；纬度带外或两门线之间返回 None（保留状态，不参与判定）。"""
    if not GATE_LAT_MIN <= latitude <= GATE_LAT_MAX:
        return None
    if longitude < GATE_WEST_LON:
        return "west"
    if longitude > GATE_EAST_LON:
        return "east"
    return None


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
) -> StraitPassageResult:
    """查询 [closure_at, end_at) 内观测完成的完整海峡通行。

    只读；读取 closure_at 之前的历史报位以确定初始侧别状态。
    读取报位数超过上限时抛 ValueError，要求缩小范围，绝不截断后宣称零匹配。
    """
    _validate(closure_at, end_at)

    position_count = db.scalar(
        select(func.count(ShipPosition.id)).where(ShipPosition.recorded_at < end_at)
    ) or 0
    if position_count > MAX_POSITIONS_READ:
        raise ValueError(
            f"判定所需报位数约 {position_count}，超过上限 {MAX_POSITIONS_READ}，"
            "请缩小查询范围，不能截断后宣称零匹配"
        )

    rows = db.execute(
        text(
            """
            SELECT
                ships.id AS ship_id,
                ships.name AS name,
                ship_positions.longitude,
                ship_positions.latitude,
                ship_positions.recorded_at
            FROM ships
            JOIN ship_positions
                ON ship_positions.ship_id = ships.id
            WHERE ship_positions.recorded_at < :end_at
            ORDER BY
                ships.id,
                ship_positions.recorded_at,
                ship_positions.id
            """
        ),
        {"end_at": end_at},
    ).mappings().all()

    if not rows:
        return StraitPassageResult(
            status="no_data",
            closure_at=closure_at,
            end_at=end_at,
            query_summary=QuerySummary(
                position_count=0,
                matched_ship_count=0,
                passage_count=0,
                uncertain_candidate_count=0,
                coverage_start=None,
                coverage_end=None,
                truncated=False,
            ),
            limitations=["窗口之前及窗口内无任何报位，无法判定，不能解释为零匹配"],
        )

    timestamps = [row["recorded_at"] for row in rows]
    coverage_start = min(timestamps)
    coverage_end = max(timestamps)

    limitations: list[str] = []

    window_position_count = sum(
        1 for row in rows if closure_at <= row["recorded_at"] < end_at
    )
    if window_position_count == 0:
        limitations.append(
            f"[{closure_at.isoformat()}, {end_at.isoformat()}) 内无报位，"
            "覆盖不足，结果不能解释为零匹配"
        )

    # 按船分组（SQL 已按 ship_id, recorded_at, id 排序，保证乱序入库的报位按时间判定）
    by_ship: dict[int, dict] = {}
    for row in rows:
        entry = by_ship.setdefault(row["ship_id"], {"name": row["name"], "rows": []})
        entry["rows"].append(row)

    confirmed: list[PassageEvidence] = []
    uncertain: list[PassageEvidence] = []

    for ship_id, entry in by_ship.items():
        previous_side: str | None = None
        previous_fix: PositionFix | None = None
        for row in entry["rows"]:
            side = _side_of(row["longitude"], row["latitude"])
            if side is None:
                continue
            if previous_side is not None and side != previous_side:
                gap = row["recorded_at"] - previous_fix.recorded_at
                distance_km = _haversine_km(
                    previous_fix.longitude,
                    previous_fix.latitude,
                    row["longitude"],
                    row["latitude"],
                )
                implied_speed_kn = (
                    distance_km / 1.852 / (gap.total_seconds() / 3600)
                    if gap.total_seconds() > 0
                    else float("inf")
                )
                if gap > LONG_GAP_THRESHOLD:
                    reason = "long_gap"
                elif implied_speed_kn > JUMP_SPEED_KN:
                    reason = "jump"
                else:
                    reason = None
                if closure_at <= row["recorded_at"] < end_at:
                    item = PassageEvidence(
                        evidence_id="",  # 统一编号在收集后分配
                        ship_id=ship_id,
                        direction=f"{previous_side}_to_{side}",
                        start_fix=previous_fix,
                        completion_fix=PositionFix(
                            recorded_at=row["recorded_at"],
                            longitude=row["longitude"],
                            latitude=row["latitude"],
                        ),
                        observed_completion_at=row["recorded_at"],
                        uncertain=reason is not None,
                        uncertain_reason=reason,
                    )
                    (uncertain if reason else confirmed).append(item)
            previous_side = side
            previous_fix = PositionFix(
                recorded_at=row["recorded_at"],
                longitude=row["longitude"],
                latitude=row["latitude"],
            )

    confirmed.sort(key=lambda item: item.observed_completion_at)
    uncertain.sort(key=lambda item: item.observed_completion_at)
    for index, item in enumerate(confirmed, start=1):
        item.evidence_id = f"P{index}"
    for index, item in enumerate(uncertain, start=1):
        item.evidence_id = f"U{index}"

    # 船去重计数；同船多次穿越计 1 艘、次数单列；按首次完成时间排序
    passages_by_ship: dict[int, int] = {}
    first_completion: dict[int, datetime] = {}
    for item in confirmed:
        passages_by_ship[item.ship_id] = passages_by_ship.get(item.ship_id, 0) + 1
        if item.ship_id not in first_completion:
            first_completion[item.ship_id] = item.observed_completion_at
    ships = [
        ShipPassageSummary(
            ship_id=ship_id,
            name=by_ship[ship_id]["name"],
            passage_count=passages_by_ship[ship_id],
        )
        for ship_id in passages_by_ship
    ]
    ships.sort(key=lambda summary: first_completion[summary.ship_id])

    if uncertain:
        limitations.append(
            f"存在 {len(uncertain)} 条不确定候选（长间隔/疑似跳点），未计入确定结果"
        )
    if window_position_count == 0:
        status = "no_data"
    elif uncertain:
        status = "partial"
    else:
        status = "ok"
        if not confirmed:
            limitations.append("所选窗口内未观测到符合规则的完整通行（零匹配为有效结果）")

    return StraitPassageResult(
        status=status,
        closure_at=closure_at,
        end_at=end_at,
        ships=ships,
        evidence=confirmed,
        uncertain_candidates=uncertain,
        query_summary=QuerySummary(
            position_count=position_count,
            matched_ship_count=len(ships),
            passage_count=len(confirmed),
            uncertain_candidate_count=len(uncertain),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            truncated=False,
        ),
        limitations=limitations,
    )
