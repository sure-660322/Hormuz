"""Independent numerical check of MobilityDB's polygon/time clipping."""
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from sqlalchemy import text
from backend.app.database import SessionLocal
from backend.app.routers.mobility import analysis, AREAS
from backend.build_mobility_demo import fingerprints

def fraction_in_polygon(a,b,ring):
    # Convex polygon half-plane clipping, independent of MobilityDB.
    orientation=1 if sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(ring,ring[1:]))>0 else -1
    lower,upper=0.0,1.0
    for p,q in zip(ring,ring[1:]):
        cross=lambda r: orientation*((q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0]))
        c=cross(a); delta=cross(b)-c
        if abs(delta)<1e-10:
            if c < -1e-8:return 0
        elif delta>0:lower=max(lower,-c/delta)
        else:upper=min(upper,-c/delta)
    return max(0,upper-lower)

def main():
    root=Path(__file__).resolve().parents[1]
    report={}
    with SessionLocal() as db:
        baseline=json.loads((root/'sim_ais_demo/output/mobility_build.json').read_text())
        assert fingerprints(db)==baseline['source_fingerprints']
        report['source_tables_unchanged']=True
        schema=db.execute(text("SELECT format_type(atttypid,atttypmod) FROM pg_attribute WHERE attrelid='mobility_demo_segments'::regclass AND attname='track'")).scalar_one()
        assert schema=='tgeompoint'
        assert db.execute(text("SELECT count(*) FROM pg_indexes WHERE tablename='mobility_demo_segments' AND indexdef LIKE '%USING gist%'")).scalar_one()==1
        # One hour crossing: middle half of the segment is in the test area.
        synthetic=db.execute(text("""SELECT extract(epoch FROM duration(atGeometry(
          'SRID=32640;[Point(0 0)@2026-01-01 00:00+00, Point(100 0)@2026-01-01 01:00+00]'::tgeompoint,
          ST_MakeEnvelope(25,-10,75,10,32640)),false))""")).scalar_one()
        assert float(synthetic)==1800
        gap=db.execute(text("""SELECT extract(epoch FROM duration(
          'SRID=32640;{[Point(0 0)@2026-01-01 00:00+00, Point(1 0)@2026-01-01 01:00+00], [Point(2 0)@2026-01-01 03:00+00, Point(3 0)@2026-01-01 04:00+00]}'::tgeompoint,false))""")).scalar_one()
        assert float(gap)==7200
        report['synthetic_crossing_seconds']=float(synthetic)
        report['two_segments_excluding_gap_seconds']=float(gap)
        source=defaultdict(list)
        rows=db.execute(text('''SELECT p.ship_id,p.recorded_at,ST_X(ST_Transform(p.location::geometry,32640)) AS x,ST_Y(ST_Transform(p.location::geometry,32640)) AS y
        FROM ship_positions p WHERE p.ship_id IN (SELECT DISTINCT ship_id FROM mobility_demo_segments) ORDER BY p.ship_id,p.recorded_at,p.id''')).mappings()
        for row in rows:source[row['ship_id']].append(row)
        for area,bounds in AREAS.items():
            result=analysis(area,db)
            ring=json.loads(db.execute(text('SELECT ST_AsGeoJSON(ST_Transform(ST_MakeEnvelope(:w,:s,:e,:n,4326),32640),12)'),dict(zip(('w','s','e','n'),bounds))).scalar_one())['coordinates'][0]
            errors=[]
            for ship in result['ships']:
                for label,(start,end) in result['windows'].items():
                    start=datetime.fromisoformat(start);end=datetime.fromisoformat(end)
                    covered=inside=0
                    for a,b in zip(source[ship['id']],source[ship['id']][1:]):
                        dt=(b['recorded_at']-a['recorded_at']).total_seconds()
                        if not 0<dt<=5400:continue
                        lower=max(start,a['recorded_at']);upper=min(end,b['recorded_at'])
                        if upper<=lower:continue
                        seconds=(upper-lower).total_seconds();covered+=seconds
                        def point(t):
                            f=(t-a['recorded_at']).total_seconds()/dt
                            return (a['x']+f*(b['x']-a['x']),a['y']+f*(b['y']-a['y']))
                        inside+=seconds*fraction_in_polygon(point(lower),point(upper),ring)
                    errors.extend([abs(inside/3600-ship[label]['area_hours']),abs(covered/3600-ship[label]['covered_hours'])])
                    assert 0<=ship[label]['area_hours']<=ship[label]['covered_hours']+0.0001<=48.0001
            assert max(errors)<0.0001, max(errors)
            report[area]={'max_difference_hours':max(errors),'analysis':result}
    target=root/'sim_ais_demo/output/mobility_verification.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v if k not in AREAS else v['max_difference_hours'] for k,v in report.items()}))

if __name__=='__main__':main()
