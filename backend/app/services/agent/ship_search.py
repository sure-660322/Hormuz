"""船舶检索工具（智能体工具 search_ships 的后端实现）。

按关键字模糊匹配有真实 AIS 报位的船舶 name/MMSI/IMO/callsign/船型/船旗，
纯只读、参数化查询；不执行模型生成的 SQL。

边界：返回的是 nnu_ais 来源的历史 AIS 船舶，不能仅凭名称与新闻实体关联。
"""
from dataclasses import dataclass, field

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from backend.app.models import Ship, ShipPosition
from backend.app.services.agent.config import SCHEMA_VERSION, SHIP_DATA_SOURCE

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

    literal_keyword = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{literal_keyword}%"
    # 先按船舶元数据检索，再用关联 EXISTS 核对该来源确有报位。
    has_positions = exists(
        select(ShipPosition.id).where(
            ShipPosition.ship_id == Ship.id,
            ShipPosition.data_source == SHIP_DATA_SOURCE,
        )
    )
    query = (
        select(Ship)
        .where(has_positions)
        .where(
            Ship.name.ilike(pattern, escape="\\")
            | Ship.mmsi.ilike(pattern, escape="\\")
            | Ship.imo.ilike(pattern, escape="\\")
            | Ship.callsign.ilike(pattern, escape="\\")
            | Ship.ship_type.ilike(pattern, escape="\\")
            | Ship.flag.ilike(pattern, escape="\\")
        )
    )
    rows = db.scalars(query.order_by(Ship.name, Ship.id).limit(limit + 1)).all()

    truncated = len(rows) > limit
    matched_count = db.scalar(
        select(func.count()).select_from(query.subquery())
    ) if truncated else len(rows)
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
        "检索范围为已有 nnu_ais 历史 AIS 报位的船；来源授权与覆盖尚未核实。"
        "新闻中的船舶须另行核对 MMSI/IMO 等标识，名称相同不足以认定同一实体"
    ]
    if truncated:
        limitations.append(f"命中数超过上限 {limit}，仅返回前 {limit} 条，可更换更精确的关键字")

    return ShipSearchResult(
        status="ok" if matches else "no_match",
        keyword=keyword,
        matches=matches,
        returned_count=len(matches),
        matched_count=matched_count,
        truncated=truncated,
        limitations=limitations,
    )
