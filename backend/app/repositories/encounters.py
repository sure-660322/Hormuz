"""Repository layer for P4 encounters: parameterized read-only SQL."""
from sqlalchemy import text
from sqlalchemy.orm import Session

ENCOUNTER_ROWS = text("""
SELECT e.id, e.ship_a_id, e.ship_b_id, e.min_distance_m, e.overlap_minutes,
       lower(e.period) AS period_start, upper(e.period) AS period_end,
       ST_AsGeoJSON(e.closest_point) AS closest_point,
       e.data_source, e.params, e.built_at,
       sa.name AS ship_a_name, sa.mmsi AS ship_a_mmsi, sa.ship_type AS ship_a_type,
       sb.name AS ship_b_name, sb.mmsi AS ship_b_mmsi, sb.ship_type AS ship_b_type
FROM encounters e
JOIN ships sa ON sa.id = e.ship_a_id
JOIN ships sb ON sb.id = e.ship_b_id
WHERE (CAST(:from AS timestamptz) IS NULL OR upper(e.period) > :from)
  AND (CAST(:to AS timestamptz) IS NULL OR lower(e.period) < :to)
  AND (CAST(:max_dist AS float8) IS NULL OR e.min_distance_m <= :max_dist)
ORDER BY e.min_distance_m, e.ship_a_id, e.ship_b_id
LIMIT :limit
""")

MANIFEST = text("""
SELECT row_count, built_at, params FROM track_build_manifest
WHERE table_name = 'encounters' ORDER BY id DESC LIMIT 1
""")

SOURCE_MAX_TIME = text("SELECT max(recorded_at) FROM ship_positions")


def fetch_encounters(db: Session, start, end, max_distance_m, limit: int):
    return db.execute(
        ENCOUNTER_ROWS,
        {"from": start, "to": end, "max_dist": max_distance_m, "limit": limit},
    ).mappings().all()


def fetch_manifest(db: Session):
    return db.execute(MANIFEST).mappings().one_or_none()


def fetch_source_max_time(db: Session):
    return db.execute(SOURCE_MAX_TIME).scalar()
