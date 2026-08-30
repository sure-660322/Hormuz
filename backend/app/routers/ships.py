from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Ship, ShipPosition
from backend.app.schemas import (
    NearbyEventResponse,
    ShipMapResponse,
    ShipPositionResponse,
    ShipResponse,
)


router = APIRouter(
    prefix="/ships",
    tags=["ships"],
)

@router.get("",response_model=list[ShipResponse])
def get_ships(db:Session = Depends(get_db)):
    statement = select(Ship).order_by(Ship.id)
    ships = db.scalars(statement).all()

    return ships

@router.get("/map", response_model=list[ShipMapResponse])
def get_map_ships(db: Session = Depends(get_db)):
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (ships.id)
                ships.id,
                ships.mmsi,
                ships.name,
                ships.ship_type,
                ships.flag,
                ships.imo,
                ships.callsign,
                ship_positions.latitude,
                ship_positions.longitude,
                ship_positions.speed,
                ship_positions.course,
                ship_positions.heading,
                ship_positions.recorded_at
            FROM ships
            JOIN ship_positions
                ON ship_positions.ship_id = ships.id
            ORDER BY
                ships.id,
                ship_positions.recorded_at DESC,
                ship_positions.id DESC
            """
        )
    ).mappings().all()

    return rows

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

@router.get("/{ship_id}/nearby-events",response_model=list[NearbyEventResponse])
def get_nearby_events(
    ship_id:int,
    radius_km:float = Query(...,gt = 0, description="查询半径，单位公里，必须大于0"),
    db:Session = Depends(get_db),
):
    #查找指定船舶是否存在
    ship = db.get(Ship,ship_id)
    if ship is None:
        raise HTTPException(status_code=404,detail="船舶不存在")

    #获取该船的最新经纬度位置
    latest_loc = db.execute(
        text(
            """
            SELECT latitude,longitude
            FROM ship_positions
            WHERE ship_id = :ship_id
            ORDER BY recorded_at DESC
            LIMIT 1
            """
        ),
        {"ship_id": ship_id}
    ).first()

    if latest_loc is None:
        raise HTTPException(404,"该船没有位置记录")

    radius_m = radius_km * 1000.0
    rows = db.execute(
        text(
            """
            SELECT
                id,
                title,
                description,
                event_type,
                latitude,
                longitude,
                occurred_at,
                source_name,
                source_url,
                ST_Distance(
                    location,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                ) / 1000.0 AS distance_km
            FROM events
            WHERE ST_DWithin(
                location,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                :radius_m
            )
            ORDER BY distance_km
            """
        ),
        {"lon": latest_loc.longitude, "lat": latest_loc.latitude, "radius_m": radius_m},
    ).all()

    return rows