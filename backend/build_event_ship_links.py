"""P2 event-ship link rebuild (docs/mobility_capability_plan.md section 7.2).

Two link types, kept strictly separate:
- mentioned: every vessel name in events.mentioned_vessels (real-news text
  evidence). ship_id stays NULL — never matched to simulated ships by name.
- observed: events with a representative coordinate are tested against the
  simulated ship_tracks layer: tracks entering the radius within the event
  time window become links. Teaching demo only, never real causality.

Rebuild is explicit and writes a track_build_manifest row:
    ./backend/.venv/Scripts/python.exe -m backend.build_event_ship_links
    ./backend/.venv/Scripts/python.exe -m backend.build_event_ship_links --radius-km 50 --half-window-hours 12
"""
import argparse
import hashlib
import json
from pathlib import Path

from sqlalchemy import text

from backend.app.database import engine
from backend.build_mobility_demo import fingerprints

ROOT = Path(__file__).resolve().parents[1]
DDL = (ROOT / "backend/sql/010_event_ship_links.sql").read_text(encoding="utf-8")

EVENTS_WITH_GEO = text("""
SELECT id, event_id, title_zh, event_datetime, publish_date_min, publish_date_max,
       event_lat, event_lng
FROM events
WHERE event_lat IS NOT NULL AND event_lng IS NOT NULL
""")

MENTIONED = text("""
INSERT INTO event_ship_links (event_id, link_type, vessel_name, evidence)
SELECT e.id, 'mentioned', name,
       jsonb_build_object('source', 'events.mentioned_vessels', 'vessel_name', name)
FROM events e, jsonb_array_elements_text(e.mentioned_vessels) AS name
""")

# One event at a time (events are few). Window: event_datetime ± half-window when
# present, else the publish-date span [min 00:00, max+1day). Distance from the
# event point to the window-clipped trajectory in EPSG:32640.
# NOTE: never pass a span as text parameter — MobilityDB's span input function
# misparses parameter values (verified 2026-09-19); use span(t, t) instead.
OBSERVED_FOR_EVENT = text("""
WITH windowed AS (
  SELECT t.ship_id, t.segment_no,
         atTime(t.track, span(CAST(:window_start AS timestamptz), CAST(:window_end AS timestamptz))) AS trip
  FROM ship_tracks t
  WHERE t.t_start < :window_end AND t.t_end > :window_start
), clipped AS (
  SELECT ship_id, segment_no, atGeometry(trip, :buffer) AS part
  FROM windowed
), distances AS (
  SELECT c.ship_id, c.segment_no,
         ST_Distance(:event_point, trajectory(c.part)::geometry) AS dist
  FROM clipped c
)
SELECT s.id AS ship_id, s.name, s.mmsi, d.segment_no, d.dist
FROM distances d JOIN ships s ON s.id = d.ship_id
WHERE d.dist <= :radius_m
ORDER BY d.dist
""")

SUMMARY = text("""
SELECT link_type, count(*) FROM event_ship_links GROUP BY link_type
""")

HASH_ROWS = text("""
SELECT event_id, ship_id, link_type, vessel_name, confidence, evidence
FROM event_ship_links ORDER BY id
""")


