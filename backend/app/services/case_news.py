"""Database-backed, reviewed news entries; no automatic name-only matching."""
from sqlalchemy import select

from backend.app.models import Event, News
from backend.case_news_data import ARTICLES, CASE_NEWS, event_key, story_id


def case_news_entries(db):
    expected_ids = [c["event_id"] for c in CASE_NEWS.values()]
    events = {e.event_id: e for e in db.scalars(select(Event).where(Event.event_id.in_(expected_ids))).all()}
    stories = {n.story_id: n for n in db.scalars(select(News).where(News.story_id.in_(
        list({story_id(s) for c in CASE_NEWS.values() for s in c["sources"]})
    ))).all()}
    entries = []
    for key, spec in CASE_NEWS.items():
        event = events.get(spec["event_id"])
        # Only the reviewed relationship is eligible, not a same-name arbitrary event.
        ready = bool(event and event.event_key == event_key(key) and event.story_ids == [story_id(s) for s in spec["sources"]]
                     and all(story_id(s) in stories and stories[story_id(s)].canonical_url == ARTICLES[s]["url"]
                             for s in spec["sources"]))
        articles = [stories[story_id(s)] for s in spec["sources"]] if ready else []
        entries.append(dict(
            case_id=key, event_id=spec["event_id"], title_zh=event.title_zh if ready else spec["title"],
            summary_zh=event.summary_zh if ready else "案例新闻证据尚未导入此环境。",
            vessel_name=spec["name"], mmsi=spec["mmsi"], imo=spec["imo"], available=ready,
            event_day=spec["event_day"],
            articles=[dict(story_id=n.story_id, title=n.title_zh, media=n.media_name, publish_date=n.publish_date,
                           url=n.canonical_url, summary=n.summary_zh) for n in articles],
        ))
    return entries
