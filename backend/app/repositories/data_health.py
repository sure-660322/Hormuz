"""Repository layer for P5 /api/data-health: parameterized read-only SQL."""
from sqlalchemy import text
from sqlalchemy.orm import Session

SOURCE_COUNTS = text("""
SELECT p.data_source,
       count(*) AS position_count,
       count(DISTINCT p.ship_id) AS ship_count,
       min(p.recorded_at) AS coverage_start,
       max(p.recorded_at) AS coverage_end,
       round((percentile_cont(0.5) WITHIN GROUP (
                  ORDER BY extract(epoch FROM (p.recorded_at - g.prev_t)) / 60.0
              ))::numeric, 1) AS median_gap_minutes
FROM ship_positions p
JOIN LATERAL (
  SELECT max(p2.recorded_at) AS prev_t
  FROM ship_positions p2
  WHERE p2.ship_id = p.ship_id AND p2.recorded_at < p.recorded_at
) g ON true
GROUP BY p.data_source
ORDER BY p.data_source
""")

GLOBAL_COUNTS = text("""
SELECT (SELECT count(*) FROM ships) AS ships,
       (SELECT count(*) FROM events) AS events,
       (SELECT count(*) FROM news) AS news,
       (SELECT count(*) FROM ship_positions) AS positions
""")

DERIVED_TABLES = ("ship_tracks", "ship_dwell", "encounters", "event_ship_links")

DERIVED_MANIFESTS = text("""
SELECT m.table_name, m.row_count, m.built_at, m.params
FROM track_build_manifest m
JOIN (
  SELECT table_name, max(id) AS max_id
  FROM track_build_manifest
  WHERE table_name IN ('ship_tracks', 'ship_dwell', 'encounters', 'event_ship_links')
  GROUP BY table_name
) latest ON latest.max_id = m.id
ORDER BY m.table_name
""")


def fetch_source_counts(db: Session):
    return [dict(row) for row in db.execute(SOURCE_COUNTS).mappings()]


def fetch_global_counts(db: Session):
    return dict(db.execute(GLOBAL_COUNTS).mappings().one())


def fetch_derived_manifests(db: Session):
    return [dict(row) for row in db.execute(DERIVED_MANIFESTS).mappings()]
