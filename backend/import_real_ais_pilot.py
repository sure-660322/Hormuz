"""Import one audited AIS CSV into an isolated PostgreSQL pilot database.

The application database is never a valid target. Source data are streamed to
a session-local staging table, then inserted into ships and ship_positions with
set-based SQL. No source row is silently skipped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

from backend.app.database import engine as application_engine


PILOT_DATABASE = "ais_import_pilot_20260225"
SOURCE = "nnu_ais"
EXPECTED_ROWS = 3_634_184
EXPECTED_HEADER = [
    "ShipName", "CallSign", "IMO", "MMSI", "ShipTypeCN", "ShipTypeEN",
    "NavStatusCN", "NavStatusEN", "Length", "Width", "Draught",
    "Heading", "Course", "Speed", "Lon", "Lat", "Rot", "Dest", "ETA",
    "Receivedtime（UTC+8）", "UnixTime", "Lon_d", "Lat_d", "AisType", "Dwt",
]
STAGE_COLUMNS = [
    "ship_name", "callsign", "imo", "mmsi", "ship_type_cn", "ship_type_en",
    "nav_status_cn", "nav_status_en", "length", "width", "draught",
    "heading", "course", "speed", "lon_dms", "lat_dms", "rot",
    "destination", "eta", "received_time", "unix_time", "longitude",
    "latitude", "ais_type", "dwt",
]


def fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_file(path: Path) -> tuple[date, str]:
    if not path.is_file():
        raise ValueError(f"CSV does not exist: {path}")
    try:
        source_day = date.fromisoformat(path.stem)
    except ValueError as exc:
        raise ValueError("CSV filename must be YYYY-MM-DD.csv") from exc
    if source_day != date(2026, 2, 25):
        raise ValueError("This pilot importer accepts only 2026-02-25.csv")
    with path.open("r", encoding="gb18030", newline="") as source:
        header = next(csv.reader(source))
    if header != EXPECTED_HEADER:
        raise ValueError("CSV header does not match the audited 25 columns")
    return source_day, fingerprint(path)


def create_pilot_database() -> None:
    if application_engine.url.database == PILOT_DATABASE:
        raise RuntimeError("Application database name collides with the pilot name")
    with application_engine.connect() as connection:
        exists = connection.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": PILOT_DATABASE})
    if exists:
        return
    # The target name is a constant, never constructed from CSV or CLI input.
    with application_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.exec_driver_sql(f"CREATE DATABASE {PILOT_DATABASE}")


def bootstrap(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ships (
                id bigserial PRIMARY KEY,
                mmsi varchar(9) NOT NULL UNIQUE,
                name varchar(100) NOT NULL,
                ship_type varchar(50) NOT NULL,
                flag varchar(50), imo varchar(20), callsign varchar(20),
                length_m double precision, width_m double precision
            );
            CREATE TABLE IF NOT EXISTS ship_positions (
                id bigserial PRIMARY KEY,
                ship_id bigint NOT NULL REFERENCES ships(id),
                latitude double precision NOT NULL,
                longitude double precision NOT NULL,
                speed double precision NOT NULL,
                course double precision NOT NULL,
                heading double precision,
                recorded_at timestamptz NOT NULL,
                unix_time bigint, nav_status varchar(50), rot double precision,
                draught_m double precision, destination varchar(255),
                ais_type varchar(50), data_source varchar(50) NOT NULL DEFAULT 'unknown',
                location geography(Point,4326) GENERATED ALWAYS AS (
                    ST_SetSRID(ST_MakePoint(longitude,latitude),4326)::geography
                ) STORED
            );
            CREATE INDEX IF NOT EXISTS idx_ship_positions_location
                ON ship_positions USING gist(location);
            CREATE INDEX IF NOT EXISTS idx_ship_positions_ship_recorded_at
                ON ship_positions(ship_id, recorded_at DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_ship_positions_recorded_at_brin
                ON ship_positions USING brin(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_ship_positions_data_source
                ON ship_positions(data_source);
        """)
        sql = (Path(__file__).parent / "sql" / "014_real_ais_import.sql").read_text(encoding="utf-8")
        cursor.execute(sql)
    connection.commit()


