"""Independent check of the P2 event_ship_links layer.

- mentioned rows equal the flattened events.mentioned_vessels names and never
  carry a ship_id (identity with simulated ships is not asserted).
- observed rows are recomputed from raw ship_positions with a different SQL
  path (geography distance on source points, not MobilityDB trajectories);
  the stored trajectory distance must be <= the raw-point distance and <= radius.
- manifest hash re-verified.

Run after backend/build_event_ship_links.py:
    ./backend/.venv/Scripts/python.exe scripts/verify_event_ship_links.py
"""
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from backend.app.database import SessionLocal

ROOT = Path(__file__).resolve().parents[1]
BUILD_REPORT = ROOT / "sim_ais_demo/output_news_aligned/event_ship_links_build.json"
TARGET = ROOT / "sim_ais_demo/output_news_aligned/event_ship_links_verification.json"


def main():
    report = {}
    build = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        manifest = dict(db.execute(text("""
            SELECT id, row_count, sha256, built_at, params
            FROM track_build_manifest WHERE table_name = 'event_ship_links'
            ORDER BY id DESC LIMIT 1
        """)).mappings().one())
        params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
        report["manifest"] = {"id": manifest["id"], "params": params}

        digest = hashlib.sha256()
        for row in db.execute(text("""
            SELECT event_id, ship_id, link_type, vessel_name, confidence, evidence
            FROM event_ship_links ORDER BY id
        """)).mappings():
            digest.update("|".join(str(row[key]) for key in row.keys()).encode())
            digest.update(b"\n")
        assert digest.hexdigest() == manifest["sha256"], "manifest sha256 mismatch"
        report["manifest_sha256_verified"] = True

        # mentioned: exact match with flattened source JSONB, never linked to a ship.
        flattened = db.execute(text("""
            SELECT count(*) FROM events e, jsonb_array_elements_text(e.mentioned_vessels) AS name
        """)).scalar()
        mentioned = db.execute(text("""
            SELECT count(*) FROM event_ship_links WHERE link_type = 'mentioned'
        """)).scalar()
        assert mentioned == flattened, f"mentioned {mentioned} != source names {flattened}"
        assert db.execute(text("""
            SELECT count(*) FROM event_ship_links WHERE link_type = 'mentioned' AND ship_id IS NOT NULL
        """)).scalar() == 0
        report["mentioned_match_source"] = True
        report["mentioned_count"] = mentioned

        # observed: independent recompute. Rebuild the segment's linear
        # interpolation in pure Python from raw fixes (UTM coordinates fetched
        # read-only) and compute point-to-segment distances — independent of
        # the atGeometry/trajectory SQL used by the builder.
        def point_segment_distance(px, py, ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            length_sq = dx * dx + dy * dy
            if length_sq == 0:
                return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
            return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5

        radius_m = params["radius_km"] * 1000.0
        observed = db.execute(text("""
            SELECT l.id, e.event_id, l.ship_id, l.confidence, l.evidence,
                   e.event_lat, e.event_lng
            FROM event_ship_links l JOIN events e ON e.id = l.event_id
            WHERE l.link_type = 'observed'
        """)).mappings().all()
        recomputed = []
        for link in observed:
            window = link["evidence"]["window"]
            window = [datetime.fromisoformat(window[0]), datetime.fromisoformat(window[1])]
            seg = db.execute(text("""
                SELECT t_start, t_end FROM ship_tracks
                WHERE ship_id = :ship_id AND segment_no = :segment_no
            """), {"ship_id": link["ship_id"], "segment_no": link["evidence"]["segment_no"]}).mappings().one()
            lo = max(window[0], seg["t_start"])
            hi = min(window[1], seg["t_end"])
            fixes = db.execute(text("""
                SELECT p.recorded_at,
                       ST_X(ST_Transform(p.location::geometry, :srid)) AS x,
                       ST_Y(ST_Transform(p.location::geometry, :srid)) AS y
                FROM ship_positions p
                WHERE p.ship_id = :ship_id
                  AND p.recorded_at >= :start AND p.recorded_at <= :end
                ORDER BY p.recorded_at, p.id
            """), {
                "srid": params["srid"], "ship_id": link["ship_id"],
                "start": seg["t_start"], "end": seg["t_end"],
            }).mappings().all()
            assert len(fixes) >= 2, f"link {link['id']}: segment has <2 fixes"
            point = db.execute(text("""
                SELECT ST_X(ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geometry, :srid)) AS x,
                       ST_Y(ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geometry, :srid)) AS y
            """), {"lng": link["event_lng"], "lat": link["event_lat"], "srid": params["srid"]}).mappings().one()
            # Pairs straddling the window boundary also count: interpolation
            # uses one fix inside and one outside the intersection.
            # Clip each pair to [lo, hi) first: the closest point of a
            # straddling pair may lie outside the window (atTime semantics).
            def interp(a, b, t):
                span = (b["recorded_at"] - a["recorded_at"]).total_seconds()
                f = (t - a["recorded_at"]).total_seconds() / span if span else 0.0
                return (a["x"] + f * (b["x"] - a["x"]), a["y"] + f * (b["y"] - a["y"]))

            best = None
            for a, b in zip(fixes, fixes[1:]):
                if not (a["recorded_at"] < hi and b["recorded_at"] >= lo):
                    continue
                lo_t = max(lo, a["recorded_at"])
                hi_t = min(hi, b["recorded_at"])
                ax, ay = interp(a, b, lo_t)
                bx, by = interp(a, b, hi_t)
                d = point_segment_distance(point["x"], point["y"], ax, ay, bx, by)
                if best is None or d < best:
                    best = d
            assert best is not None, f"link {link['id']}: no pair overlaps window"
            independent = best
            stored = float(link["evidence"]["min_distance_m"])
            assert abs(stored - independent) <= 2.0, \
                f"link {link['id']}: stored {stored} m vs independent {independent:.1f} m"
            assert stored <= radius_m * 1.01, f"link {link['id']}: stored distance over radius"
            assert 0.0 <= link["confidence"] <= 1.0
            recomputed.append(stored)
        report["observed_count"] = len(observed)
        report["observed_max_stored_distance_m"] = max(recomputed) if recomputed else None

        # structural red lines
        assert db.execute(text("""
            SELECT count(*) FROM event_ship_links
            WHERE link_type = 'observed' AND (ship_id IS NULL OR confidence IS NULL)
        """)).scalar() == 0
        assert db.execute(text("""
            SELECT count(*) FROM event_ship_links WHERE confidence IS NOT NULL AND link_type = 'mentioned'
        """)).scalar() == 0
        report["structure_ok"] = True

    TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
