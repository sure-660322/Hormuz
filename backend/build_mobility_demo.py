"""Build a bounded MobilityDB pilot without changing source records."""
import json
from pathlib import Path
from sqlalchemy import text
from backend.app.database import engine

ROOT = Path(__file__).resolve().parents[1]
BUILD = """
WITH selected AS (
  SELECT s.id FROM ships s WHERE s.name LIKE 'SIM %' AND EXISTS (
    SELECT 1 FROM ship_positions p WHERE p.ship_id=s.id
    AND p.data_source='simulation'
    AND p.longitude BETWEEN 56.15 AND 56.75 AND p.latitude BETWEEN 26.20 AND 26.95
  ) ORDER BY s.mmsi LIMIT 10
), samples AS (
  SELECT p.*, lag(recorded_at) OVER (PARTITION BY ship_id ORDER BY recorded_at,p.id) AS previous
  FROM ship_positions p JOIN selected s ON s.id=p.ship_id
  WHERE data_source='simulation'
), numbered AS (
  SELECT *, sum(CASE WHEN previous IS NULL OR recorded_at-previous > interval '90 minutes'
    THEN 1 ELSE 0 END) OVER (PARTITION BY ship_id ORDER BY recorded_at,id) AS segment
  FROM samples
)
INSERT INTO mobility_demo_segments(ship_id,segment_no,track,point_count)
SELECT ship_id,segment,
  tgeompointSeq(array_agg(tgeompoint(ST_Transform(location::geometry,32640),recorded_at)
    ORDER BY recorded_at,id), 'Linear', true,true), count(*)
FROM numbered GROUP BY ship_id,segment HAVING count(*)>=2
"""

def fingerprints(db):
    return {table: dict(db.execute(text(
        f'SELECT count(*) AS count, md5(string_agg(row_to_json(t)::text, chr(10) ORDER BY id)) AS digest FROM {table} t'
    )).mappings().one()) for table in ('ships','ship_positions','events','news')}

def main():
    with engine.begin() as db:
        before = fingerprints(db)
        db.execute(text((ROOT/'backend/sql/007_mobility_demo_segments.sql').read_text()))
        # This dedicated derived table is the sole rebuild scope.
        db.execute(text('DELETE FROM mobility_demo_segments'))
        db.execute(text(BUILD))
        assert fingerprints(db)==before
        result = dict(db.execute(text('SELECT count(*) AS segments, count(DISTINCT ship_id) AS ships, sum(point_count) AS points FROM mobility_demo_segments')).mappings().one())
        assert result['ships']==10
        result['source_tables_unchanged']=True
        result['source_fingerprints']=before
    target=ROOT/'sim_ais_demo/output/mobility_build.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='source_fingerprints'}))

if __name__=='__main__':
    main()
