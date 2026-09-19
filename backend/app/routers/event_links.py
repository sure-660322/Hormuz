"""P2 event-ship link APIs (plan section 6).

GET /api/events/{event_id}/ships  — links for one event (business event_id).
GET /api/ships/{ship_id}/events?from=&to= — observed links for one ship.

mentioned and observed are always separate; observed links are simulation-only
and carry an explicit demo disclaimer (never real-world causality).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services import event_links as links_service

router = APIRouter(prefix="/api", tags=["event-links"])


def invalid(message: str):
    raise HTTPException(
        status_code=422,
        detail={"code": "INVALID_REQUEST", "message": message, "request_id": str(uuid.uuid4())},
    )


@router.get("/events/{event_id}/ships")
def get_event_ships(event_id: str, db: Session = Depends(get_db)):
    return links_service.get_event_ships(db, event_id)


@router.get("/ships/{ship_id}/events")
def get_ship_events(
    ship_id: int,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return links_service.get_ship_events(db, ship_id, from_, to)
    except ValueError as exc:
        invalid(str(exc))