def stage_csv(connection, path: Path) -> int:
    with connection.cursor() as cursor:
        columns_sql = ", ".join(f"{column} text" for column in STAGE_COLUMNS)
        cursor.execute(
            "CREATE TEMP TABLE ais_stage (source_row bigint GENERATED ALWAYS AS IDENTITY, "
            + columns_sql + ") ON COMMIT DROP"
        )
        names = ", ".join(STAGE_COLUMNS)
        copy_sql = (
            f"COPY ais_stage ({names}) FROM STDIN "
            "WITH (FORMAT csv, HEADER true, ENCODING 'GB18030')"
        )
        with path.open("rb") as source, cursor.copy(copy_sql) as copy:
            while block := source.read(4 * 1024 * 1024):
                copy.write(block)
        count = cursor.execute("SELECT count(*) FROM ais_stage").fetchone()[0]
    return count


def validate_stage(connection, source_day: date) -> dict:
    with connection.cursor() as cursor:
        stats = cursor.execute("""
            SELECT
                count(*) FILTER (WHERE mmsi IS NULL OR unix_time IS NULL
                    OR longitude IS NULL OR latitude IS NULL
                    OR speed IS NULL OR course IS NULL) AS missing_required,
                count(*) FILTER (WHERE length(mmsi) > 10
                    OR length(ship_name) > 100 OR length(ship_type_cn) > 50
                    OR length(imo) > 20 OR length(callsign) > 20
                    OR length(nav_status_cn) > 50 OR length(destination) > 255
                    OR length(eta) > 32 OR length(ais_type) > 50) AS overlength,
                count(*) FILTER (WHERE mmsi !~ '^[0-9]{9,10}$') AS bad_identifier,
                count(*) FILTER (WHERE longitude::double precision NOT BETWEEN -180 AND 180
                    OR latitude::double precision NOT BETWEEN -90 AND 90) AS bad_coords,
                count(*) FILTER (WHERE to_timestamp(unix_time::bigint)
                    < (%s::timestamp AT TIME ZONE 'Asia/Shanghai')
                    OR to_timestamp(unix_time::bigint)
                    >= (%s::timestamp AT TIME ZONE 'Asia/Shanghai')) AS outside_day,
                count(*) FILTER (WHERE abs(extract(epoch from
                    (received_time::timestamp -
                     (to_timestamp(unix_time::bigint) AT TIME ZONE 'Asia/Shanghai')))) > 1)
                    AS time_mismatch,
                count(DISTINCT mmsi) AS vessels,
                count(*) FILTER (WHERE length(mmsi) = 10) AS ten_digit_rows
            FROM ais_stage
        """, (source_day.isoformat(), (source_day + timedelta(days=1)).isoformat())).fetchone()
    keys = ["missing_required", "overlength", "bad_identifier", "bad_coords",
            "outside_day", "time_mismatch", "vessels", "ten_digit_rows"]
    result = dict(zip(keys, stats))
    blockers = keys[:6]
    if any(result[key] for key in blockers):
        raise ValueError(f"Stage validation failed: {result}")
    return result


