"""issue #48 验收 #1 对账：业务服务 vs 受控分析快照（独立测试库）。

在同一数据库（默认 hormuz_sql_test）上重新调用确定性业务服务
（query_strait_passages 逐日 24h 窗、area_service.query_activity 全窗），
与 agent_data 快照表逐项比对：

- 通行证据：逐日窗口重建稳定键集合，与 v_passage_evidence 按 window_day 比对；
- 通行按日：v_passage_daily 的计数/独立船数比对；
- 区域访问：v_area_visit 的 visit_key 集合与观测秒/报位数比对；
- 区域按日：v_area_daily 全部数值列比对；
- 覆盖元数据：v_data_coverage 与底表重算比对；
- 固定样本探针：跨日、重复通行、边界访问、缺报/未知船型、A=0、
  部分覆盖首日（2026-02-24）；
- 反加性：sum(逐日独立船数) != 全窗去重独立船数（按日相加不能当全窗去重）。

任何不一致打印 FAIL 并以非零退出。

用法：
    python scripts/issue48_reconcile.py [--db-name hormuz_sql_test]
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts.build_agent_analysis_snapshots import (  # noqa: E402
    BATCH_ID_SQL, SEVEN_DAY_FIRST, SEVEN_DAY_LAST, SNAPSHOT_NAME, agent_config,
    area_params, area_service, batch_window, boundaries, build_coverage,
    connect, query_strait_passages,
)

UTC = timezone.utc

_failures: list[str] = []
_probes: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[reconcile] {mark} {label}" + (f" | {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def probe(label: str, detail: str) -> None:
    print(f"[reconcile] SAMPLE {label} | {detail}")
    _probes.append(label)


def as_utc(value) -> datetime:
    return value.astimezone(UTC) if value is not None else None


def dec(value) -> Decimal:
    return Decimal(str(value))


def service_passages(db: Session, window_start: datetime, window_end: datetime):
    """逐日 24h 判定窗并集，与构建脚本完全同参数。"""
    evidence: dict[date, dict[str, dict]] = {}
    daily: dict[tuple[date, str], dict] = {}
    day = window_start.date()
    last_day = (window_end - timedelta(microseconds=1)).date()
    while day <= last_day:
        closure = datetime.combine(day, time(0, 0), tzinfo=UTC)
        result = query_strait_passages(db, closure_at=closure, end_at=closure + timedelta(days=1))
        rows: dict[str, dict] = {}
        for item in result.evidence + result.uncertain_candidates:
            key = (f"{day.isoformat()}|{item.direction}"
                   f"|s{item.start_fix_id}|c{item.completion_fix_id}")
            rows[key] = {
                "ship_id": item.ship_id, "direction": item.direction,
                "observed_completion_at": as_utc(item.observed_completion_at),
                "uncertain": bool(item.uncertain),
            }
        evidence[day] = rows
        for direction in ("west_to_east", "east_to_west"):
            items = [i for i in result.evidence if i.direction == direction]
            candidates = [i for i in result.uncertain_candidates if i.direction == direction]
            daily[(day, direction)] = {
                "confirmed_passage_count": len(items),
                "confirmed_unique_ships": len({i.ship_id for i in items}),
                "uncertain_candidate_count": len(candidates),
            }
        day += timedelta(days=1)
    return evidence, daily


def snapshot_passages(db: Session):
    rows = db.execute(text(
        "SELECT window_day, passage_key, ship_id, direction, observed_completion_at, "
        "uncertain FROM agent_data.v_passage_evidence"
    )).mappings().all()
    evidence: dict[date, dict[str, dict]] = {}
    for row in rows:
        evidence.setdefault(row["window_day"], {})[row["passage_key"]] = {
            "ship_id": row["ship_id"], "direction": row["direction"],
            "observed_completion_at": as_utc(row["observed_completion_at"]),
            "uncertain": bool(row["uncertain"]),
        }
    daily_rows = db.execute(text(
        "SELECT day, direction, confirmed_passage_count, confirmed_unique_ships, "
        "uncertain_candidate_count FROM agent_data.v_passage_daily"
    )).mappings().all()
    daily = {
        (row["day"], row["direction"]): {
            "confirmed_passage_count": row["confirmed_passage_count"],
            "confirmed_unique_ships": row["confirmed_unique_ships"],
            "uncertain_candidate_count": row["uncertain_candidate_count"],
        }
        for row in daily_rows
    }
    return evidence, daily


def compare_passages(db: Session, window_start: datetime, window_end: datetime) -> None:
    service_e, service_d = service_passages(db, window_start, window_end)
    snap_e, snap_d = snapshot_passages(db)
    check("通行证据 window_day 覆盖一致", set(service_e) == set(snap_e),
          f"service={sorted(set(service_e))} snapshot={sorted(set(snap_e))}")
    mismatched_days = []
    for day in sorted(set(service_e) & set(snap_e)):
        if service_e[day] != snap_e[day]:
            missing = set(service_e[day]) - set(snap_e[day])
            extra = set(snap_e[day]) - set(service_e[day])
            diff = {k for k in service_e[day] if k in snap_e[day]
                    and service_e[day][k] != snap_e[day][k]}
            mismatched_days.append(f"{day}(-{len(missing)}/+{len(extra)}/≠{len(diff)})")
    check("通行证据逐行一致（稳定键/船/方向/完成时间/候选标记）",
          not mismatched_days, "; ".join(mismatched_days) or "全一致")
    check("通行按日汇总一致", service_d == snap_d,
          f"diff={ {k: (service_d.get(k), snap_d.get(k)) for k in set(service_d) ^ set(snap_d)} }"
          if service_d != snap_d else "全一致")


def compare_area(db: Session, window_start: datetime, window_end: datetime) -> None:
    bounds = boundaries.default_bounds()
    payload = area_service.query_activity(
        db, start=window_start, end=window_end, bounds=bounds, is_default=True,
        visit_limit=area_params.MAX_VISIT_ROWS,
    )
    service_visits = {v["visit_key"]: v for v in payload["visits"]}
    snap_visits = {
        row["visit_key"]: row
        for row in db.execute(text(
            "SELECT * FROM agent_data.v_area_visit"
        )).mappings().all()
    }
    check("区域访问 visit_key 集合一致",
          set(service_visits) == set(snap_visits),
          f"service={len(service_visits)} snapshot={len(snap_visits)} "
          f"only_service={len(set(service_visits) - set(snap_visits))} "
          f"only_snapshot={len(set(snap_visits) - set(service_visits))}")
    bad = []
    for key in set(service_visits) & set(snap_visits):
        svc, snap = service_visits[key], snap_visits[key]
        fields = {
            "ship_id": (svc["ship_id"], snap["ship_id"]),
            "status": (svc["status"], snap["status"]),
            "first_inside_at": (as_utc(svc["first_inside_at"]), as_utc(snap["first_inside_at"])),
            "last_inside_at": (as_utc(svc["last_inside_at"]), as_utc(snap["last_inside_at"])),
            "observed_seconds": (dec(svc["observed_seconds"]), dec(snap["observed_seconds"])),
            "window_seconds": (dec(svc["window_seconds"]), dec(snap["window_seconds"])),
            "fix_count": (svc["fix_count"], snap["fix_count"]),
            "segment_count": (svc["segment_count"], snap["segment_count"]),
            "flags": (",".join(svc["flags"]), snap["flags"]),
        }
        for name, (left, right) in fields.items():
            if left != right:
                bad.append(f"{key}.{name}: {left} != {right}")
    check("区域访问逐字段一致（时间/观测秒/报位段数/状态/标记）",
          not bad, "; ".join(bad[:5]) or f"{len(service_visits)} 条全一致")

    service_daily = {
        row["date"]: row for row in payload["daily"]
    }
    snap_daily = {
        row["day"].isoformat(): row
        for row in db.execute(text(
            "SELECT * FROM agent_data.v_area_daily"
        )).mappings().all()
    }
    check("区域按日日期的覆盖一致", set(service_daily) == set(snap_daily),
          f"service={sorted(set(service_daily))} snapshot={sorted(set(snap_daily))}")
    numeric = ("ships_observed", "observed_entry_count", "observed_exit_count",
               "visits_touching_day", "complete_visit_count",
               "truncated_visit_count", "interrupted_visit_count",
               "uncertain_visit_count")
    bad = []
    for day in sorted(set(service_daily) & set(snap_daily)):
        svc, snap = service_daily[day], snap_daily[day]
        if dec(svc["observed_ship_hours"]) != dec(snap["observed_ship_hours"]):
            bad.append(f"{day}.observed_ship_hours: {svc['observed_ship_hours']} != {snap['observed_ship_hours']}")
        for name in numeric:
            if svc[name] != snap[name]:
                bad.append(f"{day}.{name}: {svc[name]} != {snap[name]}")
    check("区域按日数值一致（独立船数/进出次数/船时/各状态访问数）",
          not bad, "; ".join(bad[:5]) or "全一致")


def compare_coverage(db: Session, window_start: datetime, window_end: datetime,
                     built_at: datetime) -> None:
    service_rows = {
        row["day"]: row for row in build_coverage(db, window_start, window_end, built_at)
    }
    snap_rows = {
        row["day"]: row
        for row in db.execute(text(
            "SELECT day, position_count, ship_count, first_fix_at, last_fix_at "
            "FROM agent_data.v_data_coverage"
        )).mappings().all()
    }
    check("覆盖元数据日期覆盖一致", set(service_rows) == set(snap_rows),
          f"service={sorted(set(service_rows))} snapshot={sorted(set(snap_rows))}")
    bad = []
    for day in sorted(set(service_rows) & set(snap_rows)):
        svc, snap = service_rows[day], snap_rows[day]
        for name in ("position_count", "ship_count"):
            if svc[name] != snap[name]:
                bad.append(f"{day}.{name}: {svc[name]} != {snap[name]}")
        if as_utc(svc["first_fix_at"]) != as_utc(snap["first_fix_at"]):
            bad.append(f"{day}.first_fix_at")
        if as_utc(svc["last_fix_at"]) != as_utc(snap["last_fix_at"]):
            bad.append(f"{day}.last_fix_at")
    check("覆盖元数据逐日一致（报位数/独立船数/首末报位）",
          not bad, "; ".join(bad[:5]) or "全一致")


def sample_probes(db: Session, window_start: datetime, window_end: datetime) -> None:
    """验收 #1 固定样本探针 + 「按日去重不可相加」反例。"""
    evidence = db.execute(text(
        "SELECT window_day, passage_key, ship_id, ship_name, ship_type, direction, "
        "observed_completion_at, uncertain, uncertain_reason "
        "FROM agent_data.v_passage_evidence ORDER BY window_day, passage_key"
    )).mappings().all()

    # 跨日：同一船在不同 window_day 出现
    by_ship: dict[int, set] = {}
    for row in evidence:
        by_ship.setdefault(row["ship_id"], set()).add(row["window_day"])
    cross = {ship: days for ship, days in by_ship.items() if len(days) > 1}
    check("样本-跨日：存在跨日多次判定船", bool(cross),
          f"{len(cross)} 艘，示例 {list(cross.items())[:2]}")

    # 重复通行：同一船同方向 ≥2 次确定通行
    confirmed = [r for r in evidence if not r["uncertain"]]
    by_ship_dir: dict[tuple, int] = {}
    for row in confirmed:
        by_ship_dir[(row["ship_id"], row["direction"])] = by_ship_dir.get((row["ship_id"], row["direction"]), 0) + 1
    repeats = {k: v for k, v in by_ship_dir.items() if v >= 2}
    check("样本-重复通行：存在同船同方向多次确定通行", bool(repeats),
          f"{len(repeats)} 组，示例 {list(repeats.items())[:2]}")

    # 边界访问：truncated 或 prior_state=inside（窗口边界截断）的访问
    boundary = db.execute(text(
        "SELECT count(*) FROM agent_data.v_area_visit "
        "WHERE status IN ('truncated_start', 'truncated_end') "
        "OR started_before_window"
    )).scalar_one()
    check("样本-边界访问：存在窗口边界截断/前置访问", boundary > 0,
          f"truncated/started_before_window={boundary} 条")

    # 缺报/未知船型：uncertain 候选 与 ship_type 为空/unknown/未知
    gap_candidates = db.execute(text(
        "SELECT count(*) FROM agent_data.v_passage_evidence "
        "WHERE uncertain AND uncertain_reason IN ('long_gap', 'jump')"
    )).scalar_one()
    unknown_type = db.execute(text(
        "SELECT count(*) FROM agent_data.v_passage_evidence "
        "WHERE ship_type IS NULL OR ship_type IN ('unknown', '未知', '')"
    )).scalar_one()
    check("样本-缺报：存在 long_gap/jump 候选", gap_candidates > 0,
          f"long_gap/jump={gap_candidates} 条")
    check("样本-未知船型：存在 NULL/unknown/未知 船型行", unknown_type > 0,
          f"NULL/unknown/未知 ship_type={unknown_type} 条")

    # A=0：按日表存在真实 0 值行（整个批次每个日×方向都有确定通行，
    # 零值体现在候选数等计数列）；另验证一个筛选组合返回 0 行而不是报错。
    zero_rows = db.execute(text(
        "SELECT day, direction, confirmed_passage_count, uncertain_candidate_count "
        "FROM agent_data.v_passage_daily "
        "WHERE confirmed_passage_count = 0 OR uncertain_candidate_count = 0 "
        "ORDER BY day, direction"
    )).mappings().all()
    check("样本-A=0：按日表存在真实 0 值行", bool(zero_rows),
          f"{len(zero_rows)} 行，示例 {zero_rows[:2]}")
    filtered_zero = db.execute(text(
        "SELECT count(*) FROM agent_data.v_passage_evidence "
        "WHERE window_day = :day AND direction = :dir AND ship_type = :st"
    ), {"day": date(2026, 3, 3), "dir": "west_to_east",
        "st": "不存在类型"}).scalar_one()
    check("样本-A=0：无匹配筛选返回 0 行（不报错、不截断）", filtered_zero == 0,
          f"count={filtered_zero}")

    # 部分覆盖首日：2026-02-24 报位存在但不足整天（首报位晚于日界）
    first_day = db.execute(text(
        "SELECT day, position_count, first_fix_at, last_fix_at "
        "FROM agent_data.v_data_coverage WHERE day = '2026-02-24'"
    )).mappings().one_or_none()
    if first_day is None:
        check("样本-部分覆盖：首日 2026-02-24 覆盖行存在", False, "无覆盖行")
    else:
        day_start = datetime(2026, 2, 24, tzinfo=UTC)
        partial = (as_utc(first_day["first_fix_at"]) > day_start
                   or as_utc(first_day["last_fix_at"]) < day_start + timedelta(days=1))
        check("样本-部分覆盖：首日 2026-02-24 为非整天覆盖", partial,
              f"positions={first_day['position_count']} "
              f"first={as_utc(first_day['first_fix_at'])} last={as_utc(first_day['last_fix_at'])}")

    # 反加性反例：sum(逐日独立船数) 与 全窗去重独立船数 不相等
    daily_sums = db.execute(text(
        "SELECT day, confirmed_unique_ships FROM agent_data.v_passage_daily "
        "WHERE direction = 'west_to_east'"
    )).mappings().all()
    summed = sum(row["confirmed_unique_ships"] for row in daily_sums)
    whole = len({row["ship_id"] for row in confirmed if row["direction"] == "west_to_east"})
    check("反加性：sum(逐日独立船数) ≠ 全窗去重独立船数（西→东）",
          summed != whole, f"sum={summed} whole-window-dedup={whole}")
    probe("按日去重不可相加",
          f"西→东逐日独立船数相加={summed}，全窗去重={whole}；"
          f"把逐日相加当全窗去重会高估 {summed - whole} 艘")

    # 通行证据整体规模（与交接记录基线 536=504+32 核对）
    total = len(evidence)
    unc = sum(1 for row in evidence if row["uncertain"])
    probe("通行证据规模", f"total={total} confirmed={total - unc} uncertain={unc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-name", default=os.environ.get("DB_NAME", "hormuz_sql_test"))
    args = parser.parse_args()

    engine, db = connect(args.db_name)
    try:
        window_start, window_end = batch_window(db)
        print(f"[reconcile] db={args.db_name} window {window_start} .. {window_end}")
        manifest = db.execute(text(
            "SELECT snapshot_name, catalog_version, window_start, window_end, built_at "
            "FROM agent_data.v_snapshot_manifest WHERE snapshot_name = :name"
        ), {"name": SNAPSHOT_NAME}).mappings().one_or_none()
        check("快照清单行存在", manifest is not None, f"manifest={dict(manifest) if manifest else None}")
        if manifest is None:
            raise SystemExit(1)
        if as_utc(manifest["window_start"]) != window_start:
            check("快照清单窗口与当前批次覆盖一致", False,
                  f"manifest={as_utc(manifest['window_start'])} batch={window_start}")

        compare_passages(db, window_start, window_end)
        compare_area(db, window_start, window_end)
        compare_coverage(db, window_start, window_end, datetime.now(UTC))
        sample_probes(db, window_start, window_end)

        print(f"[reconcile] 完成：{len(_probes)} 个样本探针，"
              f"{len(_failures)} 项不一致")
        if _failures:
            for label in _failures:
                print(f"[reconcile] FAILED {label}")
            raise SystemExit(1)
        print("[reconcile] ALL PASS")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
