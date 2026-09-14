"""Safe importer for a generated simulation batch.

Design rules
------------
* dry-run by default - nothing is written unless ``--apply`` is passed;
* everything runs inside a single transaction and rolls back on any error;
* the existing tables are never truncated, never deleted from and never overwritten;
* ``location`` is a generated column and is never written;
* duplicate protection:
    - a ship whose MMSI already exists in ``ships`` is not inserted again; with
      ``--link-existing`` its existing ``ships.id`` is reused and only the batch's
      positions that are missing from ``ship_positions`` are added;
    - positions whose ``(ship_id, recorded_at)`` already exist are skipped;
* the batch's temporary integer ship ids are mapped to the real auto-increment ids
  and the mapping is printed and written to a report file.

Usage (run from the project root, or pass absolute paths):

    # 1. inspect only - the default
    .\\backend\\.venv\\Scripts\\python.exe .\\sim_ais_demo\\tools\\import_to_db.py

    # 2. actually write the data
    .\\backend\\.venv\\Scripts\\python.exe .\\sim_ais_demo\\tools\\import_to_db.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))

import sqlalchemy  # noqa: E402
from sqlalchemy import text  # noqa: E402

SHIP_INSERT = text(
    """
    INSERT INTO ships (mmsi, name, ship_type, flag, imo, callsign, length_m, width_m)
    VALUES (:mmsi, :name, :ship_type, :flag, :imo, :callsign, :length_m, :width_m)
    RETURNING id
    """
)

POSITION_INSERT = text(
    """
    INSERT INTO ship_positions (
        ship_id, latitude, longitude, speed, course, heading, recorded_at,
        unix_time, nav_status, rot, draught_m, destination, ais_type, data_source
    ) VALUES (
        :ship_id, :latitude, :longitude, :speed, :course, :heading, :recorded_at,
        :unix_time, :nav_status, :rot, :draught_m, :destination, :ais_type, :data_source
    )
    """
)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="把模拟 AIS 批次安全导入数据库（默认只做 dry-run）")
    parser.add_argument("--outdir", default=str(ROOT / "output"))
    parser.add_argument("--apply", action="store_true", help="真正写入数据库；不加则只检查")
    parser.add_argument("--link-existing", action="store_true",
                        help="MMSI 已存在时复用现有 ships.id，只补缺失船位（默认遇到冲突即中止）")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    outdir = Path(args.outdir)
    ships_path = outdir / "ships.jsonl"
    positions_dir = outdir / "positions_by_date"
    if not ships_path.exists() or not positions_dir.exists():
        print(f"输出目录缺少 ships.jsonl 或 positions_by_date：{outdir}")
        return 2

    ships = load_jsonl(ships_path)
    position_files = sorted(positions_dir.glob("positions_*.jsonl"))
    positions = [row for path in position_files for row in load_jsonl(path)]

    result: dict = {
        "outdir": str(outdir),
        "mode": "apply" if args.apply else "dry-run",
        "ships_in_batch": len(ships),
        "positions_in_batch": len(positions),
        "position_files": [p.name for p in position_files],
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "planned_actions": {},
        "errors": [],
        "executed": False,
    }

    try:
        from backend.app.database import SessionLocal
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"无法导入数据库连接模块：{type(exc).__name__}: {exc}")
        write_report(args.report, outdir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    try:
        with SessionLocal() as session:
            existing_mmsi = {
                row[0]: row[1]
                for row in session.execute(text("SELECT mmsi, id FROM ships")).all()
            }
            colliding = [s for s in ships if s["mmsi"] in existing_mmsi]
            result["existing_ship_count"] = len(existing_mmsi)
            result["mmsi_collisions"] = len(colliding)
            result["mmsi_collision_sample"] = [s["mmsi"] for s in colliding[:10]]

            if colliding and not args.link_existing:
                result["errors"].append(
                    f"批次中有 {len(colliding)} 个 MMSI 已存在于 ships 表。"
                    "默认不覆盖、不重复插入。若确认要复用现有船舶并只补船位，请加 --link-existing。"
                )
                write_report(args.report, outdir, result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 3

            # existing positions for the ships involved, used for duplicate protection
            candidate_ids = [existing_mmsi[s["mmsi"]] for s in colliding] if colliding else []
            existing_positions: set[tuple[int, str]] = set()
            if candidate_ids:
                rows = session.execute(
                    text(
                        "SELECT ship_id, recorded_at FROM ship_positions "
                        "WHERE ship_id = ANY(:ids)"
                    ),
                    {"ids": candidate_ids},
                ).all()
                for ship_id, recorded_at in rows:
                    existing_positions.add((int(ship_id), recorded_at.isoformat()))

            result["existing_positions_for_linked_ships"] = len(existing_positions)

            new_ships = [s for s in ships if s["mmsi"] not in existing_mmsi]
            linked_ships = {s["temp_ship_id"]: existing_mmsi[s["mmsi"]] for s in colliding}
            positions_to_insert = 0
            for row in positions:
                if row["temp_ship_id"] in linked_ships:
                    key = (linked_ships[row["temp_ship_id"]], row["recorded_at"])
                    if key in existing_positions:
                        continue
                positions_to_insert += 1

            # read-only check: every column the import writes must really exist
            actual_columns = {}
            for table in ("ships", "ship_positions"):
                actual_columns[table] = {
                    row[0] for row in session.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = :table"
                        ),
                        {"table": table},
                    ).all()
                }
            ships_written = {"mmsi", "name", "ship_type", "flag", "imo", "callsign", "length_m", "width_m"}
            positions_written = {
                "ship_id", "latitude", "longitude", "speed", "course", "heading", "recorded_at",
                "unix_time", "nav_status", "rot", "draught_m", "destination", "ais_type", "data_source",
            }
            missing_ship_columns = sorted(ships_written - actual_columns["ships"])
            missing_position_columns = sorted(positions_written - actual_columns["ship_positions"])

            result["planned_actions"] = {
                "ships_to_insert": len(new_ships),
                "ships_linked_to_existing": len(linked_ships),
                "positions_to_insert": positions_to_insert,
                "positions_skipped_as_duplicate": len(positions) - positions_to_insert,
                "tables_touched": ["ships", "ship_positions"],
                "writes": [
                    "INSERT INTO ships (...)",
                    "INSERT INTO ship_positions (...)",
                ],
                "columns_to_write": {
                    "ships": sorted(ships_written),
                    "ship_positions": sorted(positions_written),
                },
                "missing_columns": {
                    "ships": missing_ship_columns,
                    "ship_positions": missing_position_columns,
                },
                "location_written": False,
                "never_done": [
                    "不清空任何表",
                    "不删除或覆盖已有船舶与船位",
                    "不写入 location（数据库生成列）",
                    "不修改 events 与 news",
                ],
            }
            if missing_ship_columns or missing_position_columns:
                result["errors"].append(
                    "数据库实际列与导入字段不一致："
                    f"ships 缺少 {missing_ship_columns}，ship_positions 缺少 {missing_position_columns}"
                )
                write_report(args.report, outdir, result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 4

            if not args.apply:
                result["note_zh"] = "当前为 dry-run，未写入任何数据。确认无误后加 --apply 执行。"
                write_report(args.report, outdir, result)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0

            temp_to_real: dict[int, int] = dict(linked_ships)
            # Earlier SELECTs already started the session transaction.
            # Use a savepoint for inserts, then commit that outer transaction.
            with session.begin_nested():
                for ship in new_ships:
                    real_id = session.execute(
                        SHIP_INSERT,
                        {
                            "mmsi": ship["mmsi"],
                            "name": ship["name"],
                            "ship_type": ship["ship_type"],
                            "flag": ship.get("flag"),
                            "imo": ship.get("imo"),
                            "callsign": ship.get("callsign"),
                            "length_m": ship.get("length_m"),
                            "width_m": ship.get("width_m"),
                        },
                    ).scalar_one()
                    temp_to_real[ship["temp_ship_id"]] = int(real_id)

                if set(temp_to_real) != {s["temp_ship_id"] for s in ships}:
                    raise RuntimeError("临时 ID 到实际自增 ID 的映射不完整，事务回滚")

                buffered = []
                inserted = 0
                for row in positions:
                    real_ship_id = temp_to_real[row["temp_ship_id"]]
                    if row["temp_ship_id"] in linked_ships:
                        if (real_ship_id, row["recorded_at"]) in existing_positions:
                            continue
                        existing_positions.add((real_ship_id, row["recorded_at"]))
                    buffered.append({**row, "ship_id": real_ship_id})
                    if len(buffered) >= args.batch_size:
                        session.execute(POSITION_INSERT, buffered)
                        inserted += len(buffered)
                        buffered = []
                if buffered:
                    session.execute(POSITION_INSERT, buffered)
                    inserted += len(buffered)

                result["inserted_positions"] = inserted
                result["inserted_ships"] = len(new_ships)

            session.commit()
            result["executed"] = True
            result["temp_ship_id_to_real_id"] = {str(k): v for k, v in sorted(temp_to_real.items())}

            with SessionLocal() as verify_session:
                result["post_import_counts"] = {
                    "ships": int(verify_session.execute(text("SELECT count(*) FROM ships")).scalar()),
                    "ship_positions": int(verify_session.execute(text("SELECT count(*) FROM ship_positions")).scalar()),
                    "batch_positions_present": int(
                        verify_session.execute(
                            text(
                                "SELECT count(*) FROM ship_positions "
                                "WHERE ship_id = ANY(:ids) AND data_source = 'simulation'"
                            ),
                            {"ids": list(temp_to_real.values())},
                        ).scalar()
                    ),
                }
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"{type(exc).__name__}: {exc}")
        result["rolled_back"] = True
        write_report(args.report, outdir, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    write_report(args.report, outdir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def write_report(report_path: str | None, outdir: Path, payload: dict) -> None:
    target = Path(report_path) if report_path else outdir / "import_report.json"
    payload["finished_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"无法写出导入报告：{exc}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
