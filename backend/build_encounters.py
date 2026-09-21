"""P4 encounter derived-layer rebuild (docs/mobility_capability_plan.md section 7.4).

Candidate segment pairs come from ship_tracks (same data_source, time overlap,
conservative spatial prefilter ST_DWithin on the projected trajectories,
nearestApproachDistance only as a widened coarse prefilter — verified 2026-09-20
to overshoot the true synchronized minimum). The authoritative min distance is
a dense synchronized sampling of both interpolated tracks at sample_seconds
resolution; segment pairs passing the distance/overlap thresholds aggregate to
one row per ship pair (period envelope + cumulative overlap). The closest point
comes from the same sampling grid. Encounters are never computed on the request path.

Explicit rebuild only:
    ./backend/.venv/Scripts/python.exe -m backend.build_encounters
    ./backend/.venv/Scripts/python.exe -m backend.build_encounters --distance-nm 3 --overlap-min 30
"""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from backend.app.database import engine
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]

DDL = (ROOT / "backend/sql/012_encounters.sql").read_text(encoding="utf-8")

# Segment-pair candidates. Spatial prefilter ST_DWithin on the trajectory
# GEOGRAPHIES is an exact NECESSARY condition for synchronized proximity —
# never drops true candidates (unlike the tgeompoint && stbox operator, which a
# 2026-09-20 probe showed non-conservative, and nearestApproachDistance, which
# evaluates at discrete instants and can overshoot the true synchronized minimum
# by tens of percent — neither is used as a filter). Distances are always
# measured on geography (WGS84 metres): the operating area spans 51–57.3°E,
# i.e. two UTM zones (39N/40N), and EPSG:32640 distorts distances by >20% west
# of 54°E (verified 2026-09-20: 683 m vs true 554 m at 51.5°E).
CANDIDATES_DROP = text("DROP TABLE IF EXISTS _enc_candidates")

CANDIDATES = text("""
CREATE TEMP TABLE _enc_candidates AS
SELECT a.ship_id AS ship_a, a.segment_no AS seg_a,
       b.ship_id AS ship_b, b.segment_no AS seg_b,
       a.data_source,
       greatest(a.t_start, b.t_start) AS overlap_start,
       least(a.t_end, b.t_end) AS overlap_end
FROM ship_tracks a, ship_tracks b
WHERE a.ship_id < b.ship_id
  AND a.data_source = b.data_source
  AND a.t_start < b.t_end AND b.t_start < a.t_end
  AND ST_DWithin(ST_Transform(trajectory(a.track)::geometry, 4326)::geography,
                 ST_Transform(trajectory(b.track)::geometry, 4326)::geography,
                 :prefilter_m)
""")

# Authoritative min synchronized distance per candidate: dense sampling of both
# interpolated tracks at the same instants (grid starts at the overlap start),
# measured on geography (metres, WGS84 — see the zone-distortion note above).
SAMPLED_MIN = text("""
SELECT c.ship_a, c.seg_a, c.ship_b, c.seg_b, c.data_source,
       c.overlap_start, c.overlap_end,
       min(ST_Distance(ST_Transform(valueAtTimestamp(a.track, u.t)::geometry, 4326)::geography,
                       ST_Transform(valueAtTimestamp(b.track, u.t)::geometry, 4326)::geography)) AS sampled_min
FROM _enc_candidates c
JOIN ship_tracks a ON a.ship_id = c.ship_a AND a.segment_no = c.seg_a
JOIN ship_tracks b ON b.ship_id = c.ship_b AND b.segment_no = c.seg_b,
generate_series(c.overlap_start, c.overlap_end, make_interval(secs => :step)) AS u(t)
GROUP BY c.ship_a, c.seg_a, c.ship_b, c.seg_b, c.data_source, c.overlap_start, c.overlap_end
""")

# Closest instant between two tracks inside the overlap window, by sampling on
# the same grid as the build; returns the midpoint of the two ships at that
# instant (EPSG:4326). Distances on geography (metres) — see note above.
CLOSEST_POINT = text("""
WITH samples AS (
  SELECT u.t,
         ST_Distance(ST_Transform(valueAtTimestamp(a.track, u.t)::geometry, 4326)::geography,
                     ST_Transform(valueAtTimestamp(b.track, u.t)::geometry, 4326)::geography) AS dist
  FROM ship_tracks a, ship_tracks b,
       generate_series(CAST(:start AS timestamptz), CAST(:end AS timestamptz),
                       make_interval(secs => :step)) AS u(t)
  WHERE a.ship_id = :ship_a AND a.segment_no = :seg_a
    AND b.ship_id = :ship_b AND b.segment_no = :seg_b
), best AS (
  SELECT t FROM samples ORDER BY dist ASC NULLS LAST LIMIT 1
)
SELECT ST_AsText(ST_Transform(ST_Centroid(ST_MakeLine(
         valueAtTimestamp(a.track, (SELECT t FROM best))::geometry,
         valueAtTimestamp(b.track, (SELECT t FROM best))::geometry)), 4326)) AS midpoint
FROM ship_tracks a, ship_tracks b
WHERE a.ship_id = :ship_a AND a.segment_no = :seg_a
  AND b.ship_id = :ship_b AND b.segment_no = :seg_b
""")

