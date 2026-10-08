"""区域船舶活动独立复算（issue #41 第二/三阶段验收，task-4 验证项 2）。

原则：
- 只读真实库（会话设为 READ ONLY，并监听 SQL 前缀，出现非只读语句直接失败）。
- **不 import 任何 backend.app.* 模块**：连接串自己从 .env 读取（只输出 host/port/db 名，不输出账号密码），
  SQL 与算法口径只依据 docs/area_activity.md（第一阶段定版契约）重写。
- 期望值全部由本脚本朴素实现算出，绝不引用后端函数结果。

运行（工作树根目录）：
    & .\\backend\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify_area_activity_independent.py
输出：
    output/acceptance/independent_recompute.json
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 工作树根
OUT = ROOT / "output/acceptance/independent_recompute.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

from dotenv import load_dotenv  # noqa: E402  (只用于读取连接配置)

load_dotenv(ROOT / ".env")

from sqlalchemy import URL, create_engine, event, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

UTC = timezone.utc
ALLOWED_PREFIXES = ("select", "with", "explain", "set", "show", "reset")

# ---------------------------------------------------------------- 契约参数（docs/area_activity.md §3）
P = {
    "freshness_seconds": 3600.0,
    "gap_seconds": 1800.0,
    "jump_speed_kn": 30.0,
    "jump_min_distance_km": 1.0,
    "state_lookback_seconds": 21600.0,
    "state_lookahead_seconds": 21600.0,
    "context_margin_deg": 0.05,
    "excursion_probe_seconds": 480.0,
    "source": "nnu_ais",
    "earth_radius_km": 6371.0088,
}
DEFAULT_AREA = {"area_id": "hormuz_core_v1", "south": 25.8, "west": 55.8, "north": 27.1, "east": 57.1}

SHIP_TYPE_MISSING = "__missing__"
SHIP_TYPE_UNKNOWN = "__unknown__"


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- 连接与只读守卫
def build_engine():
    url = URL.create(
        drivername="postgresql+psycopg",
        username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )
    engine = create_engine(url)
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _guard(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        statements.append(statement.strip().split()[0].lower() if statement.strip() else "")
        head = statements[-1]
        if head not in ALLOWED_PREFIXES:
            raise RuntimeError(f"独立复算脚本出现非只读语句（{head}）：{statement[:200]}")

    return engine, {"host": url.host, "port": url.port, "database": url.database}, statements


# ---------------------------------------------------------------- 基础几何/口径
def inside(area: dict, lat: float, lon: float) -> bool:
    """§1.1 半开矩形：west <= lon < east，south <= lat < north。"""
    return area["west"] <= lon < area["east"] and area["south"] <= lat < area["north"]


def expand(area: dict, margin: float) -> dict:
    return {
        "south": area["south"] - margin, "west": area["west"] - margin,
        "north": area["north"] + margin, "east": area["east"] + margin,
    }


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = P["earth_radius_km"]
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------- 场景 1：时刻在场
SNAPSHOT_SQL = """
SELECT s.id AS ship_id, s.name, s.mmsi, s.ship_type,
       p.id AS fix_id, p.recorded_at, p.latitude, p.longitude
