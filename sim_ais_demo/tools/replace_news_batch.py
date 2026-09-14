"""Replace the identified old simulation atomically, with a verified local backup."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sqlalchemy import create_engine, text
from backend.app.database import DATABASE_URL
from backend.build_mobility_demo import BUILD
from sim_ais_demo.tools.import_to_db import SHIP_INSERT, POSITION_INSERT, load_jsonl

OUT = ROOT / 'sim_ais_demo/output_news_aligned'


def digest_table(db, table):
    return dict(db.execute(text(
        f'SELECT count(*) AS count, md5(string_agg(row_to_json(t)::text, chr(10) ORDER BY id)) AS digest FROM {table} t'
    )).mappings().one())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    paths = {p.name: p for folder in (OUT, OUT/'positions_by_date', OUT/'raw_observations', OUT/'quarantine')
             for p in folder.iterdir() if p.is_file()}
    for name, expected in manifest['files'].items():
        actual = hashlib.sha256(paths[name].read_text(encoding='utf-8').encode('utf-8')).hexdigest()
        assert actual == expected, f'Batch digest mismatch: {name}'
    for name in ('acceptance_report_file_only.json','news_alignment_report.json'):
        assert not json.loads((OUT/name).read_text(encoding='utf-8'))['failures'], name
    ships = load_jsonl(OUT/'ships.jsonl')
    positions = [r for p in sorted((OUT/'positions_by_date').glob('*.jsonl')) for r in load_jsonl(p)]
    assert (len(ships), len(positions)) == (30, 9354)
    old_ships = load_jsonl(ROOT/'sim_ais_demo/output/ships.jsonl')
    old_identities = {(s['mmsi'], s['name'], s['callsign']) for s in old_ships}
    engine = create_engine(DATABASE_URL, connect_args={'connect_timeout':5})
    with engine.begin() as db:
        db.execute(text("SET LOCAL lock_timeout = '5s'"))
        db.execute(text("SET LOCAL statement_timeout = '60s'"))
        db.execute(text('LOCK TABLE ships, ship_positions, mobility_demo_segments IN SHARE ROW EXCLUSIVE MODE'))
        current = db.execute(text('SELECT id,mmsi,name,callsign FROM ships ORDER BY id')).mappings().all()
        assert {(s['mmsi'],s['name'],s['callsign']) for s in current} == old_identities, 'Existing ships differ from identified old batch; no deletion.'
        assert db.execute(text("SELECT count(*) FROM ship_positions WHERE data_source != 'simulation'")).scalar_one() == 0
        old_count = db.execute(text('SELECT count(*) FROM ship_positions')).scalar_one()
        assert old_count == 58567, 'Old position count changed; no deletion.'
        protected = {t:digest_table(db,t) for t in ('events','news')}
        report = {'mode':'apply' if args.apply else 'dry-run','old_ships':len(current),'old_positions':old_count,
                  'new_ships':len(ships),'new_positions':len(positions),'protected_before':protected}
        if not args.apply:
            print(json.dumps(report,ensure_ascii=False))
            return
        backup = OUT/'database_backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True,exist_ok=False)
        hashes = {}
        for table, order in [('ships','id'),('ship_positions','id'),('mobility_demo_segments','ship_id,segment_no')]:
            rows = db.execute(text(f'SELECT row_to_json(t)::text FROM {table} t ORDER BY {order}')).scalars().all()
            data = '\n'.join(rows)+'\n'
            target = backup/f'{table}.jsonl'
            target.write_text(data,encoding='utf-8')
            reread = target.read_text(encoding='utf-8')
            assert reread == data and len(reread.splitlines()) == len(rows)
            hashes[table]={'rows':len(rows),'sha256':hashlib.sha256(reread.encode('utf-8')).hexdigest()}
        (backup/'manifest.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
        db.execute(text('DELETE FROM mobility_demo_segments'))
        assert db.execute(text('DELETE FROM ship_positions')).rowcount == old_count
        assert db.execute(text('DELETE FROM ships')).rowcount == len(current)
        mapping = {}
        for ship in ships:
            mapping[ship['temp_ship_id']] = db.execute(SHIP_INSERT,ship).scalar_one()
        for start in range(0,len(positions),2000):
            db.execute(POSITION_INSERT,[{**r,'ship_id':mapping[r['temp_ship_id']]} for r in positions[start:start+2000]])
        db.execute(text(BUILD))
        derived = dict(db.execute(text('SELECT count(*) AS segments,count(DISTINCT ship_id) AS ships,sum(point_count) AS points FROM mobility_demo_segments')).mappings().one())
        assert derived['ships'] == 10
        assert {t:digest_table(db,t) for t in protected} == protected, 'News changed; rolling back.'
        assert db.execute(text('SELECT count(*) FROM ships')).scalar_one() == len(ships)
        assert db.execute(text('SELECT count(*) FROM ship_positions')).scalar_one() == len(positions)
        assert db.execute(text("SELECT count(*) FROM ship_positions WHERE location IS NULL OR data_source != 'simulation'")).scalar_one() == 0
        # Read back all inserted business fields and compare with the delivered batch.
        actual = db.execute(text('SELECT ship_id,latitude,longitude,speed,course,heading,recorded_at,unix_time,nav_status,rot,draught_m,destination,ais_type,data_source FROM ship_positions')).mappings().all()
        expected = {(mapping[r['temp_ship_id']],datetime.fromisoformat(r['recorded_at'])):r for r in positions}
        for row in actual:
            source = expected[(row['ship_id'],row['recorded_at'])]
            assert all(row[k] == source[k] for k in row if k not in ('ship_id','recorded_at')), 'Database readback differs from source.'
        report.update(backup=str(backup),backup_hashes=hashes,protected_unchanged=True,
                      mobility_rebuilt=derived,readback_positions_verified=len(actual),temp_ship_id_to_real_id=mapping)
    report['committed']=True
    report['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    (OUT/'database_replace_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
