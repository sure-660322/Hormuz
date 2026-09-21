"""P3 dwell (anchor/wait) derived-layer rebuild (docs/mobility_capability_plan.md section 7.3).

Set-based identification in the database: per ship, consecutive positions are grouped
into runs of a speed class (anchor: speed < anchor_speed_kn; transit: anchor <= speed <
transit_speed_kn). A run breaks when the class changes or the report gap exceeds
gap_minutes. Runs passing the duration filter (per class) become dwell rows;
at_anchor vs drift is split by displacement radius (max distance from the run centroid,
metres, computed in EPSG:32640). Thresholds are snapshotted into track_build_manifest.

Explicit rebuild only — run after source data changes:
    ./backend/.venv/Scripts/python.exe -m backend.build_ship_dwell
    ./backend/.venv/Scripts/python.exe -m backend.build_ship_dwell --data-source simulation --anchor-speed 3
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.database import engine
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]

DDL = (ROOT / "backend/sql/011_ship_dwell.sql").read_text(encoding="utf-8")

DELETE_SCOPE = text("DELETE FROM ship_dwell WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)")

CLASSIFIED = text("""
WITH base AS (
  SELECT p.ship_id, p.id, p.recorded_at, p.speed, p.location, p.data_source,
         CASE WHEN p.speed < :anchor_speed THEN 'anchor'
              WHEN p.speed < :transit_speed THEN 'transit'
              ELSE NULL END AS speed_class
  FROM ship_positions p
  WHERE (CAST(:data_source AS varchar) IS NULL OR p.data_source = :data_source)
), lagged AS (
  SELECT b.*,
         lag(recorded_at) OVER w AS prev_t,
         lag(speed_class) OVER w AS prev_class
  FROM base b
  WINDOW w AS (PARTITION BY ship_id ORDER BY recorded_at, id)
), flagged AS (
  SELECT l.*,
         CASE WHEN speed_class IS NOT NULL
                AND prev_class = speed_class
                AND recorded_at - prev_t <= make_interval(mins => :gap)
              THEN 0 ELSE 1 END AS run_break
  FROM lagged l
), runs AS (
  SELECT f.*,
         sum(run_break) OVER (PARTITION BY ship_id ORDER BY recorded_at, id) AS run_id
  FROM flagged f
), grouped AS (
  SELECT ship_id, run_id, speed_class, data_source,
         count(*) AS point_count,
         min(recorded_at) AS enter_at,
         max(recorded_at) AS leave_at,
         max(speed) AS max_speed_kn,
         ST_Centroid(ST_Collect(location::geometry)) AS centroid
  FROM runs
  WHERE speed_class IS NOT NULL
  GROUP BY ship_id, run_id, speed_class, data_source
), disp AS (
  -- Displacement radius measured on geography (WGS84 metres): the area spans
  -- two UTM zones and EPSG:32640 distorts distances >20% west of 54°E
  -- (verified 2026-09-20). Max distance from the run centroid over run points.
  SELECT r.ship_id, r.run_id,
         max(ST_Distance(r.location::geography, g.centroid::geography)) AS displacement_radius_m
  FROM runs r
  JOIN grouped g ON g.ship_id = r.ship_id AND g.run_id = r.run_id
  WHERE r.speed_class IS NOT NULL
  GROUP BY r.ship_id, r.run_id
), filtered AS (
  SELECT g.*, d.displacement_radius_m,
         CASE WHEN speed_class = 'anchor' AND d.displacement_radius_m <= :anchor_radius
              THEN 'at_anchor'
              WHEN speed_class = 'anchor' THEN 'drift'
              ELSE 'slow_transit' END AS kind,
         extract(epoch FROM (leave_at - enter_at)) / 60.0 AS duration_min
  FROM grouped g
  JOIN disp d ON d.ship_id = g.ship_id AND d.run_id = g.run_id
  WHERE (speed_class = 'anchor' AND leave_at - enter_at >= make_interval(mins => :anchor_min_duration))
     OR (speed_class = 'transit' AND leave_at - enter_at >= make_interval(mins => :transit_min_duration))
), numbered AS (
  SELECT f.*,
         row_number() OVER (PARTITION BY ship_id ORDER BY enter_at) AS dwell_no
  FROM filtered f
)
INSERT INTO ship_dwell (ship_id, dwell_no, kind, enter_at, leave_at, duration_min,
                        geom, displacement_radius_m, max_speed_kn, point_count, data_source)
