"""Repository layer for P2 event-ship links: parameterized read-only SQL."""
from sqlalchemy import text
from sqlalchemy.orm import Session

LINKS_FOR_EVENT = text("""
SELECT l.id, l.link_type, l.vessel_name, l.confidence, l.evidence,
       l.ship_id, s.mmsi, s.name AS ship_name, s.ship_type
FROM event_ship_links l
LEFT JOIN ships s ON s.id = l.ship_id
WHERE l.event_id = (SELECT id FROM events WHERE event_id = :event_id)
ORDER BY l.link_type DESC, l.confidence ASC NULLS LAST, l.id
""")

EVENT_BY_BUSINESS_ID = text("""
SELECT id, event_id, title_zh, event_datetime, event_time_text,
       publish_date_min, publish_date_max
FROM events WHERE event_id = :event_id
""")

OBSERVED_FOR_SHIP = text("""
SELECT l.id, l.confidence, l.evidence,
       e.event_id, e.title_zh, e.event_type, e.event_datetime, e.event_time_text,
       e.publish_date_min, e.publish_date_max, e.event_lat, e.event_lng
FROM event_ship_links l
JOIN events e ON e.id = l.event_id
WHERE l.link_type = 'observed' AND l.ship_id = :ship_id
  AND (CAST(:from_raw AS timestamptz) IS NULL OR
       e.event_datetime >= CAST(:from_raw AS timestamptz)
       OR (e.event_datetime IS NULL AND e.publish_date_max >= CAST(:from_raw AS date)))
  AND (CAST(:to_raw AS timestamptz) IS NULL OR
       e.event_datetime < CAST(:to_raw AS timestamptz)
       OR (e.event_datetime IS NULL AND e.publish_date_min < CAST(:to_raw AS date)))
ORDER BY e.event_datetime NULLS LAST, e.publish_date_min, e.event_id
""")

MANIFEST = text("""
SELECT row_count, built_at, params FROM track_build_manifest
WHERE table_name = 'event_ship_links' ORDER BY id DESC LIMIT 1
""")


def fetch_event_by_id(db: Session, event_id: str):
    return db.execute(EVENT_BY_BUSINESS_ID, {"event_id": event_id}).mappings().one_or_none()


def fetch_links_for_event(db: Session, event_pk: int, event_id: str):
    return db.execute(LINKS_FOR_EVENT, {"event_id": event_id}).mappings().all()


def fetch_observed_for_ship(db: Session, ship_id: int, from_raw, to_raw):
    return db.execute(
        OBSERVED_FOR_SHIP, {"ship_id": ship_id, "from_raw": from_raw, "to_raw": to_raw}
    ).mappings().all()


def fetch_manifest(db: Session):
    return db.execute(MANIFEST).mappings().one_or_none()
