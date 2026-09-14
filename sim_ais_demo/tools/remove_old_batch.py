"""Remove only the unchanged old batch verified before the new import."""
import json
import sys
from pathlib import Path
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.database import SessionLocal

out = ROOT / 'sim_ais_demo/output'
before = json.loads((out / 'db_before_import.json').read_text())
applied = json.loads((out / 'import_applied.json').read_text())
keep = list(applied['temp_ship_id_to_real_id'].values())
with SessionLocal.begin() as db:
    db.execute(text('LOCK TABLE ships, ship_positions IN SHARE ROW EXCLUSIVE MODE'))
    old = {}
    for table, column in [('ships', 'id'), ('ship_positions', 'ship_id')]:
        condition = f'{column} != ALL(:ids)'
        digest = dict(db.execute(text(f'SELECT count(*) AS count, md5(string_agg(row_to_json(t)::text, chr(10) ORDER BY id)) AS digest FROM {table} t WHERE {condition}'), {'ids': keep}).mappings().one())
        assert digest == before[table], f'{table}: old data changed; refusing deletion'
        old[table] = db.execute(text(f'SELECT row_to_json(t)::text FROM {table} t WHERE {condition} ORDER BY id'), {'ids': keep}).scalars().all()
    assert len(old['ships']) == 150 and len(old['ship_positions']) == 14400
    assert all(json.loads(row)['data_source'] == 'simulation' for row in old['ship_positions'])
    backup = out / 'old_batch_backup'
    backup.mkdir(exist_ok=True)
    for table, rows in old.items():
        target = backup / f'{table}.jsonl'
        with target.open('x', encoding='utf-8') as handle:
            handle.write('\n'.join(rows) + '\n')
        assert len(target.read_text(encoding='utf-8').splitlines()) == len(rows)
    positions = db.execute(text('DELETE FROM ship_positions WHERE ship_id != ALL(:ids)'), {'ids': keep}).rowcount
    ships = db.execute(text('DELETE FROM ships WHERE id != ALL(:ids)'), {'ids': keep}).rowcount
    assert (ships, positions) == (150, 14400)
    for table in ['events', 'news']:
        current = dict(db.execute(text(f'SELECT count(*) AS count, md5(string_agg(row_to_json(t)::text, chr(10) ORDER BY id)) AS digest FROM {table} t')).mappings().one())
        assert current == before[table]
print(json.dumps({'deleted_ships': ships, 'deleted_positions': positions, 'backup': str(backup)}))
