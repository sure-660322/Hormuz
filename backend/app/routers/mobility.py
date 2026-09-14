"""Read-only MobilityDB pilot: estimated area occupancy, never news causality."""
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.database import get_db

router=APIRouter(prefix='/mobility-demo',tags=['mobility-demo'])
AREAS={'strait': [56.15,26.20,56.75,26.95], 'approach': [56.0,25.8,57.3,27.1]}
QUERY="""
WITH windows(label,period) AS (VALUES
 ('before', tstzspan '[2026-02-26 00:00+00,2026-02-28 00:00+00)'),
 ('after', tstzspan '[2026-03-01 00:00+00,2026-03-03 00:00+00)')),
 clipped AS (
 SELECT d.ship_id,w.label,atTime(d.track,w.period) AS trip
 FROM mobility_demo_segments d CROSS JOIN windows w
), totals AS (
 SELECT ship_id,label,
 sum(extract(epoch FROM duration(trip,false)))/3600.0 AS covered_hours,
 sum(coalesce(extract(epoch FROM duration(atGeometry(trip,
 ST_Transform(ST_MakeEnvelope(:west,:south,:east,:north,4326),32640)),false)),0))/3600.0 AS area_hours
 FROM clipped GROUP BY ship_id,label
)
SELECT s.id,s.mmsi,s.name,t.label,coalesce(t.covered_hours,0) AS covered_hours,
 coalesce(t.area_hours,0) AS area_hours
FROM totals t JOIN ships s ON s.id=t.ship_id ORDER BY s.mmsi,t.label
"""

@router.get('', include_in_schema=False)
def page():
    return FileResponse(Path(__file__).resolve().parents[1]/'pages/mobility-demo.html')

@router.get('/analysis')
def analysis(area: Literal['strait','approach']='strait', db: Session=Depends(get_db)):
    west,south,east,north=AREAS[area]
    rows=db.execute(text(QUERY),dict(west=west,south=south,east=east,north=north)).mappings().all()
    ships={}
    for row in rows:
        ship=ships.setdefault(row['id'],dict(id=row['id'],name=row['name'],mmsi=row['mmsi']))
        ship[row['label']]={key:round(float(row[key]),4) for key in ('area_hours','covered_hours')}
    return {'area':area,'bounds':[west,south,east,north], 'ships':list(ships.values()),
      'is_simulated':True,'gap_minutes':90,'window_hours':48,
      'windows':{'before':['2026-02-26T00:00:00Z','2026-02-28T00:00:00Z'],
                 'after':['2026-03-01T00:00:00Z','2026-03-03T00:00:00Z']},
      'segments':db.scalar(text('SELECT count(*) FROM mobility_demo_segments')),
      'built_at':db.scalar(text('SELECT max(built_at) FROM mobility_demo_segments'))}

@router.get('/tracks')
def tracks(db: Session=Depends(get_db)):
    import json
    rows=db.execute(text('SELECT ship_id, ST_AsGeoJSON(ST_Transform(trajectory(track),4326)) AS geometry FROM mobility_demo_segments ORDER BY ship_id,segment_no')).mappings()
    return {'type':'FeatureCollection','features':[{'type':'Feature','properties':{'ship_id':r['ship_id']},'geometry':json.loads(r['geometry'])} for r in rows]}
