"""Repository layer for P3 dwell: parameterized read-only SQL."""
from sqlalchemy import text
from sqlalchemy.orm import Session

DWELL_ROWS = text("""
SELECT d.ship_id, d.dwell_no, d.kind, d.enter_at, d.leave_at, d.duration_min,
       d.displacement_radius_m, d.max_speed_kn, d.point_count, d.data_source,
       ST_AsGeoJSON(d.geom) AS geometry,
       s.name AS ship_name, s.mmsi, s.ship_type
FROM ship_dwell d
JOIN ships s ON s.id = d.ship_id
WHERE (CAST(:kind AS varchar) IS NULL OR d.kind = :kind)
  AND (CAST(:from AS timestamptz) IS NULL OR d.leave_at > :from)
  AND (CAST(:to AS timestamptz) IS NULL OR d.enter_at < :to)
ORDER BY d.enter_at, d.ship_id, d.dwell_no
LIMIT :limit
""")

MANIFEST = text("""
SELECT row_count, built_at, params FROM track_build_manifest
WHERE table_name = 'ship_dwell' ORDER BY id DESC LIMIT 1
""")

SOURCE_MAX_TIME = text("SELECT max(recorded_at) FROM ship_positions")

KINDS = ("at_anchor", "drift", "slow_transit")


def fetch_dwells(db: Session, kind, start, end, limit: int):
    return db.execute(
        DWELL_ROWS, {"kind": kind, "from": start, "to": end, "limit": limit}
    ).mappings().all()


def fetch_manifest(db: Session):
    return db.execute(MANIFEST).mappings().one_or_none()


def fetch_source_max_time(db: Session):
    return db.execute(SOURCE_MAX_TIME).scalar()
