"""Verify package, relational/spatial structure and HTTP reads on handoff DB only."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
for key, value in dotenv_values(ROOT / 'deploy/handoff.env').items():
    if key.startswith('DB_') and value:
        os.environ[key] = value

from backend.handoff import load_package, verify
from backend.app.database import engine
from sqlalchemy import text


def main():
    rows = load_package()
    with engine.connect() as db:
        verify(db, rows)
        assert db.scalar(text("SELECT attgenerated FROM pg_attribute WHERE attrelid='ship_positions'::regclass AND attname='location'")) == 's'
        assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE schemaname='public' AND indexname IN ('idx_ship_positions_location','idx_ship_positions_ship_recorded_at')")) == 2
        assert db.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid IN ('ship_positions'::regclass,'news'::regclass) AND contype='f'")) == 2
        for table in ('ships', 'ship_positions', 'events', 'news'):
            assert db.scalar(text(f'SELECT last_value FROM {table}_id_seq')) >= max(r['id'] for r in rows[table])
        linked = db.scalar(text('SELECT count(*) FROM news WHERE event_id IS NOT NULL'))
    # A separate port avoids the maintainer's running API.
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '18001'],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    checked = []
    try:
        for _ in range(40):
            if process.poll() is not None:
                raise RuntimeError('Test API failed to start (port may be occupied)')
            try:
                with urlopen('http://127.0.0.1:18001/health', timeout=1):
                    break
            except OSError:
                time.sleep(0.25)
        for route in ['/health', '/docs', '/ships', '/ships/map', '/events', '/events/evt_001/news',
                      '/simulation/meta', '/mobility-demo/analysis', '/mobility-demo/tracks']:
            with urlopen('http://127.0.0.1:18001' + route, timeout=15) as response:
                assert response.status == 200
                body = response.read()
                if route != '/docs':
                    payload = json.loads(body)
                    if route == '/ships': assert len(payload) == len(rows['ships'])
                    if route == '/events': assert len(payload) == len(rows['events'])
                checked.append(route)
    finally:
        process.terminate()
        process.wait(timeout=10)
    print(json.dumps({'checks': checked, 'linked_news': linked, 'unlinked_news': len(rows['news'])-linked,
                      'rows_match_package': True, 'generated_column_indexes_foreign_keys_sequences': True}))


if __name__ == '__main__':
    main()