SUMMARY = text("""
SELECT count(*) AS rows, count(DISTINCT ship_a_id) AS ships,
       round(min(min_distance_m)) AS min_distance_m,
       round(max(min_distance_m)) AS max_distance_m
FROM encounters
""")

HASH_ROWS = text("""
SELECT ship_a_id, ship_b_id, period::text, min_distance_m, overlap_minutes, data_source, params
FROM encounters ORDER BY ship_a_id, ship_b_id
""")


def table_sha256(db):
    digest = hashlib.sha256()
    for row in db.execute(HASH_ROWS).mappings():
        digest.update("|".join(str(row[key]) for key in row.keys()).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def run_build(distance_nm, overlap_min, sample_seconds, data_source):
    distance_m = distance_nm * 1852.0
    with engine.begin() as db:
        before = fingerprints(db)
        db.execute(text(DDL))
        db.execute(text("DELETE FROM encounters"))

        # ST_DWithin on geography is an exact necessary condition (unlike the
        # tgeompoint && stbox operator, verified non-conservative 2026-09-20),
        # so no further coarse prefilter is needed before the dense sampling.
        db.execute(CANDIDATES_DROP)
        db.execute(CANDIDATES, {"prefilter_m": distance_m})
        candidates = db.execute(SAMPLED_MIN, {"step": sample_seconds}).mappings().all()
        qualifying = [c for c in candidates
                      if c["sampled_min"] is not None
                      and float(c["sampled_min"]) <= distance_m
                      and (c["overlap_end"] - c["overlap_start"]).total_seconds() / 60.0 >= overlap_min]
        by_pair = defaultdict(list)
        for c in qualifying:
            by_pair[(c["ship_a"], c["ship_b"])].append(c)

        row_count = 0
        for (ship_a, ship_b), segs in sorted(by_pair.items()):
            best = min(segs, key=lambda c: float(c["sampled_min"]))
            params = json.dumps({
                "distance_nm": distance_nm,
                "overlap_min": overlap_min,
                "sample_seconds": sample_seconds,
                "segments": [[c["seg_a"], c["seg_b"]] for c in segs],
                "note": "模拟数据相遇（时空邻近）分析，接近不等于有交互",
            })
            point = db.execute(CLOSEST_POINT, {
                "ship_a": ship_a, "seg_a": best["seg_a"],
                "ship_b": ship_b, "seg_b": best["seg_b"],
                "start": best["overlap_start"], "end": best["overlap_end"],
                "step": sample_seconds,
            }).scalar()
            point_sql = f"ST_GeomFromText('{point}', 4326)" if point else "NULL"
            db.execute(text(f"""
                INSERT INTO encounters (ship_a_id, ship_b_id, period, min_distance_m,
                                        closest_point, overlap_minutes, data_source, params)
                VALUES (:a, :b, span(CAST(:p0 AS timestamptz), CAST(:p1 AS timestamptz)),
                        :dist, {point_sql}, :overlap, :ds, :params)
            """), {
                "a": ship_a, "b": ship_b,
                "p0": min(c["overlap_start"] for c in segs),
                "p1": max(c["overlap_end"] for c in segs),
                "dist": float(best["sampled_min"]),
                "overlap": sum((c["overlap_end"] - c["overlap_start"]).total_seconds() for c in segs) / 60.0,
                "ds": best["data_source"], "params": params,
            })
            row_count += 1

        assert fingerprints(db) == before, "source tables changed during rebuild"
        summary = dict(db.execute(SUMMARY).mappings().one())
        summary["rows"] = row_count
        digest = table_sha256(db)
        manifest_id = db.execute(text("""
            INSERT INTO track_build_manifest (table_name, row_count, sha256, params)
            VALUES ('encounters', :row_count, :sha256, :params)
            RETURNING id
        """), {
            "row_count": row_count,
            "sha256": digest,
            "params": json.dumps({
                "distance_nm": distance_nm,
                "overlap_min": overlap_min,
                "sample_seconds": sample_seconds,
                "data_source": data_source,
                "candidate_segment_pairs": len(candidates),
                "qualifying_segment_pairs": len(qualifying),
            }),
        }).scalar_one()

    return {
        "manifest_id": manifest_id,
        "sha256": digest,
        "summary": summary,
        "source_tables_unchanged": True,
        "source_fingerprints": before,
    }


def main():
    parser = argparse.ArgumentParser(description="Rebuild encounters derived layer")
    parser.add_argument("--distance-nm", type=float, default=3.0, help="max synchronized distance, NM (default 3)")
    parser.add_argument("--overlap-min", type=int, default=30, help="min segment-pair overlap, minutes (default 30)")
    parser.add_argument("--sample-seconds", type=int, default=60, help="synchronized sampling step, seconds (default 60)")
    parser.add_argument("--data-source", default=None, help="reserved for subset rebuilds (all sources share tracks)")
    args = parser.parse_args()
    if args.distance_nm <= 0 or args.overlap_min <= 0 or args.sample_seconds < 30:
        raise SystemExit("distance-nm/overlap-min 必须为正数，sample-seconds >= 30")

    result = run_build(args.distance_nm, args.overlap_min, args.sample_seconds, args.data_source)
    target = ROOT / "sim_ais_demo/output_news_aligned/encounters_build.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "source_fingerprints"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
