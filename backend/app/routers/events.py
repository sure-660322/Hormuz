from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Event
from backend.app.schemas import EventResponse

router = APIRouter(
    prefix="/events",
    tags=["events"],
)

@router.get("",response_model=list[EventResponse])
def get_events(db:Session = Depends(get_db)):
    statement = select(Event).order_by(
        Event.occurred_at,
        Event.id,
    )

    events = db.scalars(statement).all()

    return events