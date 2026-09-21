"""Independent numerical check of the P3 ship_dwell derived layer.

Recomputes speed-class runs, duration filters, kind classification and
displacement radius from ship_positions in pure Python (local equirectangular
projection, no MobilityDB/PostGIS aggregate reuse), compares every stored row,
and re-checks the build manifest hash.

Run after backend/build_ship_dwell.py:
    ./backend/.venv/Scripts/python.exe scripts/verify_ship_dwell.py
"""
import json
import hashlib
import math
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from backend.app.database import SessionLocal
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]
BUILD_REPORT = ROOT / "sim_ais_demo/output_news_aligned/ship_dwell_build.json"
TARGET = ROOT / "sim_ais_demo/output_news_aligned/ship_dwell_verification.json"

M_PER_DEG_LAT = 110574.0
DISPLACEMENT_TOL_M = 60.0  # UTM vs local equirectangular projection difference


def independent_dwells(rows, params):
    """Same run/duration/kind rules as the build, computed without the database."""
    by_ship = defaultdict(list)
    for row in rows:
        by_ship[row["ship_id"]].append(row)
    out = []
    for ship_id, fixes in by_ship.items():
        fixes.sort(key=lambda r: (r["recorded_at"], r["id"]))
        # Maximal consecutive sequences of same-class points (gap/class breaks).
        runs = strict_runs(fixes, params)
        dwells = []
        for cls, members in runs:
            duration = members[-1]["recorded_at"] - members[0]["recorded_at"]
            if cls == "anchor":
                if duration < timedelta(minutes=params["anchor_min_duration_min"]):
                    continue
            elif duration < timedelta(minutes=params["transit_min_duration_min"]):
                continue
            disp = displacement_radius(members)
            if cls == "anchor":
                kind = "at_anchor" if disp <= params["anchor_radius_m"] else "drift"
            else:
                kind = "slow_transit"
            dwells.append({
                "ship_id": ship_id,
                "kind": kind,
                "enter_at": members[0]["recorded_at"],
                "leave_at": members[-1]["recorded_at"],
                "duration_min": duration.total_seconds() / 60.0,
                "displacement_radius_m": disp,
                "max_speed_kn": max(m["speed"] for m in members),
                "point_count": len(members),
                "data_source": members[0]["data_source"],
            })
        dwells.sort(key=lambda d: d["enter_at"])
        for i, dwell in enumerate(dwells, 1):
            dwell["dwell_no"] = i
            out.append(dwell)
    return out


def strict_runs(fixes, params):
    """Maximal consecutive sequences of points sharing a speed class."""
    gap = timedelta(minutes=params["gap_minutes"])
    runs = []
    current_cls = None
    current = []
    previous_t = None
    for fix in fixes:
        cls = speed_class(fix["speed"], params)
        broken = (cls != current_cls or current_cls is None
                  or fix["recorded_at"] - previous_t > gap)
        if broken:
            if current:
                runs.append((current_cls, current))
            current = []
        if cls is not None:
            current_cls = cls
            current.append(fix)
        else:
            current_cls = None
        previous_t = fix["recorded_at"]
    if current:
        runs.append((current_cls, current))
    return [(cls, members) for cls, members in runs if members]


def speed_class(speed, params):
    if speed < params["anchor_speed_kn"]:
        return "anchor"
    if speed < params["transit_speed_kn"]:
        return "transit"
    return None


def displacement_radius(members):
    lat0 = math.radians(sum(m["lat"] for m in members) / len(members))
    # metres per degree longitude at lat0
    m_per_deg_lng = 111320.0 * math.cos(lat0)
    xs = [m["lng"] * m_per_deg_lng for m in members]
    ys = [m["lat"] * M_PER_DEG_LAT for m in members]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    return max(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in zip(xs, ys))


def main():
    report = {}
    build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        manifest = dict(db.execute(text("""
            SELECT id, row_count, sha256, built_at, params
            FROM track_build_manifest WHERE table_name = 'ship_dwell'
            ORDER BY id DESC LIMIT 1
        """)).mappings().one())
        params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
        report["manifest"] = {"id": manifest["id"], "params": params}

        assert fingerprints(db) == build["source_fingerprints"], "source tables changed since build"
        report["source_tables_unchanged"] = True

        digest = hashlib.sha256()
        rows = db.execute(text("""
            SELECT ship_id, dwell_no, kind, enter_at, leave_at, duration_min,
                   ST_AsText(geom), displacement_radius_m, max_speed_kn, point_count, data_source
            FROM ship_dwell ORDER BY ship_id, dwell_no
        """)).mappings()
        for row in rows:
            digest.update("|".join(str(row[key]) for key in row.keys()).encode())
            digest.update(b"\n")
        assert digest.hexdigest() == manifest["sha256"], "manifest sha256 mismatch"
        report["manifest_sha256_verified"] = True

        assert db.execute(text("""
            SELECT count(*) FROM pg_indexes
            WHERE tablename = 'ship_dwell' AND indexdef LIKE '%USING gist%'
        """)).scalar_one() >= 1
        assert db.execute(text("SELECT count(*) FROM ship_dwell WHERE point_count < 2")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM ship_dwell WHERE NOT (enter_at < leave_at)")).scalar_one() == 0
        assert db.execute(text("SELECT count(*) FROM ship_dwell WHERE duration_min <= 0")).scalar_one() == 0
        report["structure_ok"] = True

        source = db.execute(text("""
            SELECT p.id, p.ship_id, p.recorded_at, p.speed, p.data_source,
                   ST_X(p.location::geometry) AS lng, ST_Y(p.location::geometry) AS lat
            FROM ship_positions p ORDER BY p.ship_id, p.recorded_at, p.id
        """)).mappings().all()
        expected = independent_dwells(source, params)
        actual = [dict(row) for row in db.execute(text("""
            SELECT ship_id, dwell_no, kind, enter_at, leave_at, duration_min,
                   displacement_radius_m, max_speed_kn, point_count, data_source
            FROM ship_dwell ORDER BY ship_id, dwell_no
        """)).mappings()]
        assert len(actual) == len(expected), f"row count mismatch: {len(actual)} vs {len(expected)}"
        max_disp_error = 0.0
        for got, want in zip(actual, expected):
            for key in ("ship_id", "dwell_no", "kind", "enter_at", "leave_at",
                        "max_speed_kn", "point_count", "data_source"):
                assert got[key] == want[key], f"{key} mismatch: {got} vs {want}"
            assert abs(got["duration_min"] - want["duration_min"]) < 1e-6, "duration mismatch"
            error = abs(got["displacement_radius_m"] - want["displacement_radius_m"])
            max_disp_error = max(max_disp_error, error)
            tol = max(DISPLACEMENT_TOL_M, 0.01 * want["displacement_radius_m"])
            assert error < tol, f"displacement error {error} m (tolerance {tol} m)"
        report["rows_match"] = len(actual)
        report["max_displacement_error_m"] = max_disp_error

    TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, default=str))


if __name__ == "__main__":
    main()
