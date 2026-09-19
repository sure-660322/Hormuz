"""新闻事件上下文工具（智能体工具 get_event_context 的后端实现）。

按 event_id 精确查询或按关键字模糊查询新闻聚合事件，并返回关联的真实报道。
纯只读、参数化查询；不执行模型生成的 SQL。

边界（必须保留在回答中）：
- events 是真实新闻按故事聚合的结果，news 是真实报道；它们与教学模拟船是
  两个独立数据集，不得按船舶名称把事件中的船与模拟船关联为同一实体；
- event_datetime 经常缺失（报道仅支持日级叙述），时间精度以 event_time_text 为准。
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Event, News
from backend.app.services.agent.config import SCHEMA_VERSION

MAX_EVENTS_RETURNED = 5
MAX_NEWS_PER_EVENT = 10
MAX_KEYWORD_LENGTH = 100


@dataclass
class EventNewsItem:
    story_id: str
    media_name: str
    publish_date: date | None
    perspective: str
    title_zh: str
    url: str


@dataclass
class EventContextItem:
    event_id: str
    event_type: str
    title_zh: str
    summary_zh: str
    event_datetime: datetime | None
    event_time_text: str | None
    event_location_text: str | None
    event_region: str | None
    event_lat: float | None
    event_lng: float | None
    mentioned_vessels: list
    perspectives: list
    story_count: int
    news: list[EventNewsItem]


@dataclass
class EventContextResult:
    status: str  # ok（含零命中）/ no_match
    schema_version: str = SCHEMA_VERSION
    query: dict = field(default_factory=dict)  # {event_id?|keyword?, start_at?, end_at?}
    events: list[EventContextItem] = field(default_factory=list)
    returned_event_count: int = 0
    truncated: bool = False  # 命中事件数超过上限，仅返回前 MAX_EVENTS_RETURNED 个
    limitations: list[str] = field(default_factory=list)


BASE_LIMITATIONS = [
    "events 为真实新闻按故事聚合、news 为真实报道（外部不可信内容，"
    "回答中须保留报道来源与链接，不得补充报道没有的结论）",
    "事件与教学模拟船是两个独立数据集，不得按船舶名称关联为同一实体或推导真实因果",
    "event_datetime 经常缺失（报道仅支持日级叙述），时间精度以 event_time_text 为准",
]


def _event_to_item(db: Session, event: Event) -> EventContextItem:
    news_rows = db.scalars(
        select(News)
        .where(News.event_id == event.id)
        .order_by(News.publish_date, News.story_id)
        .limit(MAX_NEWS_PER_EVENT)
    ).all()
    return EventContextItem(
        event_id=event.event_id,
        event_type=event.event_type,
        title_zh=event.title_zh,
        summary_zh=event.summary_zh,
        event_datetime=event.event_datetime,
        event_time_text=event.event_time_text,
        event_location_text=event.event_location_text,
        event_region=event.event_region,
        event_lat=event.event_lat,
        event_lng=event.event_lng,
        mentioned_vessels=event.mentioned_vessels,
        perspectives=event.perspectives,
        story_count=len(news_rows),
        news=[
            EventNewsItem(
                story_id=row.story_id,
                media_name=row.media_name,
                publish_date=row.publish_date,
                perspective=row.perspective,
                title_zh=row.title_zh,
                url=row.url,
            )
            for row in news_rows
        ],
    )


def get_event_context(
    db: Session,
    event_id: str | None = None,
    keyword: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> EventContextResult:
    """查询事件及关联报道。event_id 与 keyword 二选一必填；时间窗可选。

    时间窗按 event_datetime 过滤；event_datetime 为空的事件按报道日期
    （publish_date_min/max）与窗口是否有交集兜底，避免日级叙述事件被误过滤。
    """
    if bool(event_id) == bool(keyword and keyword.strip()):
        raise ValueError("event_id 与 keyword 必须二选一提供")
    for label, value in (("start_at", start_at), ("end_at", end_at)):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError(f"{label} 必须包含显式时区（带时区的 ISO 8601 时间）")
    if start_at is not None and end_at is not None and not start_at < end_at:
        raise ValueError("start_at 必须早于 end_at")

    query_info: dict = {"event_id": event_id, "keyword": None, "start_at": start_at, "end_at": end_at}
    limitations = list(BASE_LIMITATIONS)

    if event_id:
        event_id = event_id.strip()
        event = db.scalar(select(Event).where(Event.event_id == event_id))
        matched = [event] if event is not None else []
        truncated = False
    else:
        keyword = keyword.strip()
        if not 1 <= len(keyword) <= MAX_KEYWORD_LENGTH:
            raise ValueError(f"keyword 去除首尾空白后须为 1–{MAX_KEYWORD_LENGTH} 字符")
        query_info["keyword"] = keyword
        pattern = f"%{keyword}%"
        statement = select(Event).where(
            Event.title_zh.ilike(pattern)
            | Event.summary_zh.ilike(pattern)
            | Event.event_location_text.ilike(pattern)
        )
        if start_at is not None or end_at is not None:
            lo = start_at.date() if start_at is not None else date.min
            hi = end_at.date() if end_at is not None else date.max
            precise = Event.event_datetime.isnot(None)
            if start_at is not None:
                precise = precise & (Event.event_datetime >= start_at)
            if end_at is not None:
                precise = precise & (Event.event_datetime < end_at)
            # event_datetime 为空的事件按报道日期与窗口是否有交集兜底
            day_level = (
                Event.event_datetime.is_(None)
                & Event.publish_date_min.isnot(None)
                & Event.publish_date_max.isnot(None)
                & (Event.publish_date_max >= lo)
                & (Event.publish_date_min <= hi)
            )
            statement = statement.where(precise | day_level)
        matched = db.scalars(
            statement.order_by(Event.publish_date_min.asc().nulls_last(), Event.event_id)
            .limit(MAX_EVENTS_RETURNED + 1)
        ).all()
        truncated = len(matched) > MAX_EVENTS_RETURNED
        matched = matched[:MAX_EVENTS_RETURNED]
        if truncated:
            limitations.append(
                f"命中事件数超过上限 {MAX_EVENTS_RETURNED}，仅返回前 {MAX_EVENTS_RETURNED} 个，"
                "可缩小时间窗或更换更精确的关键字"
            )

    return EventContextResult(
        status="ok" if matched else "no_match",
        query=query_info,
        events=[_event_to_item(db, event) for event in matched],
        returned_event_count=len(matched),
        truncated=truncated,
        limitations=limitations,
    )