def main():
    parser = argparse.ArgumentParser(description="Rebuild event_ship_links derived layer")
    parser.add_argument("--radius-km", type=float, default=50.0)
    parser.add_argument("--half-window-hours", type=int, default=12)
    parser.add_argument("--srid", type=int, default=32640)
    args = parser.parse_args()
    if args.radius_km <= 0 or args.half_window_hours <= 0:
        raise SystemExit("radius-km 与 half-window-hours 必须为正数")

    radius_m = args.radius_km * 1000.0
    with engine.begin() as db:
        before = fingerprints(db)
        db.execute(text(DDL))
        db.execute(text("DELETE FROM event_ship_links"))

        db.execute(MENTIONED)
        mentioned_count = db.execute(text("SELECT count(*) FROM event_ship_links WHERE link_type='mentioned'")).scalar()

        events = db.execute(EVENTS_WITH_GEO).mappings().all()
        observed_rows = []
        for event in events:
            if event["event_datetime"] is not None:
                start = event["event_datetime"].timestamp() - args.half_window_hours * 3600
                end = event["event_datetime"].timestamp() + args.half_window_hours * 3600
            else:
                lo = event["publish_date_min"]
                hi = event["publish_date_max"]
                if lo is None or hi is None:
                    continue
                from datetime import datetime, timezone
                start = datetime(lo.year, lo.month, lo.day, tzinfo=timezone.utc).timestamp()
                end = datetime(hi.year, hi.month, hi.day, tzinfo=timezone.utc).timestamp() + 86400
            span = f"[{datetime_from_epoch(start)}, {datetime_from_epoch(end)})"
            buffer_sql = text(
                "SELECT ST_Buffer(ST_Transform("
                "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geometry, :srid), :radius_m)"
            )
            buffer = db.execute(buffer_sql, {
                "lng": event["event_lng"], "lat": event["event_lat"],
                "srid": args.srid, "radius_m": radius_m,
            }).scalar()
            event_point = db.execute(text(
                "SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geometry, :srid)"
            ), {"lng": event["event_lng"], "lat": event["event_lat"], "srid": args.srid}).scalar()
            from datetime import datetime, timezone
            candidates = db.execute(OBSERVED_FOR_EVENT, {
                "window_start": datetime.fromtimestamp(start, tz=timezone.utc),
                "window_end": datetime.fromtimestamp(end, tz=timezone.utc),
                "buffer": buffer, "event_point": event_point, "radius_m": radius_m,
            }).mappings().all()
            for candidate in candidates:
                confidence = max(0.0, round(1.0 - float(candidate["dist"]) / radius_m, 3))
                db.execute(text("""
                    INSERT INTO event_ship_links
                        (event_id, ship_id, link_type, confidence, evidence)
                    VALUES (:event_id, :ship_id, 'observed', :confidence, :evidence)
                """), {
                    "event_id": event["id"],
                    "ship_id": candidate["ship_id"],
                    "confidence": confidence,
                    "evidence": json.dumps({
                        "event_id": event["event_id"],
                        "window": [datetime_from_epoch(start), datetime_from_epoch(end)],
                        "radius_km": args.radius_km,
                        "min_distance_m": round(float(candidate["dist"]), 1),
                        "segment_no": candidate["segment_no"],
                        "demo": True,
                        "note": "模拟数据时空邻近演示，不构成真实因果",
                    }),
                })
                observed_rows.append({
                    "event_id": event["event_id"], "ship": candidate["name"],
                    "distance_m": round(float(candidate["dist"]), 1),
                })

        assert fingerprints(db) == before, "source tables changed during rebuild"
        summary = {row["link_type"]: row["count"] for row in db.execute(SUMMARY).mappings()}
        digest = hashlib.sha256()
        for row in db.execute(HASH_ROWS).mappings():
            digest.update("|".join(str(row[key]) for key in row.keys()).encode())
            digest.update(b"\n")
        manifest_id = db.execute(text("""
            INSERT INTO track_build_manifest (table_name, row_count, sha256, params)
            VALUES ('event_ship_links', :row_count, :sha256, :params)
            RETURNING id
        """), {
            "row_count": sum(summary.values()),
            "sha256": digest.hexdigest(),
            "params": json.dumps({
                "radius_km": args.radius_km,
                "half_window_hours": args.half_window_hours,
                "srid": args.srid,
                "mentioned": summary.get("mentioned", 0),
                "observed": summary.get("observed", 0),
                "geolocated_events": len(events),
            }),
        }).scalar_one()

    result = {
        "manifest_id": manifest_id,
        "sha256": digest.hexdigest(),
        "summary": summary,
        "observed_preview": observed_rows[:10],
        "source_tables_unchanged": True,
    }
    target = ROOT / "sim_ais_demo/output_news_aligned/event_ship_links_build.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def datetime_from_epoch(epoch: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")


if __name__ == "__main__":
    main()