FROM ships s
JOIN LATERAL (
    SELECT sp.id, sp.recorded_at, sp.latitude, sp.longitude
    FROM ship_positions sp
    WHERE sp.ship_id = s.id AND sp.data_source = :source AND sp.recorded_at <= :at
    ORDER BY sp.recorded_at DESC, sp.id DESC
    LIMIT 1
) p ON true
"""


def snapshot(db: Session, area: dict, at: datetime) -> dict:
    rows = db.execute(text(SNAPSHOT_SQL), {"source": P["source"], "at": at}).mappings().all()
    in_area, fresh_out, stale = 0, 0, 0
    ships = []
    for r in rows:
        age = (at - r["recorded_at"]).total_seconds()
        fresh = age <= P["freshness_seconds"]
        if not fresh:
            stale += 1
            continue
        if inside(area, r["latitude"], r["longitude"]):
            in_area += 1
            ships.append({
                "ship_id": r["ship_id"], "name": r["name"], "mmsi": r["mmsi"],
                "ship_type": r["ship_type"], "latitude": r["latitude"], "longitude": r["longitude"],
                "recorded_at": r["recorded_at"].astimezone(UTC).isoformat(),
                "age_seconds": round(age, 3), "fresh": True, "inside": True,
            })
        else:
            fresh_out += 1
    return {
        "status": "ok" if rows else "no_data",
        "area": {"area_id": "custom" if area is not DEFAULT_AREA else DEFAULT_AREA["area_id"], **area},
        "query": {"at": at.isoformat(), "freshness_seconds": P["freshness_seconds"]},
        "summary": {
            "in_area_count": in_area,
            "out_of_area_fresh_count": fresh_out,
            "stale_fix_count": stale,
            "evaluated_ship_count": len(rows),
            "freshness_seconds": P["freshness_seconds"],
        },
        "ships_in_area": ships,
    }


# ---------------------------------------------------------------- 场景 2/3：时段活动
SCOPE_SQL = """
SELECT p.ship_id, p.id, p.recorded_at, p.latitude, p.longitude
FROM ship_positions p
JOIN ships s ON s.id = p.ship_id
WHERE p.data_source = :source
  AND p.recorded_at >= :t0 AND p.recorded_at < :t1
  AND p.longitude >= :west AND p.longitude < :east
  AND p.latitude >= :south AND p.latitude < :north
  {ship_type_clause}
  {batch_clause}
ORDER BY p.ship_id, p.recorded_at, p.id
"""

PROBE_SQL = """
SELECT v.ship_id, v.id1, v.id2,
       EXISTS (
           SELECT 1 FROM ship_positions sp
           WHERE sp.ship_id = v.ship_id AND sp.data_source = :source
             AND (sp.recorded_at, sp.id) > (v.t1, v.id1)
             AND (sp.recorded_at, sp.id) < (v.t2, v.id2)
       ) AS has_mid
