"""issue #48：构建/刷新 agent_data 分析快照（受控分析快照，catalog v3）。

快照行直接来自确定性业务服务的输出（query_strait_passages 逐日调用、
area_service.query_activity 全窗调用），不是 SQL 重写的判定结果。
整表重写在一个事务内完成，失败整体回滚、保留旧快照。

用法：
    python scripts/build_agent_analysis_snapshots.py [--db-name hormuz_sql_test]

源船位变更（重新导入、批次增删）后必须显式重跑本脚本（项目派生数据重建规则）。
"""
from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.agent import config as agent_config
from backend.app.services.agent.strait_passages import query_strait_passages
from backend.app.services.area_activity import boundaries, params as area_params
from backend.app.services.area_activity import service as area_service

UTC = timezone.utc
SNAPSHOT_NAME = "analysis_batch_v1"
CATALOG_VERSION = "3.0"
COVERAGE_SCOPE = (
    "判定走廊子集：nnu_ais、纬度 25.6–27.3°N、经度 55.6–57.3°E"
    "（覆盖通行判定带与默认区域上下文外扩）；不是全源覆盖"
)
CORRIDOR_LAT = (25.6, 27.3)
CORRIDOR_LON = (55.6, 57.3)
# 快照只覆盖七日霍尔木兹批次（批次 1–7，UTC+8 文件日 2026-02-25..03-03；
# 见 docs/database_setup.md）。batch 8（北极案例单船，含 3 月末返程走廊报位）排除。
SEVEN_DAY_FIRST = date(2026, 2, 25)
SEVEN_DAY_LAST = date(2026, 3, 3)
BATCH_ID_SQL = (
    "SELECT id FROM ais_import_batches "
    "WHERE source_day BETWEEN :batch_first AND :batch_last"
)

PASSAGE_TABLES = ["v_passage_evidence", "v_passage_daily"]
AREA_TABLES = ["v_area_visit", "v_area_daily"]
ALL_TABLES = PASSAGE_TABLES + AREA_TABLES + ["v_data_coverage", "v_snapshot_manifest"]


def connect(db_name: str):
    load_dotenv(PROJECT_ROOT / ".env")
    url = (
        f"postgresql+psycopg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{db_name}"
    )
    engine = create_engine(url)
    return engine, Session(bind=engine.connect())


def batch_window(db: Session) -> tuple[datetime, datetime]:
    """七日批次在判定走廊内的实际覆盖 [start, end)（取整天界，8 个 UTC 日）。"""
    row = db.execute(text(
        "SELECT min(recorded_at), max(recorded_at) FROM ship_positions "
        "WHERE data_source = :source AND source_batch_id IN (" + BATCH_ID_SQL + ") "
        "AND latitude BETWEEN :la AND :lb AND longitude BETWEEN :lo AND :hi"
    ), {"source": agent_config.SHIP_DATA_SOURCE, "batch_first": SEVEN_DAY_FIRST,
        "batch_last": SEVEN_DAY_LAST,
        "la": CORRIDOR_LAT[0], "lb": CORRIDOR_LAT[1],
        "lo": CORRIDOR_LON[0], "hi": CORRIDOR_LON[1]}).one()
    if row[0] is None:
        raise SystemExit("[build] 判定走廊内没有七日批次 nnu_ais 报位，无法构建快照")
    start = row[0].astimezone(UTC)
    if row[1].astimezone(UTC) >= start + timedelta(days=7):
        raise SystemExit(f"[build] 七日批次覆盖超过 7 天（max={row[1]}），请核对批次范围")
    # 通行判定按 UTC 自然日窗并集（[floor(start), ceil(end)））；
    # 区域活动窗口 = 精确 7 天 [start, start+7d)。
    return start, start + timedelta(days=7)


