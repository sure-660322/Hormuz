"""Issue #48 验收 #3/#4 可核验证据：失败关闭实测 + EXPLAIN 资源预算（测试库）。

在独立测试库 hormuz_sql_test 上逐项给出可复现命令与结果：
1. catalog 漂移（真实删 manifest 行，经执行器核验 fail closed，随后恢复）；
2. 写入拒绝（agent_reader_login 实测 INSERT 被拒）；
3. 底表访问拒绝（public.ship_positions 无 SELECT 权限 + 策略拒绝）；
4. 缺必要过滤 / 超范围（策略拒绝，不触库）；
5. 超时 / 并发 / 取消（执行器既有机制实测）；
6. 代表查询 EXPLAIN（快照表小扫描，无全库无界扫描）。

只连 hormuz_sql_test；aisdb 全程只读且本脚本不连。
用法: python scripts/issue48_acceptance_evidence.py [--db-name hormuz_sql_test]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from backend.app.services.agent.query_analytics_executor import (  # noqa: E402
    CatalogMismatchError, ExecutorConfig, QueryAnalyticsExecutor,
    QueryExecutionError,
)
from backend.app.services.agent.query_analytics_policy import (  # noqa: E402
    QueryRefusedError, validate_query,
)

RESULTS: list[dict] = []


def record(case: str, ok: bool, command: str, result: str) -> None:
    RESULTS.append({"case": case, "ok": ok, "command": command, "result": result})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}\n  命令: {command}\n  结果: {result}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-name", default="hormuz_sql_test")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    host = os.environ["DB_HOST"]
    port = int(os.environ["DB_PORT"])
    admin_dsn = (f"host={host} port={port} dbname={args.db_name} "
                 f"user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']}")
    reader_dsn = (f"host={host} port={port} dbname={args.db_name} "
                  f"user=agent_reader_login password={os.environ['AGENT_DB_PASSWORD']} "
                  "options='-c timescaledb.disable_load=on'")
    config = ExecutorConfig(
        enabled=True, db_user="agent_reader_login",
        db_password=os.environ["AGENT_DB_PASSWORD"],
        db_host=host, db_port=port, db_name=args.db_name,
    )

    def run_executor(sql: str, params=None, call="call_ev") -> tuple[str, str]:
        executor = QueryAnalyticsExecutor(config)
        try:
            result = executor.execute(
                sql=sql, params=params or [], purpose="issue48 evidence",
                request_id="req_evidence", call_id=call,
            )
            return "ok", f"rows={result.returned_row_count}"
        except CatalogMismatchError as exc:
            return "catalog_mismatch", f"mismatches={list(exc.mismatches)}"
        except QueryExecutionError as exc:
            return exc.code, f"status={exc.status} query_executed={exc.query_executed}"
        finally:
            executor.dispose()

    # ---- 1. catalog 漂移：真实删除 manifest 行，执行器核验 fail closed，然后恢复
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        columns = [desc.name for desc in admin.execute(
            "SELECT * FROM agent_data.v_snapshot_manifest LIMIT 0").description]
        backup = [dict(zip(columns, row)) for row in admin.execute(
            "SELECT * FROM agent_data.v_snapshot_manifest").fetchall()]
        admin.execute("DELETE FROM agent_data.v_snapshot_manifest")
        code, detail = run_executor(
            "SELECT count(*) AS n FROM agent_data.v_passage_daily "
            "WHERE day >= :low AND day <= :high",
            [{"name": "low", "type": "date", "value": "2026-02-25"},
             {"name": "high", "type": "date", "value": "2026-03-03"}],
            call="call_drift",
        )
        placeholders = ", ".join(f"%({c})s" for c in columns)
        for row in backup:
            admin.execute(
                f"INSERT INTO agent_data.v_snapshot_manifest ({', '.join(columns)}) "
                f"VALUES ({placeholders})", row,
            )
        row = admin.execute(
            "SELECT count(*) FROM agent_data.v_snapshot_manifest").fetchone()[0]
    restored = row == 1
    record(
        "catalog 漂移：删 manifest 行后执行器 fail closed（已恢复）",
        code == "catalog_mismatch" and restored,
        "DELETE FROM agent_data.v_snapshot_manifest; "
        "executor.execute(SELECT count(*) ... v_passage_daily)",
        f"{detail}; 恢复后 manifest 行数={row}",
    )

    # ---- 2. 写入拒绝：reader login 实测 INSERT 被拒
    with psycopg.connect(reader_dsn) as reader:
        try:
            reader.execute(
                "INSERT INTO agent_data.v_passage_daily "
                "(day, direction, confirmed_passage_count, confirmed_unique_ships, "
                "uncertain_candidate_count, schema_version, built_at) "
                "VALUES ('2026-01-01', 'west_to_east', 1, 1, 0, 'evil', now())")
            reader.commit()
            record("写入拒绝", False, "INSERT INTO agent_data.v_passage_daily ...",
                   "意外写入成功")
        except psycopg.Error as exc:
            record(
                "写入拒绝", True,
                "psycopg 以 agent_reader_login INSERT agent_data.v_passage_daily",
                f"{type(exc).__name__} sqlstate={getattr(exc, 'sqlstate', '?')} "
                f"{str(exc).splitlines()[0][:120]}",
            )

    # ---- 3. 底表访问：策略拒绝 + DB 层无权限
    try:
        validate_query("SELECT count(*) FROM public.ship_positions")
        record("底表访问（策略层）", False, "validate_query(SELECT ... FROM public.ship_positions)",
               "意外通过")
    except QueryRefusedError as exc:
        record("底表访问（策略层）", True,
               "validate_query(\"SELECT count(*) FROM public.ship_positions\")",
               f"QueryRefusedError: {exc}")
    with psycopg.connect(reader_dsn) as reader:
        try:
            reader.execute("SELECT count(*) FROM public.ship_positions")
            record("底表访问（DB 层）", False, "reader SELECT public.ship_positions",
                   "意外读取成功")
        except psycopg.Error as exc:
            record("底表访问（DB 层）", True,
                   "psycopg 以 agent_reader_login SELECT public.ship_positions",
                   f"sqlstate={getattr(exc, 'sqlstate', '?')} {str(exc).splitlines()[0][:120]}")

    # ---- 4. 缺必要过滤 / 超范围（策略拒绝，不触库）
    refused_cases = [
        ("缺必要过滤（无边界）",
         "SELECT passage_key FROM agent_data.v_passage_evidence WHERE direction = :p",
         [{"name": "p", "type": "text", "value": "west_to_east"}]),
        ("超范围（30h 证据窗）",
         "SELECT passage_key FROM agent_data.v_passage_evidence "
         "WHERE observed_completion_at >= :low AND observed_completion_at < :high",
         [{"name": "low", "type": "timestamptz", "value": "2026-02-25T00:00:00Z"},
          {"name": "high", "type": "timestamptz", "value": "2026-02-26T06:00:00Z"}]),
        ("缺 area_id 必要过滤",
         "SELECT visit_key FROM agent_data.v_area_visit "
         "WHERE first_inside_at >= :low AND first_inside_at < :high",
         [{"name": "low", "type": "timestamptz", "value": "2026-02-25T00:00:00Z"},
          {"name": "high", "type": "timestamptz", "value": "2026-02-26T00:00:00Z"}]),
    ]
    for label, sql, params in refused_cases:
        try:
            validate_query(sql, params)
            record(label, False, f"validate_query({sql[:60]}...)", "意外通过")
        except QueryRefusedError as exc:
            record(label, True, f"validate_query({sql[:60]}...)", f"QueryRefusedError: {exc}")
    # 合法对照：同表带齐条件应通过
    validated = validate_query(
        "SELECT visit_key FROM agent_data.v_area_visit "
        "WHERE area_id = :a AND first_inside_at >= :low AND first_inside_at < :high",
        [{"name": "a", "type": "text", "value": "hormuz_core_v1"},
         {"name": "low", "type": "timestamptz", "value": "2026-02-25T00:00:00Z"},
         {"name": "high", "type": "timestamptz", "value": "2026-02-26T00:00:00Z"}])
    record("合法对照（齐过滤）", validated.catalog_version == "3.0",
           "validate_query(v_area_visit 带 area_id + 24h 双边界)",
           f"catalog_version={validated.catalog_version}")

    # ---- 5a. 进程并发上限：第二个并发执行 AGENT_QUERY_BUSY（不触库）
    first = QueryAnalyticsExecutor(config)
    occupied = threading.BoundedSemaphore(2)
    occupied.acquire()
    occupied.acquire()
    second = QueryAnalyticsExecutor(config, process_slots=occupied)
    try:
        try:
            second.execute(sql="SELECT count(*) AS n FROM agent_data.v_data_coverage "
                               "WHERE day >= :low AND day <= :high",
                           params=[{"name": "low", "type": "date", "value": "2026-02-24"},
                                   {"name": "high", "type": "date", "value": "2026-03-03"}],
                           purpose="busy evidence", request_id="req_busy",
                           call_id="call_busy")
            record("进程并发上限", False, "并发 2 占满后第三查询", "意外执行")
        except QueryExecutionError as exc:
            record("进程并发上限", exc.code == "AGENT_QUERY_BUSY",
                   "process_slots 占满后 execute(v_data_coverage)",
                   f"code={exc.code} status={exc.status} query_executed={exc.query_executed}")
    finally:
        occupied.release()
        occupied.release()
        first.dispose()
        second.dispose()

    # ---- 5b. 全局并发上限：占用全部 4 个咨询锁槽位，执行器应拒绝
    holders = [psycopg.connect(admin_dsn) for _ in range(4)]
    try:
        for slot, holder in enumerate(holders):
            assert holder.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)", (20_801, slot)
            ).fetchone()[0]
        code, detail = run_executor(
            "SELECT count(*) AS n FROM agent_data.v_data_coverage "
            "WHERE day >= :low AND day <= :high",
            [{"name": "low", "type": "date", "value": "2026-02-24"},
             {"name": "high", "type": "date", "value": "2026-03-03"}],
            call="call_global_busy",
        )
        record("全局并发上限", code == "AGENT_QUERY_BUSY",
               "4 个 pg_try_advisory_xact_lock(20801, slot) 占满后 execute",
               f"{code}: {detail}")
    finally:
        for holder in holders:
            holder.rollback()
            holder.close()

    # ---- 5c. 超时/取消：管理员持表锁制造阻塞，验证锁超时与预置取消均 fail
    #      closed 且无残留活动查询（与 test_query_analytics_executor 集成用例同机制）
    lock_holder = psycopg.connect(admin_dsn)
    executor = QueryAnalyticsExecutor(config)
    try:
        lock_holder.execute("LOCK TABLE agent_data.v_data_coverage IN ACCESS EXCLUSIVE MODE")
        try:
            executor.execute(
                sql="SELECT day, position_count FROM agent_data.v_data_coverage "
                    "WHERE day >= :low AND day <= :high ORDER BY day",
                params=[{"name": "low", "type": "date", "value": "2026-02-24"},
                        {"name": "high", "type": "date", "value": "2026-03-03"}],
                purpose="lock timeout evidence", request_id="req_lock",
                call_id="call_lock",
            )
            timeout_ok, timeout_detail = False, "意外执行成功"
        except QueryExecutionError as exc:
            timeout_ok = exc.code == "AGENT_QUERY_TIMEOUT"
            timeout_detail = f"code={exc.code} status={exc.status}"
        lock_holder.rollback()

        lock_holder.execute("LOCK TABLE agent_data.v_data_coverage IN ACCESS EXCLUSIVE MODE")
        cancel2 = threading.Event()
        cancel2.set()  # 预置取消：监控线程取消被锁阻塞的查询
        try:
            executor.execute(
                sql="SELECT day, position_count FROM agent_data.v_data_coverage "
                    "WHERE day >= :low AND day <= :high ORDER BY day",
                params=[{"name": "low", "type": "date", "value": "2026-02-24"},
                        {"name": "high", "type": "date", "value": "2026-03-03"}],
                purpose="cancel evidence", request_id="req_cancel",
                call_id="call_cancel", cancel_event=cancel2,
            )
            cancel_ok, cancel_detail = False, "意外执行成功"
        except QueryExecutionError as exc:
            cancel_ok = exc.code == "AGENT_QUERY_TIMEOUT"
            cancel_detail = f"code={exc.code} status={exc.status}"
        lock_holder.rollback()
    finally:
        lock_holder.close()
        executor.dispose()
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        active = admin.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE usename = 'agent_reader_login' AND state = 'active'"
        ).fetchone()[0]
    record("锁超时（1s lock_timeout）", timeout_ok,
           "LOCK TABLE v_data_coverage ACCESS EXCLUSIVE 后 execute（无取消）",
           timeout_detail)
    record("取消（cancel_event）", cancel_ok and active == 0,
           "持锁 + cancel_event.set() 后 execute；查 pg_stat_activity 残留",
           f"{cancel_detail}; 残留活动查询={active}")

    # ---- 6. EXPLAIN 资源预算（代表查询，快照表全为小扫描）
    explain_queries = {
        "v_passage_daily 7 天聚合":
            ("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) "
             "SELECT day, direction, confirmed_passage_count, confirmed_unique_ships "
             "FROM agent_data.v_passage_daily "
             "WHERE day >= DATE '2026-02-24' AND day <= DATE '2026-03-03'"),
        "v_area_visit 24h 窗口 top5":
            ("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) "
             "SELECT ship_name, observed_seconds FROM agent_data.v_area_visit "
             "WHERE area_id = 'hormuz_core_v1' "
             "AND first_inside_at >= TIMESTAMPTZ '2026-02-25 00:00:00+00' "
             "AND first_inside_at < TIMESTAMPTZ '2026-02-26 00:00:00+00' "
             "ORDER BY observed_seconds DESC LIMIT 5"),
        "v_data_coverage 全窗口":
            ("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) "
             "SELECT day, position_count, ship_count FROM agent_data.v_data_coverage "
             "WHERE day >= DATE '2026-02-24' AND day <= DATE '2026-03-03'"),
    }
    with psycopg.connect(reader_dsn, autocommit=True) as reader:
        for label, sql in explain_queries.items():
            plan = reader.execute(sql).fetchone()[0]
            summary = plan[0]["Plan"]

            def relations(node):
                found = []
                if node.get("Relation Name"):
                    found.append(node["Relation Name"])
                for child in node.get("Plans") or []:
                    found.extend(relations(child))
                return found

            rels = relations(summary)
            allowed = {"v_passage_evidence", "v_passage_daily", "v_area_visit",
                       "v_area_daily", "v_data_coverage"}
            elapsed_ms = plan[0].get("Execution Time")
            record(
                f"EXPLAIN {label}",
                all(rel in allowed for rel in rels) and elapsed_ms is not None and elapsed_ms < 500,
                sql[:80] + "...",
                f"根节点={summary['Node Type']} 扫描对象={sorted(set(rels))} "
                f"TotalCost={summary.get('Total Cost')} 执行毫秒={elapsed_ms} "
                f"共享块读={summary.get('Shared Read Blocks')}",
            )

    failed = [item for item in RESULTS if not item["ok"]]
    out = Path(__file__).resolve().parent.parent / "output" / "issue48"
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = out / f"{stamp}_acceptance_evidence.json"
    path.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {path}")
    print(f"完成：{len(RESULTS)} 项，失败 {len(failed)} 项")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
