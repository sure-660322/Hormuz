"""Append reviewed news/events; audit by default, never recreate/clear tables."""
import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import insert, select, text, update

from backend.case_news_data import ARTICLES, CASE_NEWS, event_key, story_id


def import_news(connection):
    from backend.app.models import Event, News

    connection.execute(text("SELECT pg_advisory_xact_lock(477967700)"))
    inserted_news, inserted_events, news_ids, event_ids = [], [], {}, {}
    for key, article in ARTICLES.items():
        existing = connection.execute(select(News.__table__).where(News.canonical_url == article["url"])).mappings().first()
        if existing:
            if existing["story_id"] != story_id(key):
                raise ValueError("Canonical URL belongs to a different story; reconcile before import")
            news_ids[key] = existing["id"]
            continue
        values = dict(
            story_id=story_id(key), source_id=None, title=article["title"], url=article["url"], canonical_url=article["url"],
            publish_date=date.fromisoformat(article["date"]), language=article["language"], media_name=article["media"],
            perspective=article["perspective"], description_en=None, enrich_status=1,
            title_zh=article["title_zh"], summary_zh=article["summary_zh"], event_type="shipping",
            event_datetime=None, event_time_text=None, event_location_text="霍尔木兹海峡", event_region="霍尔木兹海峡",
            event_lat=None, event_lng=None, mentioned_vessels=article["vessels"], image_url=None, image_path=None,
            relevant=True, event_id=None,
        )
        news_ids[key] = connection.execute(insert(News.__table__).values(**values)).inserted_primary_key[0]
        inserted_news.append(key)
    for key, case in CASE_NEWS.items():
        sources = [ARTICLES[s] for s in case["sources"]]
        ids = [story_id(s) for s in case["sources"]]
        existing = connection.execute(select(Event.__table__).where(Event.event_id == case["event_id"])).mappings().first()
        if existing:
            if existing["event_key"] != event_key(key) or existing["story_ids"] != ids:
                raise ValueError("Existing event does not match reviewed association; refusing overwrite")
            event_ids[key] = existing["id"]
            continue
        values = dict(
            event_id=case["event_id"], event_key=event_key(key), title_zh=case["title"], summary_zh=case["summary"],
            event_type="shipping", event_datetime=None, event_time_text=f'{case["event_day"]}（报道描述的日期，未核定精确时刻）',
            event_location_text="霍尔木兹海峡", event_region="霍尔木兹海峡", event_lat=None, event_lng=None,
            mentioned_vessels=[case["name"]], image_url=None, image_path=None, event_points=None,
            geo_method=None, geo_note="精选案例，人工审核船名与CSV双标识；没有精确事件坐标，不作空间或因果自动关联。",
            coverage_count=len(ids), perspectives=list(dict.fromkeys(s["perspective"] for s in sources)), story_ids=ids,
            publish_date_min=min(date.fromisoformat(s["date"]) for s in sources),
            publish_date_max=max(date.fromisoformat(s["date"]) for s in sources),
        )
        event_ids[key] = connection.execute(insert(Event.__table__).values(**values)).inserted_primary_key[0]
        inserted_events.append(key)
    # Only our new records receive a primary FK. Shared citations are in Event.story_ids.
    for key in inserted_news:
        connection.execute(update(News.__table__).where(News.id == news_ids[key]).values(event_id=event_ids[ARTICLES[key]["primary_case"]]))
    return dict(inserted_news=len(inserted_news), inserted_events=len(inserted_events),
                news_ids=news_ids, event_ids=event_ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = dict(state="audit_only", articles=len(ARTICLES), events=len(CASE_NEWS),
                  sources=[a["url"] for a in ARTICLES.values()])
    if args.apply:
        if not args.database:
            parser.error("--apply requires an explicit --database; validate and back up first")
        from sqlalchemy import create_engine
        from backend.app.database import DATABASE_URL
        engine = create_engine(DATABASE_URL.set(database=args.database))
        with engine.begin() as connection:
            result.update(state="applied", **import_news(connection))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