def build_passages(db: Session, window_start: datetime, window_end: datetime,
                   built_at: datetime) -> tuple[list[dict], list[dict]]:
    evidence: list[dict] = []
    daily: dict[tuple[date, str], dict] = {}
    day = window_start.date()
    last_day = (window_end - timedelta(microseconds=1)).date()
    while day <= last_day:
        closure = datetime.combine(day, time(0, 0), tzinfo=UTC)
        result = query_strait_passages(db, closure_at=closure, end_at=closure + timedelta(days=1))
        for item in result.evidence + result.uncertain_candidates:
            key = (f"{day.isoformat()}|{item.direction}"
                   f"|s{item.start_fix_id}|c{item.completion_fix_id}")
            evidence.append({
                "passage_key": key, "window_day": day,
                "window_start": closure, "window_end": closure + timedelta(days=1),
                "ship_id": item.ship_id, "ship_name": item.ship_name,
                "ship_type": item.ship_type, "direction": item.direction,
                "observed_completion_at": item.observed_completion_at,
                "start_observed_at": item.start_fix.recorded_at,
                "start_fix_id": item.start_fix_id,
                "completion_fix_id": item.completion_fix_id,
                "uncertain": item.uncertain,
                "uncertain_reason": item.uncertain_reason,
                "data_source": agent_config.SHIP_DATA_SOURCE,
                "schema_version": agent_config.SCHEMA_VERSION,
                "built_at": built_at,
            })
        confirmed = result.evidence
        for direction in ("west_to_east", "east_to_west"):
            items = [item for item in confirmed if item.direction == direction]
            bucket = daily.setdefault((day, direction), {
                "day": day, "direction": direction,
                "confirmed_passage_count": 0, "confirmed_unique_ships": 0,
                "uncertain_candidate_count": 0,
                "schema_version": agent_config.SCHEMA_VERSION, "built_at": built_at,
            })
            bucket["confirmed_passage_count"] += len(items)
            bucket["confirmed_unique_ships"] = len({item.ship_id for item in items})
        for item in result.uncertain_candidates:
            daily[(day, item.direction)]["uncertain_candidate_count"] += 1
        print(f"[build] passage window {day}: confirmed={len(confirmed)} "
              f"uncertain={len(result.uncertain_candidates)} status={result.status}")
        day += timedelta(days=1)
    return evidence, list(daily.values())


def build_area(db: Session, window_start: datetime, window_end: datetime,
               built_at: datetime) -> tuple[list[dict], list[dict], bool]:
    bounds = boundaries.default_bounds()
    payload = area_service.query_activity(
        db, start=window_start, end=window_end, bounds=bounds, is_default=True,
        visit_limit=area_params.MAX_VISIT_ROWS,
    )
    truncated = bool(payload["limits"]["detail_truncated"])
    visits = []
    for visit in payload["visits"]:
        visits.append({
            "area_id": area_params.DEFAULT_AREA_ID,
            "area_version": area_params.DEFAULT_AREA_VERSION,
            "window_start": window_start, "window_end": window_end,
            "visit_key": visit["visit_key"],
            "ship_id": visit["ship_id"],
            "ship_name": visit["ship_name"],
            "mmsi": visit["mmsi"],
            "ship_type": visit["ship_type"],
            "prior_state": visit["prior_state"],
            "status": visit["status"],
            "flags": ",".join(visit["flags"]),
            "first_inside_at": visit["first_inside_at"],
            "last_inside_at": visit["last_inside_at"],
            "observed_seconds": visit["observed_seconds"],
            "window_seconds": visit["window_seconds"],
            "unobserved_gap_seconds": visit["unobserved_gap_seconds"],
            "entry_observed": visit["entry"]["observed"],
            "entry_observed_at": visit["entry"]["observed_at"],
            "entry_in_window": visit["entry"]["in_window"],
            "exit_observed": visit["exit"]["observed"],
            "exit_observed_at": visit["exit"]["observed_at"],
            "exit_in_window": visit["exit"]["in_window"],
            "segment_count": visit["segment_count"],
            "fix_count": visit["fix_count"],
            "started_before_window": visit["started_before_window"],
            "algorithm_version": area_params.ALGORITHM_VERSION,
            "built_at": built_at,
        })
    daily = [{
        "area_id": area_params.DEFAULT_AREA_ID,
        "area_version": area_params.DEFAULT_AREA_VERSION,
        "day": datetime.strptime(row["date"], "%Y-%m-%d").date(),
        "window_start": window_start, "window_end": window_end,
        "ships_observed": row["ships_observed"],
        "observed_entry_count": row["observed_entry_count"],
        "observed_exit_count": row["observed_exit_count"],
        "observed_ship_hours": row["observed_ship_hours"],
        "visits_touching_day": row["visits_touching_day"],
        "complete_visit_count": row["complete_visit_count"],
        "truncated_visit_count": row["truncated_visit_count"],
        "interrupted_visit_count": row["interrupted_visit_count"],
        "uncertain_visit_count": row["uncertain_visit_count"],
        "algorithm_version": area_params.ALGORITHM_VERSION,
        "built_at": built_at,
    } for row in payload["daily"]]
    print(f"[build] area visits={len(visits)} daily_rows={len(daily)} "
          f"status={payload['status']} detail_truncated={truncated}")
    return visits, daily, truncated


