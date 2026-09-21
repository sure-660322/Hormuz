"""P3 dwell API: derived ship_dwell -> GeoJSON FeatureCollection (plan section 6).

GET /api/dwell?kind=at_anchor|drift|slow_transit&from=&to=

kind/from/to are optional; from/to together must be timezone-aware ISO 8601,
from < to, window <= 24 h. Rows are precomputed (never computed on the request
path); the response carries the threshold snapshot and freshness (stale).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services import dwell as dwell_service

router = APIRouter(prefix="/api", tags=["dwell"])


def invalid(message: str):
    raise HTTPException(
        status_code=422,
        detail={"code": "INVALID_REQUEST", "message": message, "request_id": str(uuid.uuid4())},
    )


@router.get("/dwell")
def get_dwell(
    kind: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return dwell_service.get_dwell(db, kind, from_, to)
    except ValueError as exc:
        invalid(str(exc))
