"""区域船舶活动与进出分析：真实库只读验证与性能基线（issue #41 第一阶段）。

只读保证：全过程监听 SQLAlchemy 的 before_cursor_execute，任何非 SELECT/WITH/EXPLAIN
语句都会让脚本失败；并在前后记录表行数与 pg_stat_user_tables 写入计数。
证据写入 docs/area_activity_backend_verification.json。

运行（仓库根目录，Windows PowerShell 7）：
    & .\\backend\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify_area_activity_backend.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from sqlalchemy import URL, create_engine, event, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.app.services.area_activity import params, service  # noqa: E402
from backend.app.services.area_activity.boundaries import AreaBounds, default_bounds  # noqa: E402

UTC = timezone.utc
OUTPUT = PROJECT_ROOT / "docs" / "area_activity_backend_verification.json"
READ_ONLY_PREFIXES = ("select", "with", "explain")
SOURCE_TABLES = ("ships", "ship_positions", "ais_import_batches")


def build_engine():
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url), {"host": url.host, "port": url.port, "database": url.database}


def table_counts(db: Session) -> dict:
    counts = {}
    for table in SOURCE_TABLES:
        counts[table] = db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
    return counts


def write_counters(db: Session) -> dict:
    rows = db.execute(text("""
        SELECT relname, n_tup_ins, n_tup_upd, n_tup_del
        FROM pg_stat_user_tables WHERE relname = ANY(:names)
    """), {"names": list(SOURCE_TABLES)}).mappings().all()
    return {row["relname"]: {
        "ins": row["n_tup_ins"], "upd": row["n_tup_upd"], "del": row["n_tup_del"],
    } for row in rows}


def timed(fn):
    start = time.perf_counter()
    payload = fn()
    return payload, round((time.perf_counter() - start) * 1000, 1)


def summarize(payload: dict) -> dict:
    summary = payload.get("summary") or {}
    limits = payload.get("limits") or {}
    return {
        "status": payload.get("status"),
        "ships_observed": summary.get("ships_observed", summary.get("in_area_count")),
        "observed_entry_count": summary.get("observed_entry_count"),
        "observed_exit_count": summary.get("observed_exit_count"),
        "observed_ship_hours": summary.get("observed_ship_hours"),
        "visit_count": summary.get("visit_count"),
        "returned_visit_count": limits.get("returned_visit_count"),
        "detail_truncated": limits.get("detail_truncated"),
        "scanned_fix_count": limits.get("scanned_fix_count"),
        "region_fix_count": (payload.get("coverage") or {}).get("region_fix_count"),
    }


def main() -> int:
    engine, target = build_engine()
    executed: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        executed.append(statement.strip().split()[0].lower())

    event.listen(engine, "before_cursor_execute", capture)
    captured_sql: list[tuple[str, object]] = []

    def remember(conn, cursor, statement, parameters, context, executemany):
        if "WITH scoped AS MATERIALIZED" in statement:
            captured_sql.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", remember)

    evidence: dict = {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "target": target,
        "note": "本机在同一 PostgreSQL 实例上运行；未做 DROP CACHES，run1/run2 均为已预热缓存",
        "algorithm": params.algorithm_descriptor(),
        "default_area": service.default_area_payload()["area"],
    }
    runs: dict = {}
    with Session(engine) as db:
        before_counts = table_counts(db)
        before_writes = write_counters(db)
        evidence["source_before"] = {"counts": before_counts, "write_counters": before_writes}

        bounds = default_bounds()
        custom = AreaBounds(south=26.0, west=56.0, north=26.8, east=56.9)
        windows = {
            "activity_1h_default_area": (
                datetime(2026, 2, 28, 10, 0, tzinfo=UTC),
                datetime(2026, 2, 28, 11, 0, tzinfo=UTC),
            ),
            "activity_1d_default_area": (
                datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
                datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            ),
            "activity_7d_default_area": (
                datetime(2026, 2, 25, 0, 0, tzinfo=UTC),
                datetime(2026, 3, 4, 0, 0, tzinfo=UTC),
            ),
        }
        for label, (start, end) in windows.items():
            first, ms_first = timed(lambda: service.query_activity(
                db, start=start, end=end, bounds=bounds, is_default=True))
            second, ms_second = timed(lambda: service.query_activity(
                db, start=start, end=end, bounds=bounds, is_default=True))
            runs[label] = {
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "run1_ms": ms_first, "run2_ms": ms_second,
                "summary": summarize(first),
                "limits": first.get("limits"),
                "coverage": first.get("coverage"),
                "daily_rows": len(first.get("daily") or []),
                "same_summary_between_runs": first["summary"] == second["summary"],
            }

        payload, ms = timed(lambda: service.query_activity(
            db, start=windows["activity_1d_default_area"][0],
            end=windows["activity_1d_default_area"][1],
            bounds=bounds, is_default=True, ship_type_values=["油轮"],
        ))
        runs["activity_1d_oil_tanker_filter"] = {
            "run1_ms": ms, "summary": summarize(payload),
            "filters": payload["query"]["filters"],
        }

        payload, ms = timed(lambda: service.query_activity(
            db, start=windows["activity_1d_default_area"][0],
            end=windows["activity_1d_default_area"][1],
            bounds=custom, is_default=False,
        ))
        runs["activity_1d_custom_area"] = {
            "run1_ms": ms, "summary": summarize(payload),
            "area": {"area_id": payload["area"]["area_id"], "bounds": payload["area"]["bounds"]},
        }

        payload, ms = timed(lambda: service.query_snapshot(
            db, at=datetime(2026, 2, 28, 12, 0, tzinfo=UTC), bounds=bounds, is_default=True))
        runs["snapshot_default_area"] = {"run1_ms": ms, "summary": payload["summary"]}

        payload, ms = timed(lambda: service.compare_activity(
            db,
            start_a=datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
            end_a=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            start_b=datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
            end_b=datetime(2026, 3, 3, 0, 0, tzinfo=UTC),
            bounds=bounds, is_default=True,
        ))
        runs["compare_1d_vs_2d_default_area"] = {
            "run1_ms": ms,
            "status": payload["status"],
            "comparability": payload["comparability"],
            "metrics": payload["metrics"],
        }

        evidence["runs"] = runs

        if captured_sql:
            statement, parameters = captured_sql[-1]
            # 捕获到的语句已是驱动参数风格（%(name)s），直接用 DBAPI 执行 EXPLAIN。
            raw_connection = db.connection().connection.driver_connection
            with raw_connection.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                )
                plan_rows = cursor.fetchone()[0]
            plan = plan_rows[0]
            evidence["plan_activity_1d"] = {
                "planning_time_ms": plan.get("Planning Time"),
                "execution_time_ms": plan.get("Execution Time"),
                "plan": plan.get("Plan"),
            }

        after_counts = table_counts(db)
        after_writes = write_counters(db)
        evidence["source_after"] = {"counts": after_counts, "write_counters": after_writes}

    evidence["read_only"] = {
        "counts_unchanged": evidence["source_before"]["counts"] == evidence["source_after"]["counts"],
        "write_counters_unchanged": evidence["source_before"]["write_counters"] == evidence["source_after"]["write_counters"],
        "statement_prefixes": sorted(set(executed)),
        "non_read_only_statements": [
            prefix for prefix in set(executed) if not prefix.startswith(READ_ONLY_PREFIXES)
        ],
    }
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"evidence -> {OUTPUT}")
    print(json.dumps({key: {"run1_ms": value.get("run1_ms"), "run2_ms": value.get("run2_ms"),
                            "summary": value.get("summary") or value.get("status")}
                      for key, value in evidence["runs"].items()}, ensure_ascii=False, indent=2))
    print("read_only:", evidence["read_only"])
    if evidence["read_only"]["non_read_only_statements"]:
        print("存在非只读语句，验证失败")
        return 1
    if not evidence["read_only"]["counts_unchanged"]:
        print("源表行数发生变化，验证失败")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