def build_coverage(db: Session, window_start: datetime, window_end: datetime,
                   built_at: datetime) -> list[dict]:
    rows = db.execute(text(
        "SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day, "
        "count(*) AS position_count, count(DISTINCT ship_id) AS ship_count, "
        "min(recorded_at) AS first_fix_at, max(recorded_at) AS last_fix_at "
        "FROM ship_positions WHERE data_source = :source "
        "AND source_batch_id IN (" + BATCH_ID_SQL + ") "
        "AND recorded_at >= :start AND recorded_at < :end "
        "AND latitude BETWEEN :la AND :lb AND longitude BETWEEN :lo AND :hi "
        "GROUP BY 1 ORDER BY 1"
    ), {"source": agent_config.SHIP_DATA_SOURCE, "batch_first": SEVEN_DAY_FIRST,
        "batch_last": SEVEN_DAY_LAST, "start": window_start, "end": window_end,
        "la": CORRIDOR_LAT[0], "lb": CORRIDOR_LAT[1],
        "lo": CORRIDOR_LON[0], "hi": CORRIDOR_LON[1]}).mappings().all()
    return [{
        "day": row["day"], "data_source": agent_config.SHIP_DATA_SOURCE,
        "position_count": row["position_count"], "ship_count": row["ship_count"],
        "first_fix_at": row["first_fix_at"], "last_fix_at": row["last_fix_at"],
        "coverage_scope": COVERAGE_SCOPE, "built_at": built_at,
    } for row in rows]


def insert_rows(db: Session, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    db.execute(text(
        f"INSERT INTO agent_data.{table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + c for c in columns)})"
    ), rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "aisdb"))
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")

    engine, db = connect(args.db_name)
    try:
        with db.begin():
            window_start, window_end = batch_window(db)
            built_at = datetime.now(UTC)
            print(f"[build] window {window_start} .. {window_end} on {args.db_name}")
            for table in ALL_TABLES:
                db.execute(text(f"TRUNCATE agent_data.{table}"))
            evidence, passage_daily = build_passages(db, window_start, window_end, built_at)
            visits, area_daily, truncated = build_area(db, window_start, window_end, built_at)
            coverage = build_coverage(db, window_start, window_end, built_at)
            insert_rows(db, "v_passage_evidence", evidence)
            insert_rows(db, "v_passage_daily", passage_daily)
            insert_rows(db, "v_area_visit", visits)
            insert_rows(db, "v_area_daily", area_daily)
            insert_rows(db, "v_data_coverage", coverage)
            insert_rows(db, "v_snapshot_manifest", [{
                "snapshot_name": SNAPSHOT_NAME,
                "catalog_version": CATALOG_VERSION,
                "window_start": window_start, "window_end": window_end,
                "area_ids": area_params.DEFAULT_AREA_ID,
                "passage_schema_version": agent_config.SCHEMA_VERSION,
                "area_algorithm_version": area_params.ALGORITHM_VERSION,
                "source_scope": COVERAGE_SCOPE,
                "detail_truncated": truncated,
                "notes": "通行=逐日24h判定窗并集；区域=默认区域全窗(≤7d)；"
                         "源变更后须显式重跑构建脚本",
                "built_at": built_at,
            }])
        print(f"[build] committed: evidence={len(evidence)} visits={len(visits)} "
              f"coverage_days={len(coverage)}")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
