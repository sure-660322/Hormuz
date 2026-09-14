from fastapi import APIRouter, Depends
from math import ceil
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Ship, ShipPosition
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
        )
    ).one()

    ship_count = db.scalar(select(func.count(Ship.id))) or 0
    # News-derived events do not belong to the simulated ship replay.
    event_count = 0

    return SimulationMetaResponse(
        start_at=position_summary[0],
        end_at=position_summary[1],
        frame_interval_seconds=300,
        frame_count=(ceil((position_summary[1] - position_summary[0]).total_seconds() / 300) + 1
                     if position_summary[0] is not None else 0),
        ship_count=ship_count,
        position_count=position_summary[2],
        event_count=event_count,
        is_simulated=True,
    )
