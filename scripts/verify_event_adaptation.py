"""Read-only feasibility probe; does not modify application code or database."""
from collections import Counter
from datetime import date, datetime
import json
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from backend.app.database import engine

# Snapshot of the pre-adaptation contract, retained only for this research probe.
class EventResponse(BaseModel):
    id: int
    title: str
    description: str
    event_type: str
    latitude: float
    longitude: float
    occurred_at: datetime
    source_name: str | None
    source_url: str | None


class NewsSummary(BaseModel):
    story_id: str
    title_zh: str
    canonical_url: str
    media_name: str
    perspective: str
    publish_date: date


class CandidateEvent(BaseModel):
    # A proof of the core response contract, not a production API implementation.
    id: int
    event_id: str
    title_zh: str
    summary_zh: str
    event_type: str
    event_datetime: datetime | None
    event_time_text: str | None
    event_lat: float | None
    event_lng: float | None
    event_points: list[dict] | None
    geo_method: str | None
    geo_note: str | None
    coverage_count: int
    news: list[NewsSummary]


SPATIAL = """
WITH latest AS (
 SELECT DISTINCT ON (ship_id) ship_id,location
 FROM ship_positions ORDER BY ship_id,recorded_at DESC,id DESC
), points AS (
 SELECT id, ST_SetSRID(ST_MakePoint(event_lng,event_lat),4326)::geography location
 FROM events WHERE event_lat IS NOT NULL AND event_lng IS NOT NULL
)
SELECT s.ship_id,e.id,ST_Distance(s.location,e.location)/1000 AS distance_km
FROM latest s CROSS JOIN points e
WHERE ST_DWithin(s.location,e.location,20000)
ORDER BY s.ship_id,distance_km,e.id
"""


def main():
    result = {}
    with engine.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        c.execute(text("SET LOCAL statement_timeout='15s'"))
        result['transaction_read_only'] = c.execute(text('SHOW transaction_read_only')).scalar_one()
        events = [dict(r) for r in c.execute(text('SELECT * FROM public.events ORDER BY id')).mappings()]
        news = [dict(r) for r in c.execute(text('SELECT event_id,story_id,title_zh,canonical_url,media_name,perspective,publish_date FROM public.news ORDER BY publish_date,story_id')).mappings()]
        start, end = c.execute(text('SELECT min(recorded_at),max(recorded_at) FROM ship_positions')).one()
        result['ship_window'] = [start, end]
        candidates = [CandidateEvent.model_validate({**e, 'news': [n for n in news if n['event_id'] == e['id']]}) for e in events]
        assert all(len(e.news) == e.coverage_count for e in candidates)
        result['candidate_contract'] = {'events': len(candidates), 'linked_news': sum(len(e.news) for e in candidates),
            'unlinked_news': sum(n['event_id'] is None for n in news), 'serialized_bytes': len(json.dumps([e.model_dump(mode='json') for e in candidates], ensure_ascii=False).encode())}
        result['profile'] = {
            'coordinates_present': sum(e.event_lat is not None and e.event_lng is not None for e in candidates),
            'time_present': sum(e.event_datetime is not None for e in candidates),
            'within_ship_window': sum(e.event_datetime is not None and start <= e.event_datetime <= end for e in candidates),
            'with_point_arrays': sum(bool(e.event_points) for e in candidates),
            'point_count': sum(len(e.event_points or []) for e in candidates),
            'types': dict(Counter(e.event_type for e in candidates)),
            'geo_methods': dict(Counter(e.geo_method for e in candidates)),
        }
        legacy_pass = 0
        for e in candidates:
            try:
                EventResponse.model_validate(dict(id=e.id,title=e.title_zh,description=e.summary_zh,event_type=e.event_type,
                    latitude=e.event_lat,longitude=e.event_lng,occurred_at=e.event_datetime,source_name=None,source_url=None))
                legacy_pass += 1
            except ValidationError:
                pass
        result['rename_only_legacy_contract'] = {'pass': legacy_pass, 'fail':len(events)-legacy_pass}
        point_errors = []
        for e in candidates:
            for p in e.event_points or []:
                if not (isinstance(p.get('lat'), (int,float)) and isinstance(p.get('lng'), (int,float))
                        and -90 <= p['lat'] <= 90 and -180 <= p['lng'] <= 180):
                    point_errors.append(e.event_id)
        result['invalid_point_coordinates'] = point_errors
        started = perf_counter()
        nearby = c.execute(text(SPATIAL)).all()
        result['representative_point_spatial_probe'] = {'radius_km':20,'ship_event_pairs':len(nearby),
            'elapsed_ms':round((perf_counter()-started)*1000,2),'note':'One local run; geographical comparison only, no same-time relation.'}
        result['spatial_plan'] = [r[0] for r in c.execute(text('EXPLAIN (ANALYZE, BUFFERS) '+SPATIAL))]
        result['event_news_fk_index'] = [r[0] for r in c.execute(text("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='news'"))]
        result['same_name_ship_matches'] = c.execute(text("SELECT count(*) FROM events e CROSS JOIN LATERAL jsonb_array_elements_text(e.mentioned_vessels) v(name) JOIN ships s ON lower(s.name)=lower(v.name)")).scalar_one()
    output = Path(__file__).resolve().parents[1] / 'docs/event_adaptation_verification.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['spatial_plan','event_news_fk_index']},default=str,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
