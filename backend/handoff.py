"""Portable source-data exchange. No credentials or database recovery archives."""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import Date, DateTime, select, text
from backend.app.database import engine
from backend.app.models import Ship, ShipPosition, Event, News

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/handoff/current'
TABLES = [Ship.__table__, ShipPosition.__table__, Event.__table__, News.__table__]


def encoded(rows):
    return ''.join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True,
                              default=lambda v: v.isoformat()) + '\n' for row in rows).encode('utf-8')


def export_data():
    PACKAGE.mkdir(parents=True, exist_ok=True)
    manifest = {'format_version': 1, 'exported_at_utc': datetime.now(timezone.utc).isoformat(),
                'source': 'current database source tables; no credentials or full article content',
                'simulation_batch': 'sim_ais_demo/output_news_aligned', 'tables': {}}
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as db:
        with db.begin():
            db.execute(text('SET TRANSACTION READ ONLY'))
            for table in TABLES:
                rows = db.execute(select(table).order_by(table.c.id)).mappings().all()
                raw = encoded(rows)
                (PACKAGE / f'{table.name}.jsonl').write_bytes(raw)
                manifest['tables'][table.name] = {'count': len(rows), 'sha256': hashlib.sha256(raw).hexdigest()}
    (PACKAGE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v['count'] for k, v in manifest['tables'].items()}))


def load_package():
    manifest = json.loads((PACKAGE / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['format_version'] != 1 or set(manifest['tables']) != {t.name for t in TABLES}:
        raise ValueError('Unsupported package')
    result = {}
    for table in TABLES:
        raw = (PACKAGE / f'{table.name}.jsonl').read_bytes()
        expected = manifest['tables'][table.name]
        if hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError(f'Checksum mismatch: {table.name}')
        rows = [json.loads(line) for line in raw.decode('utf-8').splitlines()]
        if len(rows) != expected['count']:
            raise ValueError('Row count mismatch')
        for row in rows:
            if set(row) != set(table.columns.keys()):
                raise ValueError(f'Unexpected columns: {table.name}')
            for col in table.columns:
                if row[col.name] is not None and isinstance(col.type, (DateTime, Date)):
                    row[col.name] = (datetime if isinstance(col.type, DateTime) else date).fromisoformat(row[col.name])
        result[table.name] = rows
    return result


def verify(db, rows):
    for table in TABLES:
        actual = db.execute(select(table).order_by(table.c.id)).mappings().all()
        if encoded(actual) != encoded(rows[table.name]):
            raise ValueError(f'Database differs from package: {table.name}')
    if db.scalar(text('SELECT count(*) FROM ship_positions WHERE location IS NULL')):
        raise ValueError('Missing generated locations')
    print(json.dumps({t.name: len(rows[t.name]) for t in TABLES}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import', 'verify'])
    parser.add_argument('--database', help='Required exact target name for import')
    args = parser.parse_args()
    if args.action == 'export':
        export_data()
        return
    rows = load_package()
    with engine.begin() as db:
        if args.action == 'import':
            name = db.scalar(text('SELECT current_database()'))
            if not args.database or name != args.database:
                raise ValueError('Pass --database with the exact target database name')
            # Refuse even empty existing application tables: this is never an upgrade or replacement.
            if db.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('ships','ship_positions','events','news','mobility_demo_segments')")):
                raise ValueError('Target already contains application tables; import refused')
            db.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
            db.execute(text('CREATE EXTENSION IF NOT EXISTS mobilitydb CASCADE'))
            db.execute(text((ROOT / 'backend/sql/008_fresh_handoff_schema.sql').read_text(encoding='utf-8')))
            for table in TABLES:
                for offset in range(0, len(rows[table.name]), 500):
                    db.execute(table.insert(), rows[table.name][offset:offset + 500])
                db.execute(text("SELECT setval(pg_get_serial_sequence(:table, 'id'), COALESCE((SELECT max(id) FROM " + table.name + "), 1), EXISTS(SELECT 1 FROM " + table.name + "))"), {'table': table.name})
        verify(db, rows)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Driver exceptions may contain SQL parameters or connection details.
        print(f'Handoff failed ({type(exc).__name__}); verify target, empty database, package hashes and extensions.')
        raise SystemExit(1)
