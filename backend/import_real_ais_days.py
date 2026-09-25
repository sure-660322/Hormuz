"""Import audited 2026-02-25..03-03 AIS files, one committed day at a time.

Run --target test first; use --target app only after an independent backup.
Each day's CSV is COPYed to a transaction-local table and fully accounted for.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.app.database import engine as application_engine
from backend.import_real_ais_pilot import (
    SOURCE, bootstrap, fingerprint, stage_csv, validate_stage,
)

TEST_DATABASE = "ais_import_seven_day_test"
FIRST_DAY = date(2026, 2, 25)
LAST_DAY = date(2026, 3, 3)


def ensure_test_database() -> None:
    with application_engine.connect() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": TEST_DATABASE})
    if not exists:
        with application_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {TEST_DATABASE}")


def audit_manifest(path: Path) -> dict[str, dict]:
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        item = json.loads(line)
        result[Path(item["file"]).name] = item
    return result


def import_day(raw, path: Path, expected: dict) -> dict:
    day = date.fromisoformat(path.stem)
    if not FIRST_DAY <= day <= LAST_DAY:
        raise ValueError(f"Unexpected source day: {day}")
    if path.name != Path(expected["file"]).name or path.stat().st_size != expected["bytes"]:
        raise ValueError(f"Audit manifest does not match {path}")
    digest = fingerprint(path)
    if digest != expected["sha256"]:
        raise ValueError(f"Source changed since audit: {path}")
    count_expected = expected["counts"]["rows"]
    if any(expected["counts"].get(k, 0) for k in
           ("wrong_columns", "bad_mmsi", "bad_coordinates", "outside_day", "bad_time", "time_mismatch")):
        raise ValueError(f"Audit has blocking errors: {path.name}")
    with raw.cursor() as cursor:
        previous = cursor.execute("SELECT id,source_file,source_sha256,file_size_bytes,expected_rows,inserted_rows FROM ais_import_batches WHERE source_day=%s", (day,)).fetchall()
        if previous:
            if len(previous) == 1 and previous[0][1:] == (path.name, digest, path.stat().st_size, count_expected, count_expected):
                existing = cursor.execute("""
                    SELECT count(*),count(DISTINCT source_row),min(source_row),max(source_row)
                    FROM ship_positions WHERE source_batch_id=%s
                """, (previous[0][0],)).fetchone()
                if existing == (count_expected, count_expected, 1, count_expected):
                    return {"day": day.isoformat(), "state": "already_imported", "positions": count_expected}
            raise RuntimeError(f"Source-day conflict for {day}; refusing to replace or skip rows")
        earlier = cursor.execute("SELECT count(*) FROM ais_import_batches WHERE source_day >= %s", (day,)).fetchone()[0]
        if earlier:
            raise RuntimeError("Days must be imported in order")
        before_ships = cursor.execute("SELECT count(*) FROM ships").fetchone()[0]
        before_positions = cursor.execute("SELECT count(*) FROM ship_positions").fetchone()[0]
    copied = stage_csv(raw, path)
    if copied != count_expected:
        raise ValueError(f"COPY count mismatch for {day}: {copied} vs {count_expected}")
    quality = validate_stage(raw, day)
    with raw.cursor() as cursor:
        time_bounds = cursor.execute("SELECT min(unix_time::bigint),max(unix_time::bigint),min(source_row),max(source_row),count(DISTINCT source_row) FROM ais_stage").fetchone()
        if time_bounds[2:] != (1, copied, copied):
            raise ValueError(f"Source row accounting failed: {time_bounds}")
        # Validated source-local days cannot overlap earlier files' UTC intervals.
        overlap = cursor.execute("""
            SELECT count(*) FROM ship_positions
            WHERE recorded_at >= (%s::timestamp AT TIME ZONE 'Asia/Shanghai')
              AND recorded_at < (%s::timestamp AT TIME ZONE 'Asia/Shanghai')
        """, (day.isoformat(), (day + timedelta(days=1)).isoformat())).fetchone()[0]
        if overlap:
            raise RuntimeError(f"Cross-file time overlap on {day}: {overlap} existing rows")
        batch_id = cursor.execute("""
            INSERT INTO ais_import_batches
              (source_file,source_sha256,source_day,data_source,file_size_bytes,expected_rows,inserted_rows)
            VALUES (%s,%s,%s,%s,%s,%s,0) RETURNING id
        """, (path.name, digest, day, SOURCE, path.stat().st_size, copied)).fetchone()[0]
        cursor.execute("""
            INSERT INTO ships (mmsi,name,ship_type,ship_type_cn_raw,imo,callsign,length_m,width_m,dwt_t)
            SELECT DISTINCT ON (mmsi) mmsi,ship_name,ship_type_cn,ship_type_cn,imo,callsign,
                length::double precision,width::double precision,dwt::double precision
            FROM ais_stage
            ORDER BY mmsi,unix_time::bigint DESC,source_row DESC
            ON CONFLICT (mmsi) DO UPDATE SET
                name=EXCLUDED.name, ship_type=EXCLUDED.ship_type,
                ship_type_cn_raw=EXCLUDED.ship_type_cn_raw, imo=EXCLUDED.imo,
                callsign=EXCLUDED.callsign, length_m=EXCLUDED.length_m,
                width_m=EXCLUDED.width_m, dwt_t=EXCLUDED.dwt_t
        """)
        cursor.execute("""
            INSERT INTO ship_positions
              (ship_id,latitude,longitude,speed,course,heading,recorded_at,unix_time,
               nav_status,rot,draught_m,destination,ais_type,data_source,eta_text,source_batch_id,source_row)
            SELECT s.id,a.latitude::double precision,a.longitude::double precision,
                a.speed::double precision,a.course::double precision,a.heading::double precision,
                to_timestamp(a.unix_time::bigint),a.unix_time::bigint,a.nav_status_cn,
                a.rot::double precision,a.draught::double precision,a.destination,a.ais_type,
                %s,a.eta,%s,a.source_row::integer
            FROM ais_stage a JOIN ships s ON s.mmsi=a.mmsi
        """, (SOURCE, batch_id))
        inserted = cursor.rowcount
        if inserted != copied:
            raise ValueError(f"Inserted {inserted}, expected {copied}")
        cursor.execute("UPDATE ais_import_batches SET inserted_rows=%s WHERE id=%s", (inserted, batch_id))
        reconciled = cursor.execute("""
            SELECT count(*),count(DISTINCT source_row),min(source_row),max(source_row),
                   count(*) FILTER (WHERE location IS NULL),min(recorded_at),max(recorded_at)
            FROM ship_positions WHERE source_batch_id=%s
        """, (batch_id,)).fetchone()
        totals = cursor.execute("SELECT (SELECT count(*) FROM ships),(SELECT count(*) FROM ship_positions)").fetchone()
        if reconciled[:5] != (copied, copied, 1, copied, 0) or totals[1] != before_positions + copied:
            raise ValueError(f"Database reconciliation failed: {reconciled}, {totals}")
    raw.commit()
    return {"day": day.isoformat(), "state": "committed", "batch_id": batch_id,
            "sha256": digest, "copied": copied, "positions": inserted,
            "vessels_in_file": quality["vessels"], "new_vessels": totals[0] - before_ships,
            "total_vessels": totals[0], "total_positions": totals[1],
            "first_utc": reconciled[5].isoformat(), "last_utc": reconciled[6].isoformat(),
            "ten_digit_rows": quality["ten_digit_rows"], "cross_file_overlap": overlap}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("test", "app"), required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("csv", nargs="+", type=Path)
    args = parser.parse_args()
    if application_engine.url.database != "aisdb":
        raise RuntimeError("Expected application DB_NAME=aisdb")
    if args.target == "test":
        ensure_test_database()
    database = TEST_DATABASE if args.target == "test" else "aisdb"
    manifest = audit_manifest(args.audit)
    days = sorted((date.fromisoformat(p.stem), p.resolve(strict=True)) for p in args.csv)
    if len(days) != len(set(day for day, _ in days)):
        raise ValueError("Duplicate source days")
    target_engine = create_engine(application_engine.url.set(database=database))
    raw = target_engine.raw_connection()
    try:
        if args.target == "test":
            bootstrap(raw)
        for day, path in days:
            started = time.monotonic()
            try:
                result = import_day(raw, path, manifest[path.name])
            except Exception:
                raw.rollback()
                raise
            result["elapsed_seconds"] = round(time.monotonic() - started, 1)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        with raw.cursor() as cursor:
            cursor.execute("ANALYZE ships")
            cursor.execute("ANALYZE ship_positions")
        raw.commit()
    finally:
        raw.close()
        target_engine.dispose()


if __name__ == "__main__":
    main()
