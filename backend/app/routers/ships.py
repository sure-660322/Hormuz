from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Ship, ShipPosition
from backend.app.schemas import (
    NearbyEventResponse,
    ShipMapResponse,
    ShipSnapshotWindowResponse,
    ShipPositionResponse,
    ShipResponse,
)


router = APIRouter(
    prefix="/ships",
    tags=["ships"],
)

MAX_PLAYBACK_RANGE = timedelta(hours=24)
MAX_PLAYBACK_POINTS = 50_000
MAX_TRACK_SOURCE_POINTS = 100_000
MAX_TRACK_OUTPUT_POINTS = 5_000
TRACK_GAP_SECONDS = 90 * 60
SNAPSHOT_MAX_AGE = timedelta(hours=1)
SNAPSHOT_MAX_SHIPS = 5_000
SNAPSHOT_WINDOW_MAX_FRAMES = 4
SNAPSHOT_WINDOW_MAX_RANGE = timedelta(minutes=15)
SNAPSHOT_WINDOW_MAX_SHIPS = 20_000

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
                ships.ship_type_cn_raw,
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


def _snapshot_rows(
    db: Session,
    at: datetime,
    limit: int,
    bounds: tuple[float, float, float, float] | None = None,
):
    bounds_filter = (
        "WHERE p.latitude BETWEEN :south AND :north "
        "AND p.longitude BETWEEN :west AND :east"
        if bounds is not None else ""
    )

    # One indexed lookup per ship: never materialize the day's reports in Python.
    # A report older than one hour is not presented as a position at `at`.
    rows = db.execute(
        text(
            f"""
            SELECT s.id, s.mmsi, s.name, s.ship_type, s.ship_type_cn_raw,
                   s.flag, s.imo, s.callsign,
                   p.latitude, p.longitude, p.speed, p.course, p.heading, p.recorded_at
            FROM ships AS s
            JOIN LATERAL (
                SELECT latitude, longitude, speed, course, heading, recorded_at
                FROM ship_positions
                WHERE ship_id = s.id
                  AND recorded_at <= :at
                  AND recorded_at >= :oldest
                ORDER BY recorded_at DESC, id DESC
                LIMIT 1
            ) AS p ON TRUE
            {bounds_filter}
            ORDER BY s.id
            LIMIT :limit
            """
        ),
        {
            "at": at,
            "oldest": at - SNAPSHOT_MAX_AGE,
            "south": bounds[0] if bounds else None,
            "north": bounds[1] if bounds else None,
            "west": bounds[2] if bounds else None,
            "east": bounds[3] if bounds else None,
            "limit": limit,
        },
    ).mappings().all()
    return rows


@router.get("/snapshot", response_model=list[ShipMapResponse])
def get_ship_snapshot(
    at: datetime = Query(..., description="带时区的历史快照时刻"),
    south: float | None = Query(None, ge=-90, le=90),
    north: float | None = Query(None, ge=-90, le=90),
    west: float | None = Query(None, ge=-180, le=180),
    east: float | None = Query(None, ge=-180, le=180),
    db: Session = Depends(get_db),
):
    if at.utcoffset() is None:
        raise HTTPException(status_code=422, detail="at 必须包含时区")
    values = (south, north, west, east)
    bounds = None
    if any(value is not None for value in values):
        if any(value is None for value in values) or south >= north or west >= east:
            raise HTTPException(status_code=422, detail="视野边界必须完整且满足 south < north、west < east")
        bounds = (south, north, west, east)
    rows = _snapshot_rows(db, at, SNAPSHOT_MAX_SHIPS + 1, bounds)
    if len(rows) > SNAPSHOT_MAX_SHIPS:
        raise HTTPException(status_code=422, detail=f"单帧船舶数超过 {SNAPSHOT_MAX_SHIPS} 艘")
    return rows


@router.get("/snapshot-window", response_model=ShipSnapshotWindowResponse)
def get_ship_snapshot_window(
    at: list[datetime] = Query(..., description="按时间顺序给出 1–4 个带时区的快照时刻"),
    db: Session = Depends(get_db),
):
    if not 1 <= len(at) <= SNAPSHOT_WINDOW_MAX_FRAMES:
        raise HTTPException(status_code=422, detail="单次快照窗口只允许 1–4 帧")
    if any(value.utcoffset() is None for value in at):
        raise HTTPException(status_code=422, detail="全部 at 必须包含时区")
    if any(left >= right for left, right in zip(at, at[1:])) or at[-1] - at[0] > SNAPSHOT_WINDOW_MAX_RANGE:
        raise HTTPException(status_code=422, detail="快照时刻必须递增且跨度不超过 15 分钟")

    frames = []
    total = 0
    for frame_at in at:
        remaining = SNAPSHOT_WINDOW_MAX_SHIPS - total
        rows = _snapshot_rows(db, frame_at, min(SNAPSHOT_MAX_SHIPS, remaining) + 1)
        if len(rows) > SNAPSHOT_MAX_SHIPS or total + len(rows) > SNAPSHOT_WINDOW_MAX_SHIPS:
            raise HTTPException(status_code=422, detail="快照窗口返回船舶数超过上限")
        frames.append({"at": frame_at, "ships": rows})
        total += len(rows)
    return {"frames": frames, "max_age_seconds": int(SNAPSHOT_MAX_AGE.total_seconds())}

