"""P1 track API: derived ship_tracks -> GeoJSON + speed series (plan section 6).

GET /api/tracks/{ship_id}?from=&to=&level=full|simplified

full:        whole segments intersecting the window; geometry vertices and the
             [[epoch_s, kn], ...] speed series are aligned one-to-one (both come
             from the same instant set, computed in the database).
simplified:  time-bucket decimation in the database (bucket_seconds, default 300);
             points inside track gaps are not produced (sampling is per segment).

from/to are optional; together they must be timezone-aware ISO 8601, from < to,
window <= 24 h. Without them the ship's whole derived coverage is considered
(full level then answers every stored segment).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services import tracks as tracks_service

router = APIRouter(prefix="/api", tags=["tracks"])


def invalid(message: str):
    raise HTTPException(
        status_code=422,
        detail={"code": "INVALID_REQUEST", "message": message, "request_id": str(uuid.uuid4())},
    )


@router.get("/tracks/{ship_id}")
def get_ship_tracks(
    ship_id: int,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    level: str = Query(default="full"),
    bucket_seconds: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return tracks_service.get_ship_tracks(db, ship_id, from_, to, level, bucket_seconds)
    except ValueError as exc:
        invalid(str(exc))
