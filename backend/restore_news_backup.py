"""Rehearse restoring an archive in a temporary schema; --apply restores public tables.

Usage: python -m backend.restore_news_backup data/db_backups/<timestamp>
The default rehearsal always rolls back and leaves current tables untouched.
"""
import argparse
import json
import hashlib
import re
from pathlib import Path
import subprocess
import uuid

from backend.app.database import engine
from backend.migrate_real_news import ROOT, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    folder = args.backup.resolve()
    require(folder.is_relative_to(ROOT / "data/db_backups"), "Backup must be inside project backup directory")
    archive = folder / "events_news.dump"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    require(hashlib.sha256(archive.read_bytes()).hexdigest() == manifest["backup_sha256"], "Backup checksum mismatch")
    require(set(manifest["old_counts"]) <= {"events", "news"}, "Unexpected tables")
    with archive.open("rb") as source:
        sql = subprocess.run(["docker", "exec", "-i", "mobilitydb", "pg_restore", "--no-owner", "--no-privileges", "-f", "-"],
                             stdin=source, capture_output=True, check=True).stdout
    if args.apply:
        schema = "public"
        prefix = b"BEGIN;\nSET LOCAL lock_timeout = '10s';\nDROP TABLE IF EXISTS public.news;\nDROP TABLE IF EXISTS public.events;\n"
    else:
        schema = "restore_check_" + uuid.uuid4().hex
        # Move only table/sequence references; PostGIS types/functions stay public.
        sql = re.sub(rb"public\.(events\w*|news\w*)\b", lambda m: schema.encode() + b"." + m[1], sql)
        prefix = f"BEGIN;\nCREATE SCHEMA {schema};\n".encode()
    checks = "\n"
    for table, count in manifest["old_counts"].items():
        checks += f"DO $$ BEGIN IF (SELECT count(*) FROM {schema}.{table}) <> {int(count)} THEN RAISE EXCEPTION 'Restore count mismatch'; END IF; END $$;\n"
    checks += "COMMIT;\n" if args.apply else "ROLLBACK;\n"
    url = engine.url
    require(url.host in {"127.0.0.1", "localhost"} and url.port == 25432, "Unexpected DB endpoint")
    subprocess.run(["docker", "exec", "-i", "mobilitydb", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-U", url.username, "-d", url.database],
                   input=prefix + sql + checks.encode(), check=True)
    print("Restore applied" if args.apply else "Restore rehearsal verified and rolled back", manifest["old_counts"])


if __name__ == "__main__":
    main()
