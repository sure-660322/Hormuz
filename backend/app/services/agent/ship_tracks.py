"""单船轨迹查询工具（智能体工具 get_ship_track 的后端实现）。

查询指定船只在 [start_at, end_at) 内的全部报位，按时间排序。
纯只读、参数化查询；不做穿越判定（那是 query_strait_passages 的口径）。

边界：轨迹为 nnu_ais 来源的历史 AIS 实测报位，覆盖与授权尚未核实。
"""
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models import Ship, ShipPosition
from backend.app.services.agent.config import MAX_POSITIONS_READ, MAX_WINDOW, SCHEMA_VERSION, SHIP_DATA_SOURCE


@dataclass
class TrackFix:
    recorded_at: datetime
    longitude: float
    latitude: float
    speed: float  # 节
    course: float  # 度
    nav_status: str | None


@dataclass
class ShipTrackResult:
    status: str  # ok / no_data（窗口内无报位）/ not_found（船 ID 不存在）
    schema_version: str = SCHEMA_VERSION
    ship_id: int = 0
    ship_name: str = ""
    start_at: datetime = None
    end_at: datetime = None
    fixes: list[TrackFix] = field(default_factory=list)
    fix_count: int = 0
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    truncated: bool = False  # 恒为 False；读取超限直接报错，不截断
    limitations: list[str] = field(default_factory=list)


def _validate(start_at: datetime, end_at: datetime) -> None:
    if start_at.tzinfo is None or start_at.utcoffset() is None:
        raise ValueError("start_at 必须包含显式时区（带时区的 ISO 8601 时间）")
    if end_at.tzinfo is None or end_at.utcoffset() is None:
        raise ValueError("end_at 必须包含显式时区（带时区的 ISO 8601 时间）")
    if not start_at < end_at:
        raise ValueError("start_at 必须早于 end_at")
    if end_at - start_at > MAX_WINDOW:
        raise ValueError(f"查询窗口不能超过 24 小时，请缩小范围（当前 {end_at - start_at}）")


def get_ship_track(
    db: Session,
    ship_id: int,
    start_at: datetime,
    end_at: datetime,
) -> ShipTrackResult:
    """查询单船在 [start_at, end_at) 内的轨迹报位。船不存在返回 not_found，不抛错。"""
    _validate(start_at, end_at)

    ship = db.get(Ship, ship_id)
    if ship is None:
        return ShipTrackResult(
            status="not_found",
            ship_id=ship_id,
            start_at=start_at,
            end_at=end_at,
            limitations=[f"数据库中不存在船 ID {ship_id}；先用 search_ships 确认船名与 ID"],
        )

    fix_count = db.scalar(
        select(func.count(ShipPosition.id)).where(
            ShipPosition.ship_id == ship_id,
            ShipPosition.data_source == SHIP_DATA_SOURCE,
            ShipPosition.recorded_at >= start_at,
            ShipPosition.recorded_at < end_at,
        )
    ) or 0
    if fix_count > MAX_POSITIONS_READ:
        raise ValueError(
            f"该船窗口内报位数约 {fix_count}，超过上限 {MAX_POSITIONS_READ}，"
            "请缩小查询范围，不能截断后宣称无数据"
        )

    rows = db.scalars(
        select(ShipPosition)
        .where(
            ShipPosition.ship_id == ship_id,
            ShipPosition.data_source == SHIP_DATA_SOURCE,
            ShipPosition.recorded_at >= start_at,
            ShipPosition.recorded_at < end_at,
        )
        .order_by(ShipPosition.recorded_at, ShipPosition.id)
    ).all()

    fixes = [
        TrackFix(
            recorded_at=row.recorded_at,
            longitude=row.longitude,
            latitude=row.latitude,
            speed=row.speed,
            course=row.course,
            nav_status=row.nav_status,
        )
        for row in rows
    ]

    limitations = [
        "轨迹为 nnu_ais 来源的历史 AIS 实测报位；来源授权与覆盖尚未核实，不能据缺报推断船舶不存在"
    ]
    if not fixes:
        status = "no_data"
        limitations.append(
            f"[{start_at.isoformat()}, {end_at.isoformat()}) 内该船无报位，"
            "可能是数据覆盖不足，不能解释为该时段无此船"
        )
    else:
        status = "ok"

    return ShipTrackResult(
        status=status,
        ship_id=ship_id,
        ship_name=ship.name,
        start_at=start_at,
        end_at=end_at,
        fixes=fixes,
        fix_count=len(fixes),
        coverage_start=fixes[0].recorded_at if fixes else None,
        coverage_end=fixes[-1].recorded_at if fixes else None,
        truncated=False,
        limitations=limitations,
    )
