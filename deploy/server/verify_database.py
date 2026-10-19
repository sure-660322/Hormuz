"""Verify the restored database through the application's read-only account."""
import json
from pathlib import Path

from sqlalchemy import text
from backend.app.database import engine

manifest = json.loads(Path("/release/database-manifest.json").read_text(encoding="utf-8"))
with engine.connect() as connection:
    assert connection.execute(text("SHOW default_transaction_read_only")).scalar() == "on"
    for table, expected in manifest["counts"].items():
        assert table.isidentifier()
        actual = connection.execute(text(f'SELECT count(*) FROM public."{table}"')).scalar()
        if actual != expected:
            raise RuntimeError(f"{table}: expected {expected}, got {actual}")
        print(f"PASS {table}: {actual}")
    invalid_indexes = connection.execute(text("""
        SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT i.indisvalid
    """)).scalars().all()
    assert not invalid_indexes, invalid_indexes
    invalid_constraints = connection.execute(text("""
        SELECT conname FROM pg_constraint
        WHERE connamespace='public'::regnamespace AND NOT convalidated
    """)).scalars().all()
    assert not invalid_constraints, invalid_constraints
    generated = connection.execute(text("""
        SELECT attgenerated FROM pg_attribute
        WHERE attrelid='public.ship_positions'::regclass AND attname='location'
    """)).scalar()
    assert generated == "s", f"location must remain stored generated, got {generated!r}"
print("PASS counts, valid indexes/constraints, generated geography, read-only application account")
