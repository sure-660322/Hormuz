"""Repository layer for the P1 /api/tracks read path (plan section 5).

Parameterized read-only SQL only; row -> dict mapping happens here.
No string interpolation, no writes. Services and (future) agent tools
must go through this layer instead of issuing their own SQL.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

SEGMENTS_OVERLAP = text("""
SELECT ship_id, segment_no, point_count, t_start, t_end, data_source,
       ST_AsGeoJSON(ST_Transform(track::geometry, 4326)) AS geometry,
       (SELECT jsonb_agg(
                 jsonb_build_array(extract(epoch FROM u.t::timestamptz),
                                   valueAtTimestamp(speed, u.t::timestamptz))
                 ORDER BY u.t)
        FROM unnest(timestamps(track)) AS u(t)) AS speed
FROM ship_tracks
WHERE ship_id = :ship_id
  AND (CAST(:from AS timestamptz) IS NULL OR t_end > :from)
  AND (CAST(:to AS timestamptz) IS NULL OR t_start < :to)
ORDER BY segment_no
""")

SAMPLE_BUCKET = text("""
SELECT extract(epoch FROM u.t) AS t,
       ST_X(ST_Transform(valueAtTimestamp(track, u.t)::geometry, 4326)) AS lng,
       ST_Y(ST_Transform(valueAtTimestamp(track, u.t)::geometry, 4326)) AS lat,
       valueAtTimestamp(speed, u.t) AS speed
FROM ship_tracks, generate_series(:from, :to, make_interval(secs => :bucket)) AS u(t)
WHERE ship_id = :ship_id AND u.t >= t_start AND u.t <= t_end
ORDER BY u.t
""")

SHIP = text("SELECT id, mmsi, name, ship_type, flag FROM ships WHERE id = :ship_id")

MANIFEST = text("""
SELECT row_count, built_at, params FROM track_build_manifest
WHERE table_name = 'ship_tracks' ORDER BY id DESC LIMIT 1
""")

SOURCE_MAX_TIME = text("SELECT max(recorded_at) FROM ship_positions")

SOURCE_MAX_TIME_FOR_DATA_SOURCE = text(
    "SELECT max(recorded_at) FROM ship_positions WHERE data_source = :data_source"
)

SHIP_DATA_SOURCE = text(
    "SELECT data_source FROM ship_tracks WHERE ship_id = :ship_id LIMIT 1"
)


def fetch_ship(db: Session, ship_id: int):
    return db.execute(SHIP, {"ship_id": ship_id}).mappings().one_or_none()


def fetch_overlapping_segments(db: Session, ship_id: int, start, end):
    """Whole segments intersecting [start, end); geometry and speed share vertex order."""
    return db.execute(
        SEGMENTS_OVERLAP, {"ship_id": ship_id, "from": start, "to": end}
    ).mappings().all()


def fetch_bucket_samples(db: Session, ship_id: int, start, end, bucket_seconds: int):
    """Simplified level: bucket-sampled (t, lng, lat, speed) points within segments."""
    return db.execute(
        SAMPLE_BUCKET,
        {"ship_id": ship_id, "from": start, "to": end, "bucket": bucket_seconds},
    ).mappings().all()


def fetch_manifest(db: Session):
    return db.execute(MANIFEST).mappings().one_or_none()


def fetch_source_max_time(db: Session, data_source=None):
    if data_source is None:
        return db.execute(SOURCE_MAX_TIME).scalar()
    return db.execute(
        SOURCE_MAX_TIME_FOR_DATA_SOURCE, {"data_source": data_source}
    ).scalar()


def fetch_ship_data_source(db: Session, ship_id: int):
    return db.execute(SHIP_DATA_SOURCE, {"ship_id": ship_id}).scalar()
