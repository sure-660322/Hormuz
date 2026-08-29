from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Ship, ShipPosition
from backend.app.schemas import ShipResponse, ShipPositionResponse


router = APIRouter(
    prefix="/ships",
    tags=["ships"],
)

@router.get("",response_model=list[ShipResponse])
def get_ships(db:Session = Depends(get_db)):
    statement = select(Ship).order_by(Ship.id)
    ships = db.scalars(statement).all()

    return ships
@router.get(
    "/{ship_id}/positions",
    response_model=list[ShipPositionResponse],
)
def get_ship_positions(
    ship_id:int,
    db:Session = Depends(get_db),
):
    statement =(
        select(ShipPosition)
        .where(ShipPosition.ship_id == ship_id)
        .order_by(ShipPosition.recorded_at)
    )

    positions = db.scalars(statement).all()

    return positions