def insert_rows(connection, path: Path, source_day: date, sha256: str, stage_count: int) -> tuple[int, int]:
    with connection.cursor() as cursor:
        batch_id = cursor.execute("""
            INSERT INTO ais_import_batches
                (source_file,source_sha256,source_day,data_source,file_size_bytes,
                 expected_rows,inserted_rows)
            VALUES (%s,%s,%s,%s,%s,%s,0) RETURNING id
        """, (path.name, sha256, source_day, SOURCE, path.stat().st_size, stage_count)).fetchone()[0]
        cursor.execute("""
            INSERT INTO ships (mmsi,name,ship_type,ship_type_cn_raw,imo,callsign,
                               length_m,width_m,dwt_t)
            SELECT DISTINCT ON (mmsi)
                mmsi,ship_name,ship_type_cn,ship_type_cn,imo,callsign,
                length::double precision,width::double precision,dwt::double precision
            FROM ais_stage
            ORDER BY mmsi,unix_time::bigint DESC,source_row DESC
        """)
        ship_count = cursor.rowcount
        cursor.execute("""
            INSERT INTO ship_positions
                (ship_id,latitude,longitude,speed,course,heading,recorded_at,
                 unix_time,nav_status,rot,draught_m,destination,ais_type,data_source,
                 eta_text,source_batch_id,source_row)
            SELECT s.id,a.latitude::double precision,a.longitude::double precision,
                   a.speed::double precision,a.course::double precision,
                   a.heading::double precision,to_timestamp(a.unix_time::bigint),
                   a.unix_time::bigint,a.nav_status_cn,a.rot::double precision,
                   a.draught::double precision,a.destination,a.ais_type,%s,
                   a.eta,%s,a.source_row::integer
            FROM ais_stage a JOIN ships s ON s.mmsi=a.mmsi
        """, (SOURCE, batch_id))
        position_count = cursor.rowcount
        if position_count != stage_count:
            raise ValueError(f"Inserted {position_count}, expected {stage_count}")
        cursor.execute("UPDATE ais_import_batches SET inserted_rows=%s WHERE id=%s",
                       (position_count, batch_id))
    return ship_count, position_count


def verify(connection) -> dict:
    with connection.cursor() as cursor:
        row = cursor.execute("""
            SELECT (SELECT count(*) FROM ships),
                   (SELECT count(*) FROM ship_positions),
                   (SELECT count(*) FROM ship_positions WHERE location IS NULL),
                   (SELECT min(recorded_at) FROM ship_positions),
                   (SELECT max(recorded_at) FROM ship_positions),
                   pg_total_relation_size('ships'),
                   pg_total_relation_size('ship_positions')
        """).fetchone()
    return dict(zip(["ships", "positions", "null_locations", "first_utc", "last_utc",
                     "ships_bytes", "positions_bytes"],
                    [v.isoformat() if hasattr(v, "isoformat") else v for v in row]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    args = parser.parse_args()
    path = args.csv.resolve(strict=True)
    source_day, sha256 = validate_file(path)
    print(json.dumps({"phase": "source_checked", "file": path.name,
                      "bytes": path.stat().st_size, "sha256": sha256}), flush=True)
    started = time.monotonic()
    create_pilot_database()
    pilot_engine = create_engine(application_engine.url.set(database=PILOT_DATABASE))
    raw = pilot_engine.raw_connection()
    try:
        bootstrap(raw)
        with raw.cursor() as cursor:
            existing = cursor.execute("SELECT count(*) FROM ship_positions").fetchone()[0]
            if existing:
                raise RuntimeError("Pilot database already has positions; refusing a second import")
        count = stage_csv(raw, path)
        print(json.dumps({"phase": "copied_to_stage", "rows": count,
                          "elapsed_seconds": round(time.monotonic()-started, 1)}), flush=True)
        if count != EXPECTED_ROWS:
            raise ValueError(f"Expected {EXPECTED_ROWS} audited rows, got {count}")
        quality = validate_stage(raw, source_day)
        print(json.dumps({"phase": "validated", **quality}), flush=True)
        ships, positions = insert_rows(raw, path, source_day, sha256, count)
        raw.commit()
        with raw.cursor() as cursor:
            cursor.execute("ANALYZE ships")
            cursor.execute("ANALYZE ship_positions")
        raw.commit()
        print(json.dumps({"phase": "committed", "inserted_ships": ships,
                          "inserted_positions": positions,
                          "elapsed_seconds": round(time.monotonic()-started, 1),
                          "verification": verify(raw)}, default=str), flush=True)
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
        pilot_engine.dispose()


if __name__ == "__main__":
    main()
