"""船舶检索工具（智能体工具 search_ships 的后端实现）。

按关键字模糊匹配教学模拟批次船舶的 name/MMSI/IMO/callsign/船型/船旗，
纯只读、参数化查询；不执行模型生成的 SQL。

边界：返回的是教学模拟船（ship_positions.data_source=simulation），
不得与真实新闻事件中的船舶按名称关联。
"""
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Ship, ShipPosition
from backend.app.services.agent.config import SCHEMA_VERSION

DEFAULT_LIMIT = 10
MAX_LIMIT = 20
MAX_KEYWORD_LENGTH = 100


@dataclass
class ShipSearchMatch:
    ship_id: int
    name: str
    mmsi: str
    imo: str | None
    callsign: str | None
    ship_type: str
    flag: str | None
    length_m: float | None
    width_m: float | None


@dataclass
class ShipSearchResult:
    status: str  # ok（含零命中）/ no_match
    schema_version: str = SCHEMA_VERSION
    keyword: str = ""
    matches: list[ShipSearchMatch] = field(default_factory=list)
    returned_count: int = 0
    matched_count: int = 0  # 命中总数（可能多于返回数，见 truncated）
    truncated: bool = False  # 命中数超过 limit，仅返回前 limit 条
    limitations: list[str] = field(default_factory=list)


def search_ships(db: Session, keyword: str, limit: int = DEFAULT_LIMIT) -> ShipSearchResult:
    """按关键字检索船舶。关键字去除首尾空白后 1–100 字符；limit 1–20。"""
    keyword = keyword.strip()
    if not 1 <= len(keyword) <= MAX_KEYWORD_LENGTH:
        raise ValueError(f"keyword 去除首尾空白后须为 1–{MAX_KEYWORD_LENGTH} 字符")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit 必须在 1–{MAX_LIMIT} 之间")

    pattern = f"%{keyword}%"
    # 仅返回教学模拟批次中实际有报位的船，避免检索出无轨迹的残留记录
    has_positions = (
        select(ShipPosition.ship_id)
        .where(ShipPosition.data_source == "simulation")
        .distinct()
    )
    rows = db.scalars(
        select(Ship)
        .where(Ship.id.in_(has_positions))
        .where(
            Ship.name.ilike(pattern)
            | Ship.mmsi.ilike(pattern)
            | Ship.imo.ilike(pattern)
            | Ship.callsign.ilike(pattern)
            | Ship.ship_type.ilike(pattern)
            | Ship.flag.ilike(pattern)
        )
        .order_by(Ship.name, Ship.id)
        .limit(limit + 1)  # 多取 1 条用于判断是否截断
    ).all()

    truncated = len(rows) > limit
    matches = [
        ShipSearchMatch(
            ship_id=ship.id,
            name=ship.name,
            mmsi=ship.mmsi,
            imo=ship.imo,
            callsign=ship.callsign,
            ship_type=ship.ship_type,
            flag=ship.flag,
            length_m=ship.length_m,
            width_m=ship.width_m,
        )
        for ship in rows[:limit]
    ]

    limitations = [
        "检索范围为教学模拟批次的模拟船（ship_positions.data_source=simulation），"
        "不得与真实新闻事件中的船舶按名称关联为同一实体"
    ]
    if truncated:
        limitations.append(f"命中数超过上限 {limit}，仅返回前 {limit} 条，可更换更精确的关键字")

    return ShipSearchResult(
        status="ok" if matches else "no_match",
        keyword=keyword,
        matches=matches,
        returned_count=len(matches),
        matched_count=len(rows),
        truncated=truncated,
        limitations=limitations,
    )
