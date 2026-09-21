"""Independent numerical check of the P4 encounters derived layer.

Recomputes encounter candidate ship pairs from raw ship_positions in pure
Python (time overlap + bounding-box filter, then dense synchronized sampling
of linearly interpolated tracks in a local equirectangular projection) and
compares the pair set and per-row min distances with the stored table.
Also re-checks the build manifest hash.

Run after backend/build_encounters.py:
    ./backend/.venv/Scripts/python.exe scripts/verify_encounters.py
"""
import bisect
import json
import hashlib
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]
BUILD_REPORT = ROOT / "sim_ais_demo/output_news_aligned/encounters_build.json"
TARGET = ROOT / "sim_ais_demo/output_news_aligned/encounters_verification.json"

M_PER_DEG_LAT = 110574.0
# Build and verification sample the same grid (overlap start + k*step), so the
# only expected divergence is the projection (equirectangular vs UTM 40N).
def band(value):
    return max(30.0, 0.005 * value)


def load_tracks(db, gap_minutes):
    """Raw positions split into segments at the build's gap (matching ship_tracks).

    All fixes share ONE equirectangular scale (cos of the fleet-mean latitude):
    per-fix scaling must not be used — longitude is huge (~51.5°), so a tiny
    per-fix scale difference shifts absolute positions by ~100 m and distorts
    short-range distance checks (verified 2026-09-20).
    """
    rows = db.execute(text("""
        SELECT p.ship_id, p.recorded_at, p.speed,
               ST_X(p.location::geometry) AS lng, ST_Y(p.location::geometry) AS lat
        FROM ship_positions p ORDER BY p.ship_id, p.recorded_at, p.id
    """)).mappings().all()
    mean_lat = math.radians(sum(row["lat"] for row in rows) / len(rows))
    k = 111320.0 * math.cos(mean_lat)
    segments = []
    current = None
    current_ship = None
    last_t = None
    for row in rows:
        t = row["recorded_at"].timestamp()
        if current is None or row["ship_id"] != current_ship \
                or t - last_t > gap_minutes * 60.0:
            current = {"t": [], "x": [], "y": []}
            segments.append((row["ship_id"], current))
            current_ship = row["ship_id"]
        current["t"].append(t)
        current["x"].append(row["lng"] * k)
        current["y"].append(row["lat"] * M_PER_DEG_LAT)
        last_t = t
    return [(ship_id, seg) for ship_id, seg in segments if len(seg["t"]) >= 2]


def interp(entry, t):
    ts = entry["t"]
    i = bisect.bisect_left(ts, t)
    if i == 0:
        return ts[0] <= t <= ts[-1] and (entry["x"][0], entry["y"][0]) or None
    if i >= len(ts):
        return None
    t0, t1 = ts[i - 1], ts[i]
    f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
    return (entry["x"][i - 1] + f * (entry["x"][i] - entry["x"][i - 1]),
            entry["y"][i - 1] + f * (entry["y"][i] - entry["y"][i - 1]))


def min_synchronized_distance(a, b, start, end, step):
    """Dense sampling of synchronized linearly interpolated positions."""
    best = None
    t = start
    while t <= end:
        pa, pb = interp(a, t), interp(b, t)
        if pa and pb:
            d = math.dist(pa, pb)
            if best is None or d < best:
                best = d
        t += step
    return best