SELECT ship_id, dwell_no, kind, enter_at, leave_at, duration_min,
       centroid, displacement_radius_m, max_speed_kn, point_count, data_source
FROM numbered
""")

SUMMARY = text("""
SELECT kind, count(*) AS rows, count(DISTINCT ship_id) AS ships,
       round(sum(duration_min)) AS total_minutes
FROM ship_dwell
WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)
GROUP BY kind ORDER BY kind
""")

HASH_ROWS = text("""
SELECT ship_id, dwell_no, kind, enter_at, leave_at, duration_min,
       ST_AsText(geom), displacement_radius_m, max_speed_kn, point_count, data_source
FROM ship_dwell
WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)
ORDER BY ship_id, dwell_no
""")


def table_sha256(db, data_source):
    digest = hashlib.sha256()
    for row in db.execute(HASH_ROWS, {"data_source": data_source}).mappings():
        digest.update("|".join(str(row[key]) for key in row.keys()).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Rebuild ship_dwell derived layer")
    parser.add_argument("--anchor-speed", type=float, default=3.0, help="anchor speed bound, kn (default 3)")
    parser.add_argument("--transit-speed", type=float, default=8.0, help="slow-transit speed bound, kn (default 8)")
    parser.add_argument("--anchor-min-duration", type=int, default=30, help="anchor run min minutes (default 30)")
    parser.add_argument("--transit-min-duration", type=int, default=60, help="slow-transit run min minutes (default 60)")
    parser.add_argument("--anchor-radius", type=float, default=926.0, help="anchor displacement radius, m (default 926 = 0.5 NM)")
    parser.add_argument("--gap-minutes", type=int, default=90, help="run break gap, minutes (default 90)")
    parser.add_argument("--data-source", default=None)
    args = parser.parse_args()
    for name, value in [("anchor-speed", args.anchor_speed), ("transit-speed", args.transit_speed),
                        ("anchor-min-duration", args.anchor_min_duration),
                        ("transit-min-duration", args.transit_min_duration),
                        ("anchor-radius", args.anchor_radius), ("gap-minutes", args.gap_minutes)]:
        if value <= 0:
            raise SystemExit(f"--{name} 必须为正数")

    params = {"anchor_speed": args.anchor_speed, "transit_speed": args.transit_speed,
              "anchor_min_duration": args.anchor_min_duration,
              "transit_min_duration": args.transit_min_duration,
              "anchor_radius": args.anchor_radius, "gap": args.gap_minutes,
              "data_source": args.data_source}
    with engine.begin() as db:
        before = fingerprints(db)
        db.execute(text(DDL))
        db.execute(DELETE_SCOPE, {"data_source": args.data_source})
        db.execute(CLASSIFIED, params)
        assert fingerprints(db) == before, "source tables changed during rebuild"
        summary = [dict(row) for row in db.execute(SUMMARY, {"data_source": args.data_source}).mappings()]
        digest = table_sha256(db, args.data_source)
        manifest_id = db.execute(text("""
            INSERT INTO track_build_manifest (table_name, row_count, sha256, params)
            VALUES ('ship_dwell', :row_count, :sha256, :params)
            RETURNING id
        """), {
            "row_count": sum(int(row["rows"]) for row in summary),
            "sha256": digest,
            "params": json.dumps({
                "anchor_speed_kn": args.anchor_speed,
                "transit_speed_kn": args.transit_speed,
                "anchor_min_duration_min": args.anchor_min_duration,
                "transit_min_duration_min": args.transit_min_duration,
                "anchor_radius_m": args.anchor_radius,
                "gap_minutes": args.gap_minutes,
                "data_source": args.data_source,
                "scope": "full" if args.data_source is None else "subset",
            }),
        }).scalar_one()

    result = {"manifest_id": manifest_id, "sha256": digest, "summary": summary,
              "source_tables_unchanged": True, "source_fingerprints": before}
    target = ROOT / "sim_ais_demo/output_news_aligned/ship_dwell_build.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
