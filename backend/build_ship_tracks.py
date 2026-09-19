"""P0 generalized derived-track rebuild (docs/mobility_capability_plan.md).

Builds ship_tracks from ship_positions: per ship, linear tgeompoint in EPSG:32640
plus a step-interpolated tfloat speed sequence sharing the same time base.
Segments break when the gap exceeds gap_minutes or data_source changes.
Source tables are never modified; fingerprints are asserted before and after.

Explicit rebuild only — run after source data changes:
    ./backend/.venv/Scripts/python.exe -m backend.build_ship_tracks
    ./backend/.venv/Scripts/python.exe -m backend.build_ship_tracks --data-source simulation --gap-minutes 90
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.database import engine
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]

DDL = (ROOT / "backend/sql/009_ship_tracks.sql").read_text(encoding="utf-8")

DELETE_SCOPE = text("DELETE FROM ship_tracks WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)")

BUILD = text("""
WITH samples AS (
  SELECT p.*,
         lag(recorded_at) OVER w AS previous,
         lag(data_source)  OVER w AS previous_source
  FROM ship_positions p
  WHERE (CAST(:data_source AS varchar) IS NULL OR p.data_source = :data_source)
  WINDOW w AS (PARTITION BY ship_id ORDER BY recorded_at, id)
), numbered AS (
  SELECT *, sum(CASE WHEN previous IS NULL
                      OR recorded_at - previous > make_interval(mins => :gap)
                      OR data_source IS DISTINCT FROM previous_source
                     THEN 1 ELSE 0 END)
             OVER (PARTITION BY ship_id ORDER BY recorded_at, id) AS segment
  FROM samples
), grouped AS (
  SELECT ship_id, segment, data_source,
         count(*) AS point_count, min(recorded_at) AS t_start, max(recorded_at) AS t_end
  FROM numbered
  GROUP BY ship_id, segment, data_source
  HAVING count(*) >= 2
), dense AS (
  SELECT ship_id, segment,
         row_number() OVER (PARTITION BY ship_id ORDER BY segment) AS segment_no
  FROM grouped
)
INSERT INTO ship_tracks (ship_id, segment_no, track, speed, point_count, t_start, t_end, data_source)
SELECT g.ship_id, d.segment_no,
  tgeompointSeq(array_agg(tgeompoint(ST_Transform(p.location::geometry, :srid), p.recorded_at)
    ORDER BY p.recorded_at, p.id), 'Linear', true, true),
  tfloatSeq(array_agg(tfloat(p.speed, p.recorded_at)
    ORDER BY p.recorded_at, p.id), 'Step', true, true),
  g.point_count, g.t_start, g.t_end, g.data_source
FROM numbered p
JOIN grouped g ON g.ship_id = p.ship_id AND g.segment = p.segment
JOIN dense   d ON d.ship_id = g.ship_id AND d.segment = g.segment
GROUP BY g.ship_id, d.segment_no, g.point_count, g.t_start, g.t_end, g.data_source
""")

SUMMARY = text("""
SELECT count(*) AS segments, count(DISTINCT ship_id) AS ships,
       sum(point_count) AS points, min(t_start) AS t_start, max(t_end) AS t_end
FROM ship_tracks
WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)
""")

HASH_ROWS = text("""
SELECT ship_id, segment_no, point_count, t_start, t_end, data_source,
       asText(track) AS track, asText(speed) AS speed
FROM ship_tracks
WHERE (CAST(:data_source AS varchar) IS NULL OR data_source = :data_source)
ORDER BY ship_id, segment_no
""")


def table_sha256(db, data_source):
    digest = hashlib.sha256()
    rows = db.execute(HASH_ROWS, {"data_source": data_source}).mappings()
    for row in rows:
        digest.update("|".join(str(row[key]) for key in row.keys()).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Rebuild ship_tracks derived layer")
    parser.add_argument("--gap-minutes", type=int, default=90, help="segment break gap (default 90)")
    parser.add_argument("--srid", type=int, default=32640, help="projected SRID (default 32640)")
    parser.add_argument("--data-source", default=None, help="rebuild only this data_source (default: all)")
    args = parser.parse_args()
    if args.gap_minutes < 1:
        raise SystemExit("--gap-minutes must be >= 1")

    params = {"gap": args.gap_minutes, "srid": args.srid, "data_source": args.data_source}
    with engine.begin() as db:
        before = fingerprints(db)
        db.execute(text(DDL))
        db.execute(DELETE_SCOPE, {"data_source": args.data_source})
        db.execute(BUILD, params)
        assert fingerprints(db) == before, "source tables changed during rebuild"
        result = dict(db.execute(SUMMARY, {"data_source": args.data_source}).mappings().one())
        digest = table_sha256(db, args.data_source)
        manifest_id = db.execute(text("""
            INSERT INTO track_build_manifest (table_name, row_count, sha256, params)
            VALUES ('ship_tracks', :row_count, :sha256, :params)
            RETURNING id
        """), {
            "row_count": result["segments"],
            "sha256": digest,
            "params": json.dumps({
                "gap_minutes": args.gap_minutes,
                "srid": args.srid,
                "data_source": args.data_source,
                "ships": result["ships"],
                "points": result["points"],
                "scope": "full" if args.data_source is None else "subset",
            }),
        }).scalar_one()
        result["manifest_id"] = manifest_id
        result["sha256"] = digest
        result["source_tables_unchanged"] = True
        result["source_fingerprints"] = before

    target = ROOT / "sim_ais_demo/output_news_aligned/ship_tracks_build.json"
    target.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "source_fingerprints"}, default=str))


if __name__ == "__main__":
    main()