def main():
    report = {}
    build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        manifest = dict(db.execute(text("""
            SELECT id, row_count, sha256, built_at, params
            FROM track_build_manifest WHERE table_name = 'encounters'
            ORDER BY id DESC LIMIT 1
        """)).mappings().one())
        params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
        distance_m = params["distance_nm"] * 1852.0
        report["manifest"] = {"id": manifest["id"], "params": params}

        assert fingerprints(db) == build["source_fingerprints"], "source tables changed since build"
        report["source_tables_unchanged"] = True

        digest = hashlib.sha256()
        for row in db.execute(text("""
            SELECT ship_a_id, ship_b_id, period::text, min_distance_m, overlap_minutes, data_source, params
            FROM encounters ORDER BY ship_a_id, ship_b_id
        """)).mappings():
            digest.update("|".join(str(row[key]) for key in row.keys()).encode())
            digest.update(b"\n")
        assert digest.hexdigest() == manifest["sha256"], "manifest sha256 mismatch"
        report["manifest_sha256_verified"] = True

        assert db.execute(text("SELECT count(*) FROM encounters WHERE NOT (ship_a_id < ship_b_id)")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM encounters WHERE min_distance_m < 0")).scalar_one() == 0
        report["structure_ok"] = True

        stored = {}
        for row in db.execute(text("""
            SELECT ship_a_id, ship_b_id, min_distance_m, period::text
            FROM encounters ORDER BY ship_a_id, ship_b_id
        """)).fetchall():
            stored[(row[0], row[1])] = row
        report["stored_rows"] = len(stored)

        tracks_manifest = dict(db.execute(text("""
            SELECT params FROM track_build_manifest WHERE table_name = 'ship_tracks'
            ORDER BY id DESC LIMIT 1
        """)).mappings().one())
        tracks_params = (tracks_manifest["params"] if isinstance(tracks_manifest["params"], dict)
                         else json.loads(tracks_manifest["params"]))
        tracks = load_tracks(db, tracks_params["gap_minutes"])
        expected = {}
        checked_pairs = 0
        for i, (sa, a) in enumerate(tracks):
            for sb, b in tracks[i + 1:]:
                if sa >= sb:
                    continue
                start = max(a["t"][0], b["t"][0])
                end = min(a["t"][-1], b["t"][-1])
                if start >= end:
                    continue
                if end - start < params["overlap_min"] * 60.0:
                    continue
                # Coarse bounding-box reject (margin covers interpolation excursions).
                margin = distance_m + 2000.0
                if min(a["x"]) - max(b["x"]) > margin or min(b["x"]) - max(a["x"]) > margin:
                    continue
                if min(a["y"]) - max(b["y"]) > margin or min(b["y"]) - max(a["y"]) > margin:
                    continue
                checked_pairs += 1
                d = min_synchronized_distance(a, b, start, end, params["sample_seconds"])
                if d is None:
                    continue
                key = (sa, sb)
                if d <= distance_m + band(distance_m):
                    if key not in expected or d < expected[key]:
                        expected[key] = d
        report["candidate_segment_pairs_checked"] = checked_pairs
        report["close_pairs_sampled"] = len(expected)

        # Direction 1: pairs STRICTLY inside the threshold (beyond the projection
        # band) must be stored; pairs in the boundary shell (thr ± band) may sit
        # on either side for the two independent computations and are reported,
        # not asserted (verified case 2026-09-20: pair 319-325 at 5579.6 m vs a
        # 5556 m threshold).
        inside = {p for p, d in expected.items() if d <= distance_m - band(distance_m)}
        missing = inside - set(stored)
        assert not missing, f"{len(missing)} expected pairs missing, e.g. {sorted(missing)[:5]}"
        shell = {p for p, d in expected.items() if distance_m - band(distance_m) < d <= distance_m + band(distance_m)}
        report["strictly_within_pairs"] = len(inside)
        report["boundary_shell_pairs"] = len(shell)
        report["boundary_shell_stored"] = len(shell & set(stored))
        report["pair_set_match"] = True

        # Direction 2: every stored pair must reproduce within the projection band.
        unexplained = []
        max_abs_diff = 0.0
        for (sa, sb), row in stored.items():
            python_min = expected.get((sa, sb))
            stored_min = float(row[2])
            if python_min is None:
                unexplained.append((sa, sb, stored_min, None))
                continue
            diff = abs(python_min - stored_min)
            max_abs_diff = max(max_abs_diff, diff)
            if diff > band(stored_min):
                unexplained.append((sa, sb, stored_min, python_min))
        assert not unexplained, f"{len(unexplained)} stored pairs not reproduced, e.g. {unexplained[:5]}"
        report["max_abs_distance_diff_m"] = max_abs_diff

    TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, default=str))


if __name__ == "__main__":
    main()
