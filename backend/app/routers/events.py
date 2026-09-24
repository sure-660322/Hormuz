import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import PROJECT_ROOT, get_db
from backend.app.models import Event, News
from backend.app.schemas import EventResponse, EventNewsResponse

router = APIRouter(prefix="/events", tags=["events"])

_COVER_PATH = re.compile(r"images/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|avif)\Z", re.IGNORECASE)
_COVER_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".avif": "image/avif"}


def _event_cover_file(image_path: str | None) -> Path:
    if not image_path or not _COVER_PATH.fullmatch(image_path):
        raise HTTPException(status_code=404, detail="事件配图不存在")
    configured_root = os.getenv("NEWS_IMAGE_ROOT")
    root = (Path(configured_root).expanduser() if configured_root else PROJECT_ROOT.parent / "news_raw_data").resolve()
    image = (root / image_path).resolve()
    if not image.is_relative_to(root) or not image.is_file():
        raise HTTPException(status_code=404, detail="事件配图不存在")
    return image


@router.get("", response_model=list[EventResponse])
def get_events(db: Session = Depends(get_db)):
    # Reporting dates determine list order, not an inferred occurrence time.
    return db.scalars(select(Event).order_by(Event.publish_date_min.asc().nulls_last(), Event.event_id)).all()


@router.get("/{event_id}/cover", response_class=FileResponse)
def get_event_cover(event_id: str, db: Session = Depends(get_db)):
    image_path = db.scalar(select(Event.image_path).where(Event.event_id == event_id))
    image = _event_cover_file(image_path)
    return FileResponse(
        image,
        media_type=_COVER_MIME[image.suffix.lower()],
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{event_id}/news", response_model=list[EventNewsResponse])
def get_event_news(event_id: str, db: Session = Depends(get_db)):
    event_pk = db.scalar(select(Event.id).where(Event.event_id == event_id))
    if event_pk is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return db.scalars(select(News).where(News.event_id == event_pk).order_by(News.publish_date, News.story_id)).all()
