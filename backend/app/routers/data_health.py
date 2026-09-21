"""P5 data-health API: source coverage + derived-layer freshness (plan section 6).

GET /api/data-health — no parameters; answers what exists, how fresh each
derived layer is, and which parameters each build used.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services import data_health as health_service

router = APIRouter(prefix="/api", tags=["data-health"])


@router.get("/data-health")
def get_data_health(db: Session = Depends(get_db)):
    return health_service.get_data_health(db)
