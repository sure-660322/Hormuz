from fastapi import APIRouter, Depends
from math import ceil
from sqlalchemy import exists, func, select, text
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
    # Curated single-vessel supplements have their own replay window.
    # Keep them out of the default fleet coverage; do not stretch across gaps.
    normal_scope = text("NOT EXISTS (SELECT 1 FROM ais_import_batches b WHERE b.id = ship_positions.source_batch_id AND b.source_file LIKE 'case/%')")
    position_summary = db.execute(
        select(
            func.min(ShipPosition.recorded_at),
            func.max(ShipPosition.recorded_at),
            func.count(ShipPosition.id),
        ).where(normal_scope)
    ).one()

    ship_count = db.scalar(select(func.count(Ship.id))) or 0
    has_non_simulated_positions = db.scalar(
        select(exists().where(ShipPosition.data_source != "simulation"))
    ) or False
    available = db.execute(text("""
        SELECT to_regclass('public.events') IS NOT NULL AS has_events,
               to_regclass('public.ship_tracks') IS NOT NULL
               AND to_regclass('public.ship_dwell') IS NOT NULL
               AND to_regclass('public.encounters') IS NOT NULL
               AND to_regclass('public.track_build_manifest') IS NOT NULL AS has_derived
    """)).one()
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
        is_simulated=bool(position_summary[2]) and not has_non_simulated_positions,
        has_events=available.has_events,
        has_derived=available.has_derived,
    )
