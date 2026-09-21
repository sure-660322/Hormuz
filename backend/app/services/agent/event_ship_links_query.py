"""AG-05 query_event_ship_links 的服务适配：事件—船舶关联的双向只读查询。

复用 P2 event-ship link 服务（get_event_ships / get_ship_events），只读
event_ship_links 派生层现有结果，不触发重建：
- event_id 方向（by_event）：mentioned（原文船名文本证据，ship_id 恒为空，
  与模拟船不按名称关联）与 observed（模拟轨迹时空邻近演示）按 link_type 分列；
- ship_id 方向（by_ship）：observed 反查；mentioned 类不指向模拟船，不参与反向；
- 未知 event_id / ship_id 抛 ValueError 进入纠正循环（提示先用 get_event_context /
  search_ships 检索），不当作零结果；
- 关联距离为构建时 EPSG:32640 平面投影近似，保留投影误差限制，
  不得标成精确 geography 度量。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.repositories import event_links as links_repo
from backend.app.repositories import tracks as tracks_repo
from backend.app.services import event_links as links_service

DEFAULT_LINK_TYPE = "observed"
LINK_TYPES = ("observed", "mentioned")
MAX_WINDOW = timedelta(hours=24)

MENTIONED_LIMITATION = (
    "mentioned 为新闻原文提及的真实船舶名称（文本证据），ship_id 恒为空；"
    "与数据库中模拟船不按名称关联，未认定同一实体"
)
OBSERVED_LIMITATION = (
    "observed 为模拟数据时空邻近演示（模拟轨迹在事件时间窗内进入构建半径），"
    "不构成真实因果"
)
PROJECTION_LIMITATION = (
    "关联距离为构建时 EPSG:32640 平面投影近似（跨 UTM 带存在失真），"
    "不是精确地理度量，不得标成已修复的 geography 度量"
)
TIME_PRECISION_LIMITATION = (
    "事件时间精度：event_datetime 缺失时按 event_time_text / 报道日期叙述，"
    "不虚构精确发生时刻"
)


def _parse_direction_args(args: dict) -> tuple[str | None, int | None]:
    """event_id 与 ship_id 必须且只能提供一个。"""
    event_id = args.get("event_id")
    ship_id = args.get("ship_id")
    if (event_id is None) == (ship_id is None):
        raise ValueError("event_id 与 ship_id 必须且只能提供一个")
    if event_id is not None:
        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id 必须是非空字符串（如 evt_001）")
        return event_id.strip(), None
    if not isinstance(ship_id, int) or isinstance(ship_id, bool):
        raise ValueError("ship_id 必须是整数；可先用 search_ships 按船名检索")
    return None, ship_id


def _parse_link_type(args: dict) -> str:
    link_type = args.get("link_type")
    if link_type is None:
        return DEFAULT_LINK_TYPE
    if not isinstance(link_type, str) or link_type not in LINK_TYPES:
        raise ValueError(f"link_type 必须是 {'/'.join(LINK_TYPES)} 之一")
    return link_type


def _parse_window_args(args: dict) -> tuple[datetime | None, datetime | None]:
    """start_at/end_at 仅按船反查方向可用：成对、带时区、≤24 小时。"""
    raw_start = args.get("start_at")
    raw_end = args.get("end_at")
    if (raw_start is None) != (raw_end is None):
        raise ValueError("start_at 与 end_at 必须同时提供或同时省略")
    if raw_start is None:
        return None, None
    if not isinstance(raw_start, str) or not isinstance(raw_end, str):
        raise ValueError("start_at/end_at 必须是 ISO 8601 字符串")
    try:
        start = datetime.fromisoformat(raw_start)
        end = datetime.fromisoformat(raw_end)
    except ValueError:
        raise ValueError("start_at/end_at 无法解析为 ISO 8601 时间") from None
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start_at 必须带时区（统一 UTC）")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end_at 必须带时区（统一 UTC）")
    if not start < end:
        raise ValueError("start_at 必须早于 end_at")
    if end - start > MAX_WINDOW:
        raise ValueError("查询窗口不能超过 24 小时，请缩小范围或分窗查询")
    return start, end


def _event_direction(db: Session, event_id: str, link_type: str) -> dict:
    event = links_repo.fetch_event_by_id(db, event_id)
    if event is None:
        raise ValueError(
            f"事件 {event_id} 不存在；请先用 get_event_context 按关键字检索确认事件 ID"
        )
    result = links_service.get_event_ships(db, event_id)
    links = [item for item in result["links"] if item["link_type"] == link_type]

    limitations = [PROJECTION_LIMITATION, TIME_PRECISION_LIMITATION]
    limitations.append(MENTIONED_LIMITATION if link_type == "mentioned" else OBSERVED_LIMITATION)
    if link_type == "observed":
        limitations.append(
            "observed 关联要求事件有代表坐标与时间窗覆盖；事件无坐标/时间时不会产生"
            " observed 关联，零条仅表示派生层内无此类关联"
        )

    return {
        "status": "ok" if links else "no_data",
        "direction": "by_event",
        "event_id": result["event_id"],
        "title_zh": result["title_zh"],
        "link_type": link_type,
        "links": links,
        "returned_count": len(links),
        "built_at": result["built_at"],
        "params": result["params"],
        "limitations": limitations,
    }


def _ship_direction(
    db: Session, ship_id: int, start: datetime | None, end: datetime | None
) -> dict:
    ship = tracks_repo.fetch_ship(db, ship_id)
    if ship is None:
        raise ValueError(
            f"ship_id={ship_id} 不存在；请先用 search_ships 按船名检索确认船 ID"
        )
    from_raw = start.isoformat() if start else None
    to_raw = end.isoformat() if end else None
    result = links_service.get_ship_events(db, ship_id, from_raw, to_raw)
    events = result["observed"]

    return {
        "status": "ok" if events else "no_data",
        "direction": "by_ship",
        "ship_id": ship_id,
        "ship_name": ship["name"],
        "link_type": "observed",
        "window": [start, end] if start else None,
        "events": events,
        "returned_count": len(events),
        "built_at": result["built_at"],
        "limitations": [
            OBSERVED_LIMITATION,
            PROJECTION_LIMITATION,
            TIME_PRECISION_LIMITATION,
            "mentioned 类关联不指向模拟船，不参与按船反查；"
            "原文船名提及见事件方向的 link_type=mentioned 查询",
            "未提供时间窗时按整个已构建批次反查",
        ],
    }


def run_event_ship_links_query(db: Session, args: dict) -> dict:
    """执行 query_event_ship_links：校验参数 → 复用 event-ship link 服务。"""
    if not isinstance(args, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    event_id, ship_id = _parse_direction_args(args)
    link_type = _parse_link_type(args)
    start, end = _parse_window_args(args)

    if event_id is not None:
        if start is not None:
            raise ValueError("时间窗仅用于按船反查方向（ship_id）；按事件查询请勿提供时间窗")
        return _event_direction(db, event_id, link_type)

    # ship_id 反查方向
    if link_type == "mentioned":
        raise ValueError(
            "mentioned 类关联不指向模拟船，不能按 ship_id 反查；"
            "请改用 event_id 方向查询原文提及船名"
        )
    return _ship_direction(db, ship_id, start, end)
