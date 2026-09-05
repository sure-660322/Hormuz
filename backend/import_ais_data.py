import argparse
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

from backend.app.database import engine


EXPECTED_COLUMNS = (
    "mmsi",
    "timestamp",
    "latitude",
    "longitude",
    "speed",
    "course",
    "heading",
    "ship_name",
    "ship_type",
    "destination",
    "draught",
    "length",
    "width",
    "flag",
    "received_at",
)

SOURCE_NAME = "Hormuz AIS public dataset - positions.parquet"
SOURCE_URL = "https://huggingface.co/datasets/yasumorishima/hormuz-ais"
SOURCE_VERSION = "a31d2cbe82a5a60ed2a6af343b2c4d697ee10063"
COVERAGE_NOTE = (
    "历史 AIS 数据切片，主要覆盖迪拜/杰贝阿里；"
    "陆基接收存在盲区，不代表完整霍尔木兹海峡态势。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把原始 positions.parquet 导入独立 AIS 表，不修改模拟数据表。",
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument(
        "--confirm-import",
        action="store_true",
        help="确认执行数据库写入；未提供时只做文件预检",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def normalize_mmsi(value: Any) -> str:
    if value is None:
        raise ValueError("发现缺少 MMSI 的记录")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def normalize_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    if math.isnan(number):
        return None
    return number


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def ensure_migration_applied(connection) -> None:
    tables = connection.execute(
        text(
            """
            SELECT to_regclass('public.ais_datasets'),
                   to_regclass('public.ais_vessels'),
                   to_regclass('public.ais_positions')
            """
        )
    ).one()
    if any(table is None for table in tables):
        raise RuntimeError(
            "AIS 表尚未创建，请先执行 backend/sql/005_add_ais_history_tables.sql",
        )


def inspect_parquet(parquet_file) -> tuple[dict[str, dict[str, Any]], int]:
    actual_columns = tuple(parquet_file.schema_arrow.names)
    missing_columns = [
        column for column in EXPECTED_COLUMNS if column not in actual_columns
    ]
    if missing_columns:
        raise ValueError(f"Parquet 缺少字段：{', '.join(missing_columns)}")

    vessels: dict[str, dict[str, Any]] = {}
    record_count = 0
    metadata_fields = (
        "ship_name",
        "ship_type",
        "flag",
        "destination",
        "draught",
        "length",
        "width",
    )

    for batch in parquet_file.iter_batches(
        batch_size=10_000,
        columns=list(EXPECTED_COLUMNS),
    ):
        for row in batch.to_pylist():
            record_count += 1
            mmsi = normalize_mmsi(row["mmsi"])
            recorded_at = normalize_datetime(row["timestamp"])
            if recorded_at is None:
                raise ValueError(f"第 {record_count} 行缺少 timestamp")

            state = vessels.setdefault(
                mmsi,
                {
                    "mmsi": mmsi,
                    "first_seen": recorded_at,
                    "last_seen": recorded_at,
                    "_field_times": {},
                },
            )
            state["first_seen"] = min(state["first_seen"], recorded_at)
            state["last_seen"] = max(state["last_seen"], recorded_at)

            for field in metadata_fields:
                value = row[field]
                if value is None or value == "":
                    continue
                previous_time = state["_field_times"].get(field)
                if previous_time is None or recorded_at >= previous_time:
                    state[field] = value
                    state["_field_times"][field] = recorded_at

    return vessels, record_count


def vessel_insert_rows(vessels: dict[str, dict[str, Any]], dataset_id: int):
    rows = []
    for state in vessels.values():
        rows.append(
            {
                "dataset_id": dataset_id,
                "mmsi": state["mmsi"],
                "name": normalize_text(state.get("ship_name")),
                "ship_type": normalize_number(state.get("ship_type")),
                "flag": normalize_text(state.get("flag")),
                "destination": normalize_text(state.get("destination")),
                "draught": normalize_number(state.get("draught")),
                "length": normalize_number(state.get("length")),
                "width": normalize_number(state.get("width")),
                "first_seen": state["first_seen"],
                "last_seen": state["last_seen"],
            }
        )
    return rows


def import_positions(
    connection,
    parquet_file,
    dataset_id: int,
    vessel_ids: dict[str, int],
) -> int:
    raw_connection = connection.connection.driver_connection
    row_number = 0
    copy_sql = """
        COPY ais_positions (
            dataset_id, vessel_id, source_row_number, mmsi,
            recorded_at, latitude, longitude, speed, course, heading,
            ship_name, ship_type, destination, draught, length, width,
            flag, received_at
        ) FROM STDIN
    """

    with raw_connection.cursor().copy(copy_sql) as copy:
        for batch in parquet_file.iter_batches(
            batch_size=10_000,
            columns=list(EXPECTED_COLUMNS),
        ):
            for row in batch.to_pylist():
                row_number += 1
                mmsi = normalize_mmsi(row["mmsi"])
                recorded_at = normalize_datetime(row["timestamp"])
                latitude = normalize_number(row["latitude"])
                longitude = normalize_number(row["longitude"])
                if recorded_at is None or latitude is None or longitude is None:
                    raise ValueError(
                        f"第 {row_number} 行缺少时间或经纬度，导入已回滚",
                    )

                copy.write_row(
                    (
                        dataset_id,
                        vessel_ids[mmsi],
                        row_number,
                        mmsi,
                        recorded_at,
                        latitude,
                        longitude,
                        normalize_number(row["speed"]),
                        normalize_number(row["course"]),
                        normalize_number(row["heading"]),
                        normalize_text(row["ship_name"]),
                        normalize_number(row["ship_type"]),
                        normalize_text(row["destination"]),
                        normalize_number(row["draught"]),
                        normalize_number(row["length"]),
                        normalize_number(row["width"]),
                        normalize_text(row["flag"]),
                        normalize_datetime(row["received_at"]),
                    )
                )

    return row_number


def main() -> None:
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "缺少 pyarrow，请先执行 python -m pip install -r backend/requirements.txt",
        ) from exc

    args = parse_args()
    source = args.source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"未找到数据文件：{source}")

    source_sha256 = sha256_file(source)
    parquet_file = pq.ParquetFile(source)
    vessels, inspected_count = inspect_parquet(parquet_file)
    start_at = min(state["first_seen"] for state in vessels.values())
    end_at = max(state["last_seen"] for state in vessels.values())

    print(f"文件：{source}")
    print(f"SHA-256：{source_sha256}")
    print(f"预检记录数：{inspected_count}")
    print(f"预检船舶数：{len(vessels)}")
    print(f"时间范围（UTC）：{start_at.isoformat()} 至 {end_at.isoformat()}")

    if not args.confirm_import:
        print("仅完成预检；添加 --confirm-import 才会写入数据库。")
        return

    with engine.begin() as connection:
        ensure_migration_applied(connection)
        existing = connection.execute(
            text(
                """
                SELECT id, record_count, vessel_count
                FROM ais_datasets
                WHERE source_sha256 = :source_sha256
                """
            ),
            {"source_sha256": source_sha256},
        ).mappings().first()
        if existing is not None:
            print(
                "该 SHA-256 已导入，未重复写入："
                f"dataset_id={existing['id']}，"
                f"{existing['record_count']} 条位置，"
                f"{existing['vessel_count']} 艘船。"
            )
            return

        dataset_id = connection.execute(
            text(
                """
                INSERT INTO ais_datasets (
                    name, source_url, source_version, source_sha256,
                    record_count, vessel_count, start_at, end_at, coverage_note
                ) VALUES (
                    :name, :source_url, :source_version, :source_sha256,
                    0, 0, :start_at, :end_at, :coverage_note
                )
                RETURNING id
                """
            ),
            {
                "name": SOURCE_NAME,
                "source_url": SOURCE_URL,
                "source_version": SOURCE_VERSION,
                "source_sha256": source_sha256,
                "start_at": start_at,
                "end_at": end_at,
                "coverage_note": COVERAGE_NOTE,
            },
        ).scalar_one()

        connection.execute(
            text(
                """
                INSERT INTO ais_vessels (
                    dataset_id, mmsi, name, ship_type, flag, destination,
                    draught, length, width, first_seen, last_seen
                ) VALUES (
                    :dataset_id, :mmsi, :name, :ship_type, :flag, :destination,
                    :draught, :length, :width, :first_seen, :last_seen
                )
                """
            ),
            vessel_insert_rows(vessels, dataset_id),
        )
        vessel_ids = {
            row["mmsi"]: row["id"]
            for row in connection.execute(
                text(
                    """
                    SELECT id, mmsi
                    FROM ais_vessels
                    WHERE dataset_id = :dataset_id
                    """
                ),
                {"dataset_id": dataset_id},
            ).mappings()
        }

        imported_count = import_positions(
            connection,
            parquet_file,
            dataset_id,
            vessel_ids,
        )
        if imported_count != inspected_count:
            raise RuntimeError(
                f"预检 {inspected_count} 条，但实际写入 {imported_count} 条",
            )

        connection.execute(
            text(
                """
                UPDATE ais_datasets
                SET record_count = :record_count,
                    vessel_count = :vessel_count
                WHERE id = :dataset_id
                """
            ),
            {
                "record_count": imported_count,
                "vessel_count": len(vessels),
                "dataset_id": dataset_id,
            },
        )

    print(
        f"导入完成：dataset_id={dataset_id}，"
        f"{imported_count} 条原始位置，{len(vessels)} 艘船。"
    )
    print("模拟表 ships、ship_positions、events 未修改。")


if __name__ == "__main__":
    main()
