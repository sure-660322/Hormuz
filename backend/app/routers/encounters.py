"""P4 encounter APIs (plan section 6).

GET  /api/encounters?from=&to=&max_distance_nm= — precomputed pair list.
POST /api/encounters/analyze — controlled synchronous rebuild with body
     {distance_nm, overlap_min, sample_seconds}; writes the encounters layer
     and a track_build_manifest row.

Encounters are spatio-temporal proximity on simulated tracks only; proximity
is not interaction and never real-world causality.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services import encounters as enc_service

router = APIRouter(prefix="/api/encounters", tags=["encounters"])


def invalid(message: str):
    raise HTTPException(
        status_code=422,
        detail={"code": "INVALID_REQUEST", "message": message, "request_id": str(uuid.uuid4())},
    )


class AnalyzeRequest(BaseModel):
    distance_nm: float = Field(default=3.0, gt=0, le=50)
    overlap_min: int = Field(default=30, gt=0, le=24 * 60)
    sample_seconds: int = Field(default=60, ge=30, le=3600)


@router.get("")
def get_encounters(
    from_: Optional[str] = Query(default=None, alias="from"),
    to: Optional[str] = Query(default=None),
    max_distance_nm: Optional[float] = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        return enc_service.list_encounters(db, from_, to, max_distance_nm)
    except ValueError as exc:
        invalid(str(exc))


@router.post("/analyze")
def post_analyze(body: AnalyzeRequest, db: Session = Depends(get_db)):
    try:
        return enc_service.analyze_encounters(db, body.distance_nm, body.overlap_min, body.sample_seconds)
    except ValueError as exc:
        invalid(str(exc))
