from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas import (
    AisDatasetMetaResponse,
    AisMapShipResponse,
    AisPositionResponse,
    AisVesselResponse,
)


router = APIRouter(prefix="/ais", tags=["historical AIS"])

MAX_PLAYBACK_RANGE = timedelta(hours=24)
MAX_PLAYBACK_POINTS = 50_000


def require_timezone(value: datetime, parameter_name: str) -> None:
    if value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail=f"{parameter_name} 必须包含时区",
        )


def get_latest_dataset(db: Session):
    dataset = db.execute(
        text(
            """
            SELECT id, name, source_url, source_version, source_sha256,
                   start_at, end_at, vessel_count, record_count, coverage_note
            FROM ais_datasets
            ORDER BY imported_at DESC, id DESC
            LIMIT 1
            """
        )
    ).mappings().first()

    if dataset is None:
        raise HTTPException(status_code=404, detail="尚未导入 AIS 数据")

    return dataset


@router.get("/meta", response_model=AisDatasetMetaResponse)
def get_ais_meta(db: Session = Depends(get_db)):
    dataset = get_latest_dataset(db)
    return {
        "dataset_id": dataset["id"],
        "name": dataset["name"],
        "source_url": dataset["source_url"],
        "source_version": dataset["source_version"],
        "source_sha256": dataset["source_sha256"].strip(),
        "start_at": dataset["start_at"],
        "end_at": dataset["end_at"],
        "vessel_count": dataset["vessel_count"],
        "position_count": dataset["record_count"],
        "frame_interval_seconds": 300,
        "is_simulated": False,
        "coverage_note": dataset["coverage_note"],
    }


@router.get("/vessels", response_model=list[AisVesselResponse])
def get_ais_vessels(db: Session = Depends(get_db)):
    dataset = get_latest_dataset(db)
    return db.execute(
        text(
            """
            SELECT id, mmsi, name, ship_type, flag, destination,
                   draught, length, width, first_seen, last_seen
            FROM ais_vessels
            WHERE dataset_id = :dataset_id
            ORDER BY mmsi, id
            """
        ),
        {"dataset_id": dataset["id"]},
    ).mappings().all()


@router.get("/ships/map", response_model=list[AisMapShipResponse])
def get_ais_map_ships(
    at: datetime = Query(..., description="带时区的历史时刻"),
    db: Session = Depends(get_db),
):
    require_timezone(at, "at")
    dataset = get_latest_dataset(db)
    return db.execute(
        text(
            """
            SELECT v.id, v.mmsi, v.name, v.ship_type, v.flag,
                   v.destination, v.draught, v.length, v.width,
                   v.first_seen, v.last_seen,
                   p.id AS position_id, p.latitude, p.longitude,
                   p.speed, p.course, p.heading,
                   p.recorded_at, p.received_at
            FROM ais_vessels AS v
            JOIN LATERAL (
                SELECT id, latitude, longitude, speed, course, heading,
                       recorded_at, received_at
                FROM ais_positions
                WHERE vessel_id = v.id AND recorded_at <= :at
                ORDER BY recorded_at DESC, id DESC
                LIMIT 1
            ) AS p ON TRUE
            WHERE v.dataset_id = :dataset_id
            ORDER BY v.mmsi, v.id
            """
        ),
        {"dataset_id": dataset["id"], "at": at},
    ).mappings().all()


@router.get("/ships/playback", response_model=list[AisPositionResponse])
def get_ais_playback_positions(
    start_at: datetime = Query(..., description="带时区的窗口开始时间"),
    end_at: datetime = Query(..., description="带时区的窗口结束时间"),
    db: Session = Depends(get_db),
):
    require_timezone(start_at, "start_at")
    require_timezone(end_at, "end_at")
    if end_at < start_at:
        raise HTTPException(status_code=422, detail="end_at 不能早于 start_at")
    if end_at - start_at > MAX_PLAYBACK_RANGE:
        raise HTTPException(
            status_code=422,
            detail="单次 AIS 回放时间范围不能超过 24 小时",
        )

    dataset = get_latest_dataset(db)
    parameters = {
        "dataset_id": dataset["id"],
        "start_at": start_at,
        "end_at": end_at,
    }
    point_count = db.execute(
        text(
            """
            SELECT COUNT(*)
            FROM ais_positions
            WHERE dataset_id = :dataset_id
              AND recorded_at >= :start_at
              AND recorded_at <= :end_at
            """
        ),
        parameters,
    ).scalar_one()

    if point_count > MAX_PLAYBACK_POINTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"该窗口包含 {point_count} 个位置点，"
                f"超过单次上限 {MAX_PLAYBACK_POINTS}"
            ),
        )

    return db.execute(
        text(
            """
            SELECT id, vessel_id AS ship_id, latitude, longitude,
                   speed, course, heading, recorded_at, received_at
            FROM ais_positions
            WHERE dataset_id = :dataset_id
              AND recorded_at >= :start_at
              AND recorded_at <= :end_at
            ORDER BY recorded_at, vessel_id, id
            """
        ),
        parameters,
    ).mappings().all()


@router.get(
    "/ships/{vessel_id}/positions",
    response_model=list[AisPositionResponse],
)
def get_ais_vessel_positions(
    vessel_id: int,
    db: Session = Depends(get_db),
):
    dataset = get_latest_dataset(db)
    vessel_exists = db.execute(
        text(
            """
            SELECT 1
            FROM ais_vessels
            WHERE id = :vessel_id AND dataset_id = :dataset_id
            """
        ),
        {"vessel_id": vessel_id, "dataset_id": dataset["id"]},
    ).first()
    if vessel_exists is None:
        raise HTTPException(status_code=404, detail="未找到该 AIS 船舶")

    return db.execute(
        text(
            """
            SELECT id, vessel_id AS ship_id, latitude, longitude,
                   speed, course, heading, recorded_at, received_at
            FROM ais_positions
            WHERE vessel_id = :vessel_id
            ORDER BY recorded_at, id
            """
        ),
        {"vessel_id": vessel_id},
    ).mappings().all()