FROM unnest(
    CAST(:ships AS bigint[]), CAST(:id1s AS bigint[]), CAST(:t1s AS timestamptz[]),
    CAST(:id2s AS bigint[]), CAST(:t2s AS timestamptz[])
) AS v(ship_id, id1, t1, id2, t2)
"""


def _ship_type_clause(ship_types):
    if not ship_types:
        return "", {}
    parts, params = [], {}
    plain = []
    for t in ship_types:
        if t == SHIP_TYPE_MISSING:
            parts.append("(s.ship_type IS NULL OR s.ship_type = '')")
        elif t == SHIP_TYPE_UNKNOWN:
            parts.append("s.ship_type = '未知'")
        else:
            plain.append(t)
    if plain:
        parts.append("s.ship_type = ANY(:ship_types)")
        params["ship_types"] = plain
    return "AND (" + " OR ".join(parts) + ")", params


def _need_probe(dt_seconds: float, dist_km: float) -> bool:
    """§2.0 待探测对判据：间隔 > 480 s，或（位移 >= 1 km 且推算速度 > 30 kn）。"""
    if dt_seconds > P["excursion_probe_seconds"]:
        return True
    if dt_seconds <= 0:
        return False
    speed_kn = (dist_km / (dt_seconds / 3600.0)) / 1.852
    return dist_km >= P["jump_min_distance_km"] and speed_kn > P["jump_speed_kn"]


def _classify_interval(dt_seconds: float, dist_km: float) -> str:
    """§2.3 同一访问内相邻两报位：continuous / gap / jump。"""
    if dt_seconds <= 0:
        return "continuous"
    jump = (dt_seconds <= P["gap_seconds"]
            and dist_km >= P["jump_min_distance_km"]
            and (dist_km / (dt_seconds / 3600.0)) / 1.852 > P["jump_speed_kn"])
    if jump:
        return "jump"
    if dt_seconds > P["gap_seconds"]:
        return "gap"
    return "continuous"


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def activity(db: Session, area: dict, start: datetime, end: datetime,
             ship_types=None, batch_ids=None, label: str = "") -> dict:
    """独立朴素实现，口径见 docs/area_activity.md §2。"""
    t_begin = time.perf_counter()
    ctx = expand(area, P["context_margin_deg"])
    st_clause, st_params = _ship_type_clause(ship_types)
    batch_clause, batch_params = "", {}
    if batch_ids:
        batch_clause = "AND p.source_batch_id = ANY(:batch_ids)"
        batch_params["batch_ids"] = list(batch_ids)
    sql = SCOPE_SQL.format(ship_type_clause=st_clause, batch_clause=batch_clause)
    params = {
        "source": P["source"],
        "t0": start - timedelta(seconds=P["state_lookback_seconds"]),
        "t1": end + timedelta(seconds=P["state_lookahead_seconds"]),
        "west": ctx["west"], "east": ctx["east"], "south": ctx["south"], "north": ctx["north"],
        **st_params, **batch_params,
    }

    # --- 读取观测上下文（按 ship 流式分组）
    scope_fix_count = 0
    per_ship: dict[int, list[tuple]] = {}
    result = db.connection().execution_options(stream_results=True).execute(text(sql), params)
    cur_ship, buf = None, []
    candidates: dict[int, list[tuple]] = {}
    while True:
        chunk = result.fetchmany(20000)
        if not chunk:
            break
        for ship_id, fix_id, recorded_at, lat, lon in chunk:
            scope_fix_count += 1
            if ship_id != cur_ship:
                if cur_ship is not None:
                    per_ship[cur_ship] = buf
                cur_ship, buf = ship_id, []
            buf.append((fix_id, recorded_at, lat, lon))
    if cur_ship is not None:
        per_ship[cur_ship] = buf

    non_candidates = 0
    for ship_id, fixes in per_ship.items():
        if any(start <= f[1] < end and inside(area, f[2], f[3]) for f in fixes):
            candidates[ship_id] = fixes
        else:
            non_candidates += 1
    del per_ship

    # --- 待探测对（相邻两条区内报位）
    probe_pairs: dict[int, list[tuple[int, int]]] = {}
    for ship_id, fixes in candidates.items():
        idx_inside = [i for i, f in enumerate(fixes) if inside(area, f[2], f[3])]
        pairs = []
        for a, b in zip(idx_inside, idx_inside[1:]):
            dt = (fixes[b][1] - fixes[a][1]).total_seconds()
            dist = haversine_km(fixes[a][2], fixes[a][3], fixes[b][2], fixes[b][3])
            if _need_probe(dt, dist):
                pairs.append((a, b))
        if pairs:
            probe_pairs[ship_id] = pairs

    # --- 有界存在性探测（可越出上下文，只看有/无）
    proven: dict[int, set[tuple[int, int]]] = {sid: set() for sid in probe_pairs}
    probe_pair_total = 0
    CHUNK = 2000
    for ship_id, pairs in probe_pairs.items():
        probe_pair_total += len(pairs)
    for ship_id in list(probe_pairs):
        pairs = probe_pairs[ship_id]
        for i in range(0, len(pairs), CHUNK):
            part = pairs[i:i + CHUNK]
            rows = db.execute(text(PROBE_SQL), {
                "source": P["source"],
                "ships": [ship_id] * len(part),
                "id1s": [candidates[ship_id][a][0] for a, _ in part],
                "t1s": [candidates[ship_id][a][1] for a, _ in part],
                "id2s": [candidates[ship_id][b][0] for _, b in part],
                "t2s": [candidates[ship_id][b][1] for _, b in part],
            }).all()
            for _sid, _id1, _id2, has_mid in rows:
                if has_mid:
                    for a, b in part:
                        if candidates[ship_id][a][0] == _id1 and candidates[ship_id][b][0] == _id2:
                            proven[ship_id].add((a, b))
                            break

    # --- 访问划分与统计
    day_keys = []
    d = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    while d < end:
        day_keys.append(d)
        d = d + timedelta(days=1)

    daily = {k: {"ships": set(), "entries": 0, "exits": 0, "ship_seconds": 0.0, "visits": set()}
             for k in day_keys}
    total_seconds = 0.0
    entries = exits = 0
    visit_no = 0
    visit_touch_count = 0
    visit_rows = []
    left_returned_pairs = 0

    for ship_id, fixes in candidates.items():
        n = len(fixes)
        ins = [inside(area, f[2], f[3]) for f in fixes]
        proven_set = proven.get(ship_id, set())
        left_returned_pairs += len(proven_set)
        visits: list[dict] = []
        cur = None
        for i in range(n):
            if not ins[i]:
                continue
            prev_i = i - 1 if i > 0 else None
            prev_inside = ins[prev_i] if prev_i is not None else None
            if cur is not None:
                last_i = cur["idx"][-1]
                if (last_i, i) in proven_set:
                    cur["exit_observed"] = True
                    cur["exit_left_returned"] = True
                    visits.append(cur)
                    cur = None
                elif prev_inside is False:
                    cur["exit_observed"] = True
                    visits.append(cur)
                    cur = None
            if cur is None:
                cur = {
                    "ship_id": ship_id, "idx": [i],
                    "entry_observed": prev_inside is False,
                    "prior_state": "outside" if prev_inside is False else "unknown",
                    "entry_left_returned": False,
                    "exit_observed": False, "exit_left_returned": False,
                }
                # 被探测拆开的后半段：进入由区外证据证明
                if visits and visits[-1].get("exit_left_returned"):
                    cur["entry_observed"] = True
                    cur["prior_state"] = "outside"
                    cur["entry_left_returned"] = True
            else:
                cur["idx"].append(i)
        if cur is not None:
            visits.append(cur)

        for v in visits:
            idxs = v["idx"]
            first_i, last_i = idxs[0], idxs[-1]
            # 离开观测：后一条报位在区内则不可能（同一访问已连续），区外则观测到
            if last_i + 1 < n and not ins[last_i + 1]:
                v["exit_observed"] = True
            elif last_i + 1 >= n and not v["exit_left_returned"]:
                v["exit_observed"] = False
            v["first_inside_at"] = fixes[first_i][1]
            v["last_inside_at"] = fixes[last_i][1]
            # segments（同一访问内被 gap / jump 断开）
            segments = []
            seg_start = idxs[0]
            seg_fix_count = 1
            unobserved = 0.0
            for a, b in zip(idxs, idxs[1:]):
                dt = (fixes[b][1] - fixes[a][1]).total_seconds()
                dist = haversine_km(fixes[a][2], fixes[a][3], fixes[b][2], fixes[b][3])
                kind = _classify_interval(dt, dist)
                if kind == "continuous":
                    seg_fix_count += 1
                else:
                    segments.append({"start_idx": seg_start, "end_idx": a,
                                     "fix_count": seg_fix_count,
                                     "seconds": (fixes[a][1] - fixes[seg_start][1]).total_seconds()})
                    unobserved += dt
                    seg_start, seg_fix_count = b, 1
            segments.append({"start_idx": seg_start, "end_idx": idxs[-1],
                             "fix_count": seg_fix_count,
                             "seconds": (fixes[idxs[-1]][1] - fixes[seg_start][1]).total_seconds()})
            v["segments"] = segments
            v["unobserved_gap_seconds"] = unobserved
            v["observed_seconds"] = sum(s["seconds"] for s in segments)
            window_seconds = 0.0
            for s in segments:
                s_at, e_at = fixes[s["start_idx"]][1], fixes[s["end_idx"]][1]
                window_seconds += max(0.0, (min(e_at, end) - max(s_at, start)).total_seconds())
            v["window_seconds"] = window_seconds
            v["touches_window"] = window_seconds > 0 or (v["first_inside_at"] < end and v["last_inside_at"] >= start)
            if v["touches_window"]:
                visit_touch_count += 1
            total_seconds += window_seconds
            visit_no += 1
            v["visit_key"] = f"s{ship_id}:f{fixes[first_i][0]}"

            # 事件计数（事件时间必须落在窗口内）
            if v["entry_observed"] and start <= v["first_inside_at"] < end:
                entries += 1
                v["entry_in_window"] = True
            else:
                v["entry_in_window"] = False
            if v["exit_observed"] and start <= v["last_inside_at"] < end:
                exits += 1
                v["exit_in_window"] = True
            else:
                v["exit_in_window"] = False

            # 每日统计：出现去重船数 = 当日 ∩ 窗口内至少一条区域内报位（§2.4）
            for k in day_keys:
                day_s, day_e = k, k + timedelta(days=1)
                lo, hi = max(day_s, start), min(day_e, end)
                if lo >= hi:
                    continue
                if any(lo <= fixes[j][1] < hi for j in idxs):
                    daily[k]["visits"].add(v["visit_key"])
                    daily[k]["ships"].add(ship_id)
                for s in segments:
                    s_at, e_at = fixes[s["start_idx"]][1], fixes[s["end_idx"]][1]
                    inter = max(0.0, (min(e_at, hi) - max(s_at, lo)).total_seconds())
                    if inter > 0:
                        daily[k]["ship_seconds"] += inter
                if v["entry_in_window"] and lo <= v["first_inside_at"] < hi:
                    daily[k]["entries"] += 1
                if v["exit_in_window"] and lo <= v["last_inside_at"] < hi:
                    daily[k]["exits"] += 1
            if len(visit_rows) < 2000:
                visit_rows.append({
                    "visit_key": v["visit_key"], "ship_id": ship_id,
                    "first_inside_at": _iso(v["first_inside_at"]),
                    "last_inside_at": _iso(v["last_inside_at"]),
                    "entry_observed": v["entry_observed"], "exit_observed": v["exit_observed"],
                    "prior_state": v["prior_state"],
                    "fix_count": len(idxs), "segment_count": len(segments),
                    "observed_seconds": round(v["observed_seconds"], 3),
                    "window_seconds": round(v["window_seconds"], 3),
                    "unobserved_gap_seconds": round(v["unobserved_gap_seconds"], 3),
                    "touches_window": v["touches_window"],
                    "entry_in_window": v["entry_in_window"],
                    "exit_in_window": v["exit_in_window"],
                    "status_hint": ("truncated_start" if not v["entry_observed"]
                                    else "truncated_end" if not v["exit_observed"] else "complete"),
                })

    daily_rows = []
    for k in day_keys:
        row = daily[k]
        daily_rows.append({
            "date": k.date().isoformat(),
            "ships_observed": len(row["ships"]),
            "observed_entry_count": row["entries"],
            "observed_exit_count": row["exits"],
            "observed_ship_seconds": round(row["ship_seconds"], 3),
            "observed_ship_hours": round(row["ship_seconds"] / 3600.0, 6),
            "visits_touching_day": len(row["visits"]),
        })

    visits_touching_window = visit_touch_count
    elapsed = round((time.perf_counter() - t_begin) * 1000, 1)
    return {
        "label": label,
        "area": {"area_id": "custom", **area},
        "query": {"start": _iso(start), "end": _iso(end), "ship_type": ship_types, "batch_ids": batch_ids},
        "scope": {
            "context_bbox": ctx,
            "scope_fix_count": scope_fix_count,
            "candidate_ship_count": len(candidates),
            "non_candidate_ships_with_scope_fixes": non_candidates,
            "probe_pair_count": probe_pair_total,
            "probe_confirmed_pairs": left_returned_pairs,
        },
        "summary": {
            "ships_observed": len(candidates),
            "observed_entry_count": entries,
            "observed_exit_count": exits,
            "observed_ship_seconds": round(total_seconds, 3),
            "observed_ship_hours": round(total_seconds / 3600.0, 6),
            "visit_count": visits_touching_window,
            "visits_total": visit_no,
        },
        "daily": daily_rows,
        "self_checks": {
            "sum_daily_seconds_equals_total": abs(sum(r["observed_ship_seconds"] for r in daily_rows)
                                                  - round(total_seconds, 3)) < 0.01,
            "daily_ships_le_total": all(r["ships_observed"] <= len(candidates) for r in daily_rows),
        },
        "visits_sample": visit_rows[:50],
        "elapsed_ms": elapsed,
    }


def compare(a: dict, b: dict) -> dict:
    """§2.5 两时段比较：delta = b - a；change_rate = (b - a) / a（a == 0 → null）。"""
    metrics = []
    for key in ("ships_observed", "observed_entry_count", "observed_exit_count"):
        av, bv = a["summary"][key], b["summary"][key]
        metrics.append({"metric": key, "a": av, "b": bv, "delta": bv - av,
                        "change_rate": (None if av == 0 else (bv - av) / av)})
    ah, bh = a["summary"]["observed_ship_hours"], b["summary"]["observed_ship_hours"]
    metrics.append({"metric": "observed_ship_hours", "a": ah, "b": bh, "delta": round(bh - ah, 6),
                    "change_rate": (None if ah == 0 else (bh - ah) / ah)})

    def _len_days(x):
        s = datetime.fromisoformat(x["query"]["start"])
        e = datetime.fromisoformat(x["query"]["end"])
        return (e - s).total_seconds() / 86400.0

    la, lb = _len_days(a), _len_days(b)
    return {
        "metrics": metrics,
        "comparability": {
            "same_area": a["area"] == b["area"],
            "equal_length": abs(la - lb) < 1e-9,
            "window_length_days_a": la, "window_length_days_b": lb,
        },
        "a_summary": a["summary"], "b_summary": b["summary"],
    }


SCENARIOS = [
    ("snapshot_default_2026-02-28T12:00Z", "snapshot", {"at": datetime(2026, 2, 28, 12, 0, tzinfo=UTC), "area": DEFAULT_AREA}),
    ("activity_default_1d_2026-02-28", "activity", {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
                                                    "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC), "area": DEFAULT_AREA}),
    ("activity_custom_26.0-26.8N_56.0-56.9E_1d", "activity",
     {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": {"south": 26.0, "west": 56.0, "north": 26.8, "east": 56.9}}),
    ("activity_rectA_west_1d", "activity",
     {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": {"south": 25.8, "west": 55.8, "north": 27.1, "east": 56.45}}),
    ("activity_rectB_east_1d", "activity",
     {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": {"south": 25.8, "west": 56.45, "north": 27.1, "east": 57.1}}),
    ("activity_default_1d_batch4", "activity",
     {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": DEFAULT_AREA, "batch_ids": [4]}),
    ("activity_default_1d_ship_type_oil", "activity",
     {"start": datetime(2026, 2, 28, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": DEFAULT_AREA, "ship_type": ["油轮"]}),
    ("activity_default_prev1d_2026-02-27", "activity",
     {"start": datetime(2026, 2, 27, 0, 0, tzinfo=UTC), "end": datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
      "area": DEFAULT_AREA}),
    ("activity_default_3d_2026-02-26_03-01", "activity",
     {"start": datetime(2026, 2, 26, 0, 0, tzinfo=UTC), "end": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
      "area": DEFAULT_AREA}),
    ("activity_rectA_west_prev1d", "activity",
     {"start": datetime(2026, 2, 27, 0, 0, tzinfo=UTC), "end": datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
      "area": {"south": 25.8, "west": 55.8, "north": 27.1, "east": 56.45}}),
    ("activity_rectB_east_prev1d", "activity",
     {"start": datetime(2026, 2, 27, 0, 0, tzinfo=UTC), "end": datetime(2026, 2, 28, 0, 0, tzinfo=UTC),
      "area": {"south": 25.8, "west": 56.45, "north": 27.1, "east": 57.1}}),
]


SOURCE_TABLES = ("ships", "ship_positions", "ais_import_batches")


def write_counters(db: Session) -> dict:
    rows = db.execute(text("""
        SELECT relname, n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd, n_live_tup
        FROM pg_stat_user_tables WHERE relname = ANY(:names)
    """), {"names": list(SOURCE_TABLES)}).mappings().all()
    return {r["relname"]: {"ins": r["n_tup_ins"], "upd": r["n_tup_upd"], "del": r["n_tup_del"],
                           "hot_upd": r["n_tup_hot_upd"], "live_tup": r["n_live_tup"]} for r in rows}


def table_counts(db: Session) -> dict:
    return {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in SOURCE_TABLES}


def main() -> int:
    engine, target, statements = build_engine()
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "worktree": str(ROOT),
        "database_target": target,
        "note": "独立复算；不 import backend.app.*；只读；口径依据 docs/area_activity.md",
        "params": P,
        "default_area": DEFAULT_AREA,
        "scenarios": {},
        "compare": {},
        "sql": {"scope": SCOPE_SQL, "snapshot": SNAPSHOT_SQL, "probe": PROBE_SQL},
    }
    results = {}
    with Session(engine) as db:
        # 当前事务显式只读：SET TRANSACTION 必须作为事务内第一条语句执行
        db.execute(text("SET TRANSACTION READ ONLY"))
        readonly = db.execute(text("SHOW transaction_read_only")).scalar()
        payload["session_transaction_read_only"] = readonly
        assert readonly == "on", f"只读事务未生效：transaction_read_only={readonly}"
        before_counts, before_write = table_counts(db), write_counters(db)
        log(f"read-only transaction = {readonly}; db={target['database']}@{target['host']}:{target['port']}")
        for name, kind, opts in SCENARIOS:
            log(f"[scenario] {name} ...")
            if kind == "snapshot":
                res = snapshot(db, opts["area"], opts["at"])
            else:
                res = activity(db, opts["area"], opts["start"], opts["end"],
                               ship_types=opts.get("ship_type"), batch_ids=opts.get("batch_ids"),
                               label=name)
            results[name] = res
            payload["scenarios"][name] = res
            s = res["summary"]
            log(f"    -> {json.dumps({k: s[k] for k in s if not k.endswith('_seconds')}, ensure_ascii=False)}"
                f" ({res.get('elapsed_ms', 'n/a')} ms)")
        payload["compare"]["default_prev1d_vs_1d"] = compare(results["activity_default_prev1d_2026-02-27"],
                                                             results["activity_default_1d_2026-02-28"])
        payload["compare"]["rectA_prev1d_vs_1d"] = compare(results["activity_rectA_west_prev1d"],
                                                          results["activity_rectA_west_1d"])
        payload["compare"]["rectB_prev1d_vs_1d"] = compare(results["activity_rectB_east_prev1d"],
                                                          results["activity_rectB_east_1d"])
        payload["compare"]["default_1d_batch4_vs_all"] = compare(results["activity_default_1d_2026-02-28"],
                                                                 results["activity_default_1d_batch4"])
        # 跨矩形同窗口对照：/api/area-activity/compare 要求两期同一矩形（§2.5），
        # 因此这条只作几何对照，不能作为 API 期望值。
        payload["compare"]["rectA_vs_rectB_same_window_not_api_case"] = compare(
            results["activity_rectA_west_1d"], results["activity_rectB_east_1d"])
        after_counts, after_write = table_counts(db), write_counters(db)
        payload["readonly_evidence"] = {
            "transaction_read_only": readonly,
            "table_counts_before": before_counts, "table_counts_after": after_counts,
            "table_counts_unchanged": before_counts == after_counts,
            "write_counters_before": before_write, "write_counters_after": after_write,
            "write_counters_unchanged": before_write == after_write,
        }
        payload["statements_observed"] = sorted(set(statements))
        payload["read_only_prefixes_only"] = all(s in ALLOWED_PREFIXES for s in statements)
        assert before_counts == after_counts, "源表行数在本脚本运行期间发生变化"
        assert before_write == after_write, "pg_stat 写计数在本脚本运行期间发生变化"
        assert payload["read_only_prefixes_only"], "出现非只读语句前缀"

    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"written: {OUT}")
    c = payload["compare"]["default_prev1d_vs_1d"]
    log("rectA vs rectB: " + json.dumps(c["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
