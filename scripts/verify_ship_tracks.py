"""Independent numerical check of the P0 ship_tracks derived layer.

Recomputes segmentation, point counts and time bounds from ship_positions in
pure Python (no MobilityDB), samples interpolated positions and step speeds
from the database, and compares both. Also re-checks the build manifest hash.

Run after backend/build_ship_tracks.py:
    ./backend/.venv/Scripts/python.exe scripts/verify_ship_tracks.py
"""
import json
import hashlib
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]
BUILD_REPORT = ROOT / "sim_ais_demo/output_news_aligned/ship_tracks_build.json"
TARGET = ROOT / "sim_ais_demo/output_news_aligned/ship_tracks_verification.json"

GAP_MINUTES = None  # taken from the build manifest params
SAMPLES_PER_SEGMENT = 3
SAMPLED_SEGMENTS = 15


def independent_segments(rows, gap_minutes):
    """Same break rules as the build, computed without MobilityDB."""
    by_ship = defaultdict(list)
    for row in rows:
        by_ship[row["ship_id"]].append(row)
    segments = {}
    for ship_id, fixes in by_ship.items():
        fixes.sort(key=lambda r: (r["recorded_at"], r["id"]))
        current = []
        ship_segments = []
        previous = None
        for fix in fixes:
            if previous is not None and (
                fix["recorded_at"] - previous["recorded_at"]
                > timedelta_gap(gap_minutes)
                or fix["data_source"] != previous["data_source"]
            ):
                ship_segments.append(current)
                current = []
            current.append(fix)
            previous = fix
        if current:
            ship_segments.append(current)
        dense = [seg for seg in ship_segments if len(seg) >= 2]
        segments[ship_id] = dense
    return segments


def timedelta_gap(minutes):
    from datetime import timedelta
    return timedelta(minutes=minutes)


def lerp_position(fixes, t):
    """Linear interpolation between transformed source fixes (EPSG:32640)."""
    for a, b in zip(fixes, fixes[1:]):
        if a["recorded_at"] <= t <= b["recorded_at"]:
            dt = (b["recorded_at"] - a["recorded_at"]).total_seconds()
            f = (t - a["recorded_at"]).total_seconds() / dt if dt else 0.0
            return (
                a["x"] + f * (b["x"] - a["x"]),
                a["y"] + f * (b["y"] - a["y"]),
                a["speed"],
            )
    return None


def main():
    report = {}
    build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    gap = build.get("params_gap_minutes")
    with SessionLocal() as db:
        manifest = dict(db.execute(text("""
            SELECT id, row_count, sha256, built_at, params
            FROM track_build_manifest WHERE table_name = 'ship_tracks'
            ORDER BY id DESC LIMIT 1
        """)).mappings().one())
        params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
        gap = params["gap_minutes"]
        report["manifest"] = {"id": manifest["id"], "params": params}

        # Source unchanged since the recorded build.
        assert fingerprints(db) == build["source_fingerprints"], "source tables changed since build"
        report["source_tables_unchanged"] = True

        # Manifest sha256 over the same canonical rows.
        digest = hashlib.sha256()
        rows = db.execute(text("""
            SELECT ship_id, segment_no, point_count, t_start, t_end, data_source,
                   asText(track) AS track, asText(speed) AS speed
            FROM ship_tracks ORDER BY ship_id, segment_no
        """)).mappings()
        for row in rows:
            digest.update("|".join(str(row[key]) for key in row.keys()).encode())
            digest.update(b"\n")
        assert digest.hexdigest() == manifest["sha256"], "manifest sha256 mismatch"
        report["manifest_sha256_verified"] = True

        # Structural checks.
        assert db.execute(text("""
            SELECT count(*) FROM pg_indexes
            WHERE tablename = 'ship_tracks' AND indexdef LIKE '%USING gist%'
        """)).scalar_one() >= 1
        assert db.execute(text("SELECT count(*) FROM ship_tracks WHERE point_count < 2")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM ship_tracks WHERE NOT (t_start < t_end)")).scalar_one() == 0
        report["structure_ok"] = True

        # Independent segmentation from source.
        source = db.execute(text("""
            SELECT p.id, p.ship_id, p.recorded_at, p.speed, p.data_source,
                   ST_X(ST_Transform(p.location::geometry, :srid)) AS x,
                   ST_Y(ST_Transform(p.location::geometry, :srid)) AS y
            FROM ship_positions p ORDER BY p.ship_id, p.recorded_at, p.id
        """), {"srid": params["srid"]}).mappings().all()
        expected = independent_segments(source, gap)
        actual = defaultdict(list)
        for row in db.execute(text("""
            SELECT ship_id, segment_no, point_count, t_start, t_end
            FROM ship_tracks ORDER BY ship_id, segment_no
        """)).mappings():
            actual[row["ship_id"]].append(row)
        assert set(actual) == set(expected), "ship coverage mismatch"
        segment_errors = []
        for ship_id, segs in expected.items():
            got = actual[ship_id]
            assert len(got) == len(segs), f"segment count mismatch for ship {ship_id}"
            for seg, row in zip(segs, got):
                assert row["point_count"] == len(seg), f"point_count mismatch ship {ship_id} seg {row['segment_no']}"
                assert row["t_start"] == seg[0]["recorded_at"], f"t_start mismatch ship {ship_id}"
                assert row["t_end"] == seg[-1]["recorded_at"], f"t_end mismatch ship {ship_id}"
        report["segmentation_match"] = True
        report["segments"] = sum(len(v) for v in expected.values())

        # Sampled interpolation and speed checks against MobilityDB.
        rng = random.Random(20260919)
        all_keys = [(ship_id, i) for ship_id, segs in expected.items() for i in range(len(segs))]
        sampled = rng.sample(all_keys, min(SAMPLED_SEGMENTS, len(all_keys)))
        max_pos_error_m = 0.0
        speed_mismatches = 0
        checked = 0
        fixes_by_ship = {ship_id: [f for segs in expected[ship_id] for f in segs] for ship_id in expected}
        for ship_id, seg_idx in sampled:
            seg = expected[ship_id][seg_idx]
            intervals = list(zip(seg, seg[1:]))
            picks = rng.sample(intervals, min(SAMPLES_PER_SEGMENT, len(intervals)))
            for a, b in picks:
                t = a["recorded_at"] + (b["recorded_at"] - a["recorded_at"]) / 2
                got = db.execute(text("""
                    SELECT ST_X(valueAtTimestamp(track, :t)) AS x,
                           ST_Y(valueAtTimestamp(track, :t)) AS y,
                           valueAtTimestamp(speed, :t) AS speed
                    FROM ship_tracks WHERE ship_id = :ship_id AND segment_no = :segment_no
                """), {"t": t, "ship_id": ship_id, "segment_no": seg_idx + 1}).mappings().one()
                want = lerp_position(seg, t)
                assert want is not None
                error = ((got["x"] - want[0]) ** 2 + (got["y"] - want[1]) ** 2) ** 0.5
                max_pos_error_m = max(max_pos_error_m, error)
                if abs(got["speed"] - a["speed"]) > 1e-6:
                    speed_mismatches += 1
                checked += 1
        assert max_pos_error_m < 2.0, f"position error {max_pos_error_m} m"
        assert speed_mismatches == 0, f"{speed_mismatches} speed mismatches"
        report["sampled_checks"] = checked
        report["max_position_error_m"] = max_pos_error_m
        report["speed_mismatches"] = speed_mismatches

    TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, default=str))


if __name__ == "__main__":
    main()
