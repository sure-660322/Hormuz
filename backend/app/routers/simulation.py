from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Event, Ship, ShipPosition
from backend.app.schemas import SimulationMetaResponse


router = APIRouter(
    prefix="/simulation",
    tags=["simulation"],
)


@router.get("/meta", response_model=SimulationMetaResponse)
def get_simulation_meta(db: Session = Depends(get_db)):
    position_summary = db.execute(
        select(
            func.min(ShipPosition.recorded_at),
            func.max(ShipPosition.recorded_at),
            func.count(ShipPosition.id),
            func.count(distinct(ShipPosition.recorded_at)),
        )
    ).one()

    ship_count = db.scalar(select(func.count(Ship.id))) or 0
    event_count = db.scalar(select(func.count(Event.id))) or 0

    return SimulationMetaResponse(
        start_at=position_summary[0],
        end_at=position_summary[1],
        frame_interval_seconds=300,
        frame_count=position_summary[3],
        ship_count=ship_count,
        position_count=position_summary[2],
        event_count=event_count,
        is_simulated=True,
    )
