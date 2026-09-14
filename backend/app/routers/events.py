from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Event, News
from backend.app.schemas import EventResponse, EventNewsResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def get_events(db: Session = Depends(get_db)):
    # Reporting dates determine list order, not an inferred occurrence time.
    return db.scalars(select(Event).order_by(Event.publish_date_min.asc().nulls_last(), Event.event_id)).all()


@router.get("/{event_id}/news", response_model=list[EventNewsResponse])
def get_event_news(event_id: str, db: Session = Depends(get_db)):
    event_pk = db.scalar(select(Event.id).where(Event.event_id == event_id))
    if event_pk is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return db.scalars(select(News).where(News.event_id == event_pk).order_by(News.publish_date, News.story_id)).all()
