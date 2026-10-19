"""Read-only application-table backup; no local .env or credentials are read.

The source container supplies its existing POSTGRES_USER/POSTGRES_DB. Extension
objects, cluster roles and passwords are deliberately outside this archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def psql(container: str, sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", container, "sh", "-c",
         'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        input=sql, text=True, encoding="utf-8", capture_output=True, timeout=600,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    dump = args.output / "application.dump"
    manifest_file = args.output / "database-manifest.json"
    if dump.exists() or manifest_file.exists():
        raise SystemExit("Output already exists; choose a new empty output directory.")

    snapshot_process = subprocess.Popen(
        ["docker", "exec", "-i", args.container, "sh", "-c",
         'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8",
    )
    try:
        snapshot_process.stdin.write(
            "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\nSELECT pg_export_snapshot();\n"
        )
        snapshot_process.stdin.flush()
        snapshot = snapshot_process.stdout.readline().strip()
        if not re.fullmatch(r"[0-9A-Fa-f-]+", snapshot):
            raise RuntimeError("Source snapshot could not be established.")
        prefix = ("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; "
                  f"SET TRANSACTION SNAPSHOT '{snapshot}'; ")
        tables = json.loads(psql(args.container, prefix + """
            SELECT json_agg(c.relname ORDER BY c.relname)
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
              AND NOT EXISTS (
                SELECT FROM pg_depend d WHERE d.classid='pg_class'::regclass
                AND d.objid=c.oid AND d.deptype='e'
              ); ROLLBACK;
        """))
        required = {"ships", "ship_positions", "events", "news", "ais_import_batches"}
        if not required.issubset(tables) or any(not re.fullmatch(r"[a-z_]+", t) for t in tables):
            raise RuntimeError("Unexpected application table inventory.")
        metadata = json.loads(psql(args.container, prefix + """
            SELECT json_build_object(
              'database',current_database(), 'server_version',current_setting('server_version'),
              'database_bytes',pg_database_size(current_database()),
              'extensions',(SELECT json_object_agg(extname,extversion) FROM pg_extension),
              'hypertables',(SELECT count(*) FROM _timescaledb_catalog.hypertable)
            ); ROLLBACK;
        """))
        if metadata["hypertables"]:
            raise RuntimeError("Source has Timescale hypertables; selective archive requires review.")
        counts_sql = " UNION ALL ".join(
            f"SELECT '{table}' AS name, count(*) AS rows FROM public.\"{table}\""
            for table in tables
        )
        counts = json.loads(psql(args.container, prefix +
            f"SELECT json_object_agg(name,rows) FROM ({counts_sql}) x; ROLLBACK;"))
        metadata.update({"tables": tables, "counts": counts,
                         "snapshot": snapshot,
                         "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                         "scope": "all non-extension ordinary public tables; no roles or extension internals"})
        command = 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl'
        command += f" --snapshot={snapshot}"
        command += "".join(f" --table=public.{table}" for table in tables)
        with dump.open("xb") as output:
            result = subprocess.run(["docker", "exec", args.container, "sh", "-c", command],
                                    stdout=output, stderr=subprocess.PIPE, timeout=1200)
        if result.returncode:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace"))
        metadata["dump_bytes"] = dump.stat().st_size
        with dump.open("rb") as stream:
            metadata["dump_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"output": str(args.output), "counts": counts,
                          "dump_bytes": metadata["dump_bytes"], "sha256": metadata["dump_sha256"]}))
    finally:
        if snapshot_process.poll() is None:
            snapshot_process.communicate("ROLLBACK;\n\\q\n", timeout=15)


if __name__ == "__main__":
    main()
