"""Run against deploy/handoff.env without changing the maintainer's root .env."""
import runpy
import sys
from pathlib import Path
from dotenv import dotenv_values
import os

path = Path(__file__).resolve().parents[1] / 'deploy/handoff.env'
values = dotenv_values(path)
required = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']
if any(not values.get(k) for k in required) or values.get('DB_PASSWORD') == 'CHANGE_ME':
    raise SystemExit('Configure deploy/handoff.env with a new local password first.')
for key in required:
    os.environ[key] = values[key]

if sys.argv[1:] == ['build-mobility']:
    from backend.build_mobility_demo import BUILD, fingerprints
    from backend.app.database import engine
    from sqlalchemy import text
    from backend.handoff import load_package, verify
    with engine.begin() as db:
        verify(db, load_package())
        before = fingerprints(db)
        db.execute(text('DELETE FROM mobility_demo_segments'))
        db.execute(text(BUILD))
        if fingerprints(db) != before:
            raise RuntimeError('Source tables changed')
        print('Mobility segments:', db.scalar(text('SELECT count(*) FROM mobility_demo_segments')))
elif sys.argv[1:] == ['serve']:
    import uvicorn
    uvicorn.run('backend.app.main:app', host='127.0.0.1', port=8000)
else:
    runpy.run_module('backend.handoff', run_name='__main__')
