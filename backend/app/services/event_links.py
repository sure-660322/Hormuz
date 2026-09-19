"""Service layer for P2 event-ship link APIs.

Red lines enforced in the response shape:
- mentioned links never carry a ship (text evidence only);
- observed links are simulation-only and always carry the demo disclaimer.
"""
import json

from sqlalchemy.orm import Session

from backend.app.repositories import event_links as links_repo
from backend.app.services.tracks import parse_window

OBSERVED_NOTE = "模拟数据时空邻近演示，不构成真实因果"
MENTIONED_NOTE = "新闻原文提及的真实船舶名称；与数据库中模拟船不按名称关联，未认定同一实体"


def _params(manifest):
    return manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])


def get_event_ships(db: Session, event_id: str) -> dict:
    event = links_repo.fetch_event_by_id(db, event_id)
    if event is None:
        return {"status": "not_found", "event_id": event_id}

    rows = links_repo.fetch_links_for_event(db, event["id"], event_id)
    mentioned, observed = [], []
    # observed may repeat a ship across segments; keep the strongest (closest) one.
    best_by_ship: dict = {}
    for row in rows:
        if row["link_type"] == "mentioned":
            mentioned.append({
                "link_type": "mentioned",
                "vessel_name": row["vessel_name"],
                "ship": None,
                "confidence": None,
                "note": MENTIONED_NOTE,
            })
            continue
        current = best_by_ship.get(row["ship_id"])
        if current is None or row["confidence"] > current["confidence"]:
            best_by_ship[row["ship_id"]] = row
    for row in sorted(best_by_ship.values(), key=lambda r: -(r["confidence"] or 0)):
        observed.append({
            "link_type": "observed",
            "ship": {
                "id": row["ship_id"], "mmsi": row["mmsi"],
                "name": row["ship_name"], "ship_type": row["ship_type"],
            },
            "confidence": row["confidence"],
            "min_distance_m": row["evidence"].get("min_distance_m"),
            "window": row["evidence"].get("window"),
            "is_simulated": True,
            "note": OBSERVED_NOTE,
        })

    manifest = links_repo.fetch_manifest(db)
    return {
        "status": "ok",
        "event_id": event["event_id"],
        "title_zh": event["title_zh"],
        "links": observed + mentioned,
        "built_at": manifest["built_at"] if manifest else None,
        "params": _params(manifest) if manifest else None,
    }


def get_ship_events(db: Session, ship_id: int, from_raw: str | None, to_raw: str | None) -> dict:
    start, end = parse_window(from_raw, to_raw)
    rows = links_repo.fetch_observed_for_ship(
        db, ship_id,
        start.isoformat() if start else None,
        end.isoformat() if end else None,
    )
    manifest = links_repo.fetch_manifest(db)
    observed = []
    for row in rows:
        observed.append({
            "event_id": row["event_id"],
            "title_zh": row["title_zh"],
            "event_type": row["event_type"],
            "event_datetime": row["event_datetime"],
            "event_time_text": row["event_time_text"],
            "publish_date_min": row["publish_date_min"],
            "publish_date_max": row["publish_date_max"],
            "representative_point": (
                {"lng": row["event_lng"], "lat": row["event_lat"]}
                if row["event_lat"] is not None else None
            ),
            "confidence": row["confidence"],
            "min_distance_m": row["evidence"].get("min_distance_m"),
            "note": OBSERVED_NOTE,
        })
    return {
        "status": "ok" if observed else "no_data",
        "ship_id": ship_id,
        "window": [start, end] if start else None,
        "observed": observed,
        "mentioned": [],
        "mentioned_note": "文本提及类关联不指向模拟船，见 GET /api/events/{event_id}/ships",
        "built_at": manifest["built_at"] if manifest else None,
    }