@router.get("/{ship_id}/track-window")
def get_ship_track_window(
    ship_id: int,
    from_at: datetime = Query(..., alias="from", description="带时区的起始时刻"),
    to: datetime = Query(..., description="带时区的结束时刻"),
    bucket_seconds: int = Query(300, ge=30, le=3600),
    db: Session = Depends(get_db),
):
    """Read one vessel's indexed reports; split real gaps before sampling."""
    if from_at.utcoffset() is None or to.utcoffset() is None:
        raise HTTPException(status_code=422, detail="from/to 必须包含时区")
    if not from_at < to or to - from_at > MAX_PLAYBACK_RANGE:
        raise HTTPException(status_code=422, detail="轨迹窗口须大于零且不超过 24 小时")
    if db.get(Ship, ship_id) is None:
        raise HTTPException(status_code=404, detail="船舶不存在")

    rows = db.execute(
        text("""
            SELECT id, latitude, longitude, speed, course, heading, recorded_at
            FROM ship_positions
            WHERE ship_id = :ship_id AND recorded_at >= :from_at AND recorded_at <= :to_at
            ORDER BY recorded_at, id
            LIMIT :limit
        """),
        {"ship_id": ship_id, "from_at": from_at, "to_at": to,
         "limit": MAX_TRACK_SOURCE_POINTS + 1},
    ).mappings().all()
    if len(rows) > MAX_TRACK_SOURCE_POINTS:
        raise HTTPException(status_code=422, detail="单船窗口报位超过 10 万条，请缩小时间范围")

    segments: list[dict] = []
    gaps: list[dict] = []
    sampled: list[dict] = []
    previous = None
    last_bucket = None

    def finish_segment():
        if not sampled:
            return
        segments.append({"segment_no": len(segments) + 1, "points": sampled.copy()})
        sampled.clear()

    for row in rows:
        at = row["recorded_at"]
        if previous is not None and (at - previous["recorded_at"]).total_seconds() > TRACK_GAP_SECONDS:
            # Include the actual endpoint on each side of the gap.
            endpoint = {"id": previous["id"], "latitude": previous["latitude"], "longitude": previous["longitude"],
                        "speed": previous["speed"], "course": previous["course"], "heading": previous["heading"], "recorded_at": previous["recorded_at"]}
            if sampled and sampled[-1]["id"] != endpoint["id"]:
                sampled.append(endpoint)
            finish_segment()
            gaps.append({"from": previous["recorded_at"], "to": at,
                         "minutes": round((at - previous["recorded_at"]).total_seconds() / 60, 1)})
            last_bucket = None
        bucket = int(at.timestamp()) // bucket_seconds
        if bucket != last_bucket:
            sampled.append({"id": row["id"], "latitude": row["latitude"], "longitude": row["longitude"],
                            "speed": row["speed"], "course": row["course"], "heading": row["heading"], "recorded_at": at})
            last_bucket = bucket
        previous = row
    if previous is not None:
        endpoint = {"id": previous["id"], "latitude": previous["latitude"], "longitude": previous["longitude"],
                    "speed": previous["speed"], "course": previous["course"], "heading": previous["heading"], "recorded_at": previous["recorded_at"]}
        if sampled and sampled[-1]["id"] != endpoint["id"]:
            sampled.append(endpoint)
    finish_segment()
    output_count = sum(len(segment["points"]) for segment in segments)
    if output_count > MAX_TRACK_OUTPUT_POINTS:
        raise HTTPException(status_code=422, detail="抽稀后仍超过 5000 点，请增大 bucket_seconds")
    return {"ship_id": ship_id, "from": from_at, "to": to,
            "bucket_seconds": bucket_seconds, "gap_minutes": TRACK_GAP_SECONDS // 60,
            "source_count": len(rows), "point_count": output_count,
            "segments": segments, "gaps": gaps}


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


@router.get("/playback", response_model=list[ShipPositionResponse])
def get_playback_positions(
    start_at: datetime = Query(
        ...,
        description="回放开始时间，必须是带时区的 ISO 8601 时间",
    ),
    end_at: datetime = Query(
        ...,
        description="回放结束时间，必须是带时区的 ISO 8601 时间",
    ),
    db: Session = Depends(get_db),
):
    if start_at.utcoffset() is None or end_at.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="start_at 和 end_at 必须包含时区",
        )

    if end_at < start_at:
        raise HTTPException(
            status_code=422,
            detail="end_at 不能早于 start_at",
        )

    if end_at - start_at > MAX_PLAYBACK_RANGE:
        raise HTTPException(
            status_code=422,
            detail="单次回放时间范围不能超过 24 小时",
        )

    filters = (
        ShipPosition.recorded_at >= start_at,
        ShipPosition.recorded_at <= end_at,
    )
    point_count = db.scalar(
        select(func.count(ShipPosition.id)).where(*filters)
    ) or 0

    if point_count > MAX_PLAYBACK_POINTS:
        raise HTTPException(
            status_code=422,
            detail=f"回放位置点不能超过 {MAX_PLAYBACK_POINTS} 条",
        )

    statement = (
        select(ShipPosition)
        .where(*filters)
        .order_by(
            ShipPosition.recorded_at,
            ShipPosition.ship_id,
            ShipPosition.id,
        )
    )

    return db.scalars(statement).all()
