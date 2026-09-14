"""Acceptance checks for a generated simulation batch.

Runs over the written output files only, so it can be executed independently of
the generator. `model_stats` (optional) carries numbers that only exist inside the
generation process, such as intervals before dropout; those are reported separately
and clearly marked as model-side.

Standard library only.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from geo import haversine_km  # noqa: E402
from land_check import LandChecker  # noqa: E402

PLAYBACK_MAX_RANGE_HOURS = 24
PLAYBACK_MAX_POINTS = 50000

REQUIRED_POSITION_FIELDS = {
    "temp_ship_id": int,
    "latitude": float,
    "longitude": float,
    "speed": float,
    "course": float,
    "recorded_at": str,
    "data_source": str,
}
NULLABLE_POSITION_FIELDS = {"heading", "unix_time", "nav_status", "rot", "draught_m",
                            "destination", "ais_type"}
REQUIRED_SHIP_FIELDS = {"temp_ship_id": int, "mmsi": str, "name": str, "ship_type": str}
NULLABLE_SHIP_FIELDS = {"flag", "imo", "callsign", "length_m", "width_m"}

UNDERWAY_STATUS = {"在航", "操纵受限"}
ANCHORED_STATUS = {"锚泊", "漂航"}


def quantile(ordered: list[float], q: float) -> float:
    if not ordered:
        return float("nan")
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def describe(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    mean = sum(ordered) / len(ordered)
    stdev = statistics.pstdev(ordered) if len(ordered) > 1 else 0.0
    return {
        "n": len(ordered),
        "mean": round(mean, 2),
        "median": round(quantile(ordered, 0.5), 2),
        "p10": round(quantile(ordered, 0.1), 2),
        "p90": round(quantile(ordered, 0.9), 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "stdev": round(stdev, 2),
        "cv": round(stdev / mean, 4) if mean else None,
    }


def parse_ts(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_acceptance(outdir: Path, cfg: dict, model_stats: dict | None = None,
                   news_snapshot_available: bool | None = None) -> dict:
    land = LandChecker.from_geojson(ROOT / "reference" / "ne_10m_land.geojson")
    land.build()

    report: dict = {"outdir": str(outdir), "checks": {}, "failures": [], "warnings": []}
    checks = report["checks"]

    def fail(area: str, message: str) -> None:
        report["failures"].append(f"{area}: {message}")

    def warn(area: str, message: str) -> None:
        report["warnings"].append(f"{area}: {message}")

    # ---------- load ----------
    ships_path = outdir / "ships.jsonl"
    positions_dir = outdir / cfg["output"]["positions_subdir"]
    raw_dir = outdir / cfg["output"]["raw_subdir"]

    ships = load_jsonl(ships_path)
    position_files = sorted(positions_dir.glob("positions_*.jsonl"))
    raw_files = sorted(raw_dir.glob("raw_*.jsonl"))
    positions = [row for path in position_files for row in load_jsonl(path)]
    raw = [row for path in raw_files for row in load_jsonl(path)]

    checks["row_counts"] = {
        "ships": len(ships),
        "position_files": len(position_files),
        "positions": len(positions),
        "raw_files": len(raw_files),
        "raw_records": len(raw),
        "expected_ships": cfg["ships"]["count"],
        "expected_days": cfg["time_window"]["days"],
    }
    if len(ships) != cfg["ships"]["count"]:
        fail("规模", f"船舶数量 {len(ships)} != 配置 {cfg['ships']['count']}")
    if len(position_files) != cfg["time_window"]["days"]:
        fail("规模", f"船位分片数 {len(position_files)} != 窗口天数 {cfg['time_window']['days']}")

    # ---------- schema / types / required / length ----------
    ship_field_issues = []
    mmsi_seen: set[str] = set()
    temp_ids: set[int] = set()
    for index, ship in enumerate(ships):
        for field, expected in REQUIRED_SHIP_FIELDS.items():
            value = ship.get(field)
            if not isinstance(value, expected):
                ship_field_issues.append(f"第 {index} 行 {field} 类型错误：{type(value).__name__}")
        for field in NULLABLE_SHIP_FIELDS:
            if field in ship and ship[field] is not None and not isinstance(ship[field], (str, float, int)):
                ship_field_issues.append(f"第 {index} 行 {field} 类型错误")
        if len(ship.get("mmsi", "")) != 9 or not ship["mmsi"].isdigit():
            ship_field_issues.append(f"第 {index} 行 MMSI 非 9 位数字：{ship.get('mmsi')!r}")
        if "SIM" not in ship.get("name", ""):
            ship_field_issues.append(f"第 {index} 行船名未标注 SIM：{ship.get('name')!r}")
        if len(ship.get("name", "")) > 100:
            ship_field_issues.append(f"第 {index} 行船名超过 100 字符")
        if ship.get("ship_type") and len(ship["ship_type"]) > 50:
            ship_field_issues.append(f"第 {index} 行船型超过 50 字符")
        if ship.get("flag") is not None and len(ship["flag"]) > 50:
            ship_field_issues.append(f"第 {index} 行船旗超过 50 字符")
        if ship.get("imo") is not None and len(ship["imo"]) > 20:
            ship_field_issues.append(f"第 {index} 行 IMO 超过 20 字符")
        if ship.get("callsign") is not None and len(ship["callsign"]) > 20:
            ship_field_issues.append(f"第 {index} 行呼号超过 20 字符")
        mmsi_seen.add(ship["mmsi"])
        temp_ids.add(ship["temp_ship_id"])
    checks["ships"] = {
        "mmsi_unique": len(mmsi_seen) == len(ships),
        "mmsi_9_digit": all(len(s) == 9 and s.isdigit() for s in mmsi_seen),
        "temp_id_unique": len(temp_ids) == len(ships),
        "field_issue_count": len(ship_field_issues),
        "field_issues_sample": ship_field_issues[:5],
        "ship_type_distribution": dict(sorted(
            ((t, sum(1 for s in ships if s["ship_type"] == t))
             for t in {s["ship_type"] for s in ships}), key=lambda kv: -kv[1])),
        "has_sim_in_name": all("SIM" in s["name"] for s in ships),
        "imo_all_null": all(s.get("imo") is None for s in ships),
    }
    if ship_field_issues:
        fail("船舶字段", f"{len(ship_field_issues)} 项字段问题")
    if len(mmsi_seen) != len(ships):
        fail("标识唯一性", "船舶 MMSI 存在重复")

    # ---------- position field checks ----------
    position_issues = []
    unix_mismatch = 0
    naive_time = 0
    lat_out = lon_out = speed_out = course_out = heading_out = 0
    data_source_bad = 0
    field_missing = defaultdict(int)
    landing: set[int] = set()
    landing_count = 0
    stored_fields: set[str] = set()

    for row in positions:
        stored_fields.update(row.keys())
        for field, expected in REQUIRED_POSITION_FIELDS.items():
            value = row.get(field)
            if not isinstance(value, expected):
                position_issues.append(f"{field} 类型错误：{type(value).__name__}")
        for field in ("temp_ship_id", "latitude", "longitude", "speed", "course",
                      "recorded_at", "data_source"):
            if row.get(field) is None:
                position_issues.append(f"{field} 为 NULL")
        if "location" in row:
            position_issues.append("出现了不应手动写入的 location 字段")
        if row["temp_ship_id"] not in temp_ids:
            position_issues.append(f"temp_ship_id {row['temp_ship_id']} 无对应船舶")
        if row.get("data_source") != "simulation":
            data_source_bad += 1
        for field in NULLABLE_POSITION_FIELDS:
            if row.get(field) is None:
                field_missing[field] += 1

        moment = parse_ts(row["recorded_at"])
        if moment.tzinfo is None or moment.utcoffset() != timedelta(0):
            naive_time += 1
        if row.get("unix_time") is not None and int(moment.timestamp()) != row["unix_time"]:
            unix_mismatch += 1
        if not -90 <= row["latitude"] <= 90:
            lat_out += 1
        if not -180 <= row["longitude"] <= 180:
            lon_out += 1
        if row["speed"] < 0 or row["speed"] > 60:
            speed_out += 1
        if not 0 <= row["course"] < 360:
            course_out += 1
        if row.get("heading") is not None and not 0 <= row["heading"] < 360:
            heading_out += 1
        if len(row.get("nav_status") or "") > 50:
            position_issues.append("nav_status 超过 50 字符")
        if len(row.get("destination") or "") > 255:
            position_issues.append("destination 超过 255 字符")
        if len(row.get("ais_type") or "") > 50:
            position_issues.append("ais_type 超过 50 字符")
        if len(row.get("data_source") or "") > 50:
            position_issues.append("data_source 超过 50 字符")
        if row.get("rot") is not None:
            position_issues.append("rot 应为 NULL")

    checks["positions_schema"] = {
        "issue_count": len(position_issues),
        "issues_sample": position_issues[:6],
        "fields_present": sorted(stored_fields),
        "unix_time_mismatch": unix_mismatch,
        "non_utc_recorded_at": naive_time,
        "latitude_out_of_range": lat_out,
        "longitude_out_of_range": lon_out,
        "speed_out_of_range": speed_out,
        "course_out_of_range": course_out,
        "heading_out_of_range": heading_out,
        "data_source_not_simulation": data_source_bad,
        "null_counts": dict(sorted(field_missing.items())),
        "rot_null_ratio": round(field_missing.get("rot", 0) / max(1, len(positions)), 6),
        "unix_time_present_ratio": round(1 - field_missing.get("unix_time", 0) / max(1, len(positions)), 6),
        "ais_type_present_ratio": round(1 - field_missing.get("ais_type", 0) / max(1, len(positions)), 6),
        "draught_present_ratio": round(1 - field_missing.get("draught_m", 0) / max(1, len(positions)), 6),
    }
    if position_issues:
        fail("船位字段", f"{len(position_issues)} 项问题")
    if unix_mismatch:
        fail("时间一致性", f"{unix_mismatch} 条 unix_time 与 recorded_at 不一致")
    if data_source_bad:
        fail("数据来源", f"{data_source_bad} 条 data_source 不是 simulation")
    if lat_out or lon_out or speed_out or course_out or heading_out:
        fail("取值范围", "存在越界坐标、速度或方向字段")

    # ---------- interval statistics (file-side, observed) ----------
    by_ship: dict[int, list[dict]] = defaultdict(list)
    for row in positions:
        by_ship[row["temp_ship_id"]].append(row)
    for rows in by_ship.values():
        rows.sort(key=lambda r: r["recorded_at"])

    underway_intervals: list[float] = []
    anchored_intervals: list[float] = []
    transition_intervals: list[float] = []
    interval_histogram: dict[str, int] = defaultdict(int)
    per_ship_counts: list[int] = []
    longest_gaps: list[float] = []
    gap_gt_hour = 0
    gap_gt_4h = 0
    gap_gt_hour_underway = 0
    gap_gt_hour_anchored = 0
    gap_gt_hour_transition = 0

    for ship_id, rows in by_ship.items():
        per_ship_counts.append(len(rows))
        for previous, current in zip(rows, rows[1:]):
            seconds = (parse_ts(current["recorded_at"]) - parse_ts(previous["recorded_at"])).total_seconds()
            if seconds <= 0:
                continue
            state_before = previous.get("nav_status") or ""
            state_after = current.get("nav_status") or ""
            if state_before in UNDERWAY_STATUS and state_after in UNDERWAY_STATUS:
                underway_intervals.append(seconds)
                if seconds > 3600:
                    gap_gt_hour_underway += 1
            elif state_before in ANCHORED_STATUS and state_after in ANCHORED_STATUS:
                anchored_intervals.append(seconds)
                if seconds > 3600:
                    gap_gt_hour_anchored += 1
            else:
                transition_intervals.append(seconds)
                if seconds > 3600:
                    gap_gt_hour_transition += 1
            interval_histogram[f"{int(seconds // 60)}"] += 1
            if seconds > 3600:
                gap_gt_hour += 1
            if seconds > 4 * 3600:
                gap_gt_4h += 1
        for previous, current in zip(rows, rows[1:]):
            seconds = (parse_ts(current["recorded_at"]) - parse_ts(previous["recorded_at"])).total_seconds()
            if seconds > 0:
                longest_gaps.append(seconds)

    checks["intervals"] = {
        "underway": describe(underway_intervals),
        "anchored": describe(anchored_intervals),
        "state_transition": describe(transition_intervals),
        "per_ship_position_count": describe([float(c) for c in per_ship_counts]),
        "gaps_over_1h": gap_gt_hour,
        "gaps_over_1h_by_state": {
            "underway_both_ends": gap_gt_hour_underway,
            "anchored_both_ends": gap_gt_hour_anchored,
            "state_transition": gap_gt_hour_transition,
        },
        "gaps_over_4h": gap_gt_4h,
        "distinct_interval_minute_buckets": len(interval_histogram),
        "top_interval_buckets": sorted(interval_histogram.items(), key=lambda kv: -kv[1])[:5],
        "expected_log_normal_tail_note_zh": (
            "对数正态 σ=0.6 时，在航间隔超过 1 小时的天然概率约 0.5%，锚泊间隔（均值 45 分钟）"
            "超过 1 小时的天然概率约 22%。因此固定 1 小时阈值不是识别信号丢失的好办法；"
            "锚泊间隔的长尾属于分布本身，不能当作异常。"
        ),
    }
    if not underway_intervals or not anchored_intervals:
        warn("间隔统计", "在航或锚泊的间隔样本为空，无法分别统计")

    # ---------- irregularity and asynchrony evidence ----------
    timestamp_counts: dict[str, int] = defaultdict(int)
    second_ship_sets: dict[str, set] = defaultdict(set)
    for row in positions:
        timestamp_counts[row["recorded_at"]] += 1
        second_ship_sets[row["recorded_at"]].add(row["temp_ship_id"])
    max_same_second = max((len(v) for v in second_ship_sets.values()), default=0)
    all_underway = underway_intervals
    unique_ratio = len(set(round(v, 3) for v in all_underway)) / max(1, len(all_underway))
    checks["irregularity"] = {
        "total_positions": len(positions),
        "distinct_recorded_at": len(timestamp_counts),
        "distinct_ratio": round(len(timestamp_counts) / max(1, len(positions)), 4),
        "max_ships_in_same_second": max_same_second,
        "max_rows_in_same_second": max(timestamp_counts.values(), default=0),
        "underway_interval_unique_ratio": round(unique_ratio, 4),
        "exactly_900s_share": round(
            sum(1 for v in all_underway if abs(v - 900) < 1e-9) / max(1, len(all_underway)), 6
        ),
        "exactly_1800s_share": round(
            sum(1 for v in all_underway if abs(v - 1800) < 1e-9) / max(1, len(all_underway)), 6
        ),
    }
    if checks["irregularity"]["exactly_900s_share"] > 0.02:
        fail("不规则性", "在航间隔中固定 900 秒占比过高，疑似等间隔生成")
    if max_same_second > max(3, int(0.05 * len(ships))):
        fail("异步性", f"同一秒内有 {max_same_second} 艘船同时报位，疑似同步生成")

    # ---------- anomaly counts on the raw feed ----------
    raw_by_ship: dict[int, list[dict]] = defaultdict(list)
    raw_keys: dict[tuple, int] = defaultdict(int)
    for row in raw:
        raw_by_ship[row["temp_ship_id"]].append(row)
        raw_keys[(row["temp_ship_id"], row["recorded_at"], row["latitude"], row["longitude"])] += 1
    for rows in raw_by_ship.values():
        rows.sort(key=lambda r: r["arrival_seq"])

    duplicate_records = sum(count - 1 for count in raw_keys.values() if count > 1)
    out_of_order_records = 0
    for rows in raw_by_ship.values():
        previous = None
        for row in rows:
            moment = parse_ts(row["recorded_at"])
            if previous is not None and moment < previous:
                out_of_order_records += 1
            previous = moment

    implied_speed_high = 0
    speed_ratio = cfg["cleaning"].get("quarantine_speed_ratio", 1.6)
    speed_margin = cfg["cleaning"].get("quarantine_speed_margin_kn", 4.0)
    speed_floor = cfg["cleaning"].get("quarantine_speed_floor_kn", 6.0)
    for ship_id, rows in raw_by_ship.items():
        previous = None
        for row in rows:
            if previous is not None:
                seconds = (parse_ts(row["recorded_at"]) - parse_ts(previous["recorded_at"])).total_seconds()
                if seconds > 0:
                    implied = haversine_km(
                        (previous["latitude"], previous["longitude"]),
                        (row["latitude"], row["longitude"]),
                    ) / (seconds / 3600.0) / 1.852
                    limit = max(
                        speed_ratio * max(previous["speed"], row["speed"]) + speed_margin,
                        speed_floor,
                    )
                    if implied > limit:
                        implied_speed_high += 1
            previous = row

    heading_missing_raw = sum(1 for row in raw if row.get("heading") is None)
    raw_arrival_monotonic = all(
        raw[i]["arrival_seq"] <= raw[i + 1]["arrival_seq"] for i in range(len(raw) - 1)
    )
    checks["anomalies_observed_in_files"] = {
        "raw_records": len(raw),
        "clean_records": len(positions),
        "removed_by_cleaning": len(raw) - len(positions),
        "duplicate_records_detected": duplicate_records,
        "out_of_order_records_detected": out_of_order_records,
        "records_with_implied_speed_over_threshold": implied_speed_high,
        "heading_missing_in_raw": heading_missing_raw,
        "heading_missing_ratio_raw": round(heading_missing_raw / max(1, len(raw)), 5),
        "heading_missing_in_clean": checks["positions_schema"]["null_counts"].get("heading", 0),
        "raw_sorted_by_arrival_seq": raw_arrival_monotonic,
        "longest_single_gap_hours": round(max(longest_gaps) / 3600.0, 3) if longest_gaps else None,
        "gaps_over_1h": gap_gt_hour,
    }

    labels_path = outdir / "anomaly_labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else {}
    checks["anomalies_injected"] = {
        "source": "anomaly_labels.json（生成过程写入的注入记录）",
        "by_type": labels.get("by_type", {}),
        "blackout_windows": len(labels.get("blackout_windows", [])),
        "position_jump_records": len(labels.get("position_jump_records", [])),
        "duplicate_records": len(labels.get("duplicate_records", [])),
    }
    if labels:
        injected_jumps = len(labels.get("position_jump_records", []))
        if injected_jumps and implied_speed_high < injected_jumps * 0.5:
            warn("跳点清洗", f"注入 {injected_jumps} 个跳点，规则只识别出 {implied_speed_high} 条")

    # ---------- trajectory consistency ----------
    deviations = []
    implied_speeds = []
    reported_speeds = []
    for ship_id, rows in by_ship.items():
        for previous, current in zip(rows, rows[1:]):
            seconds = (parse_ts(current["recorded_at"]) - parse_ts(previous["recorded_at"])).total_seconds()
            if seconds <= 0 or seconds > 6 * 3600:
                continue
            distance = haversine_km(
                (previous["latitude"], previous["longitude"]),
                (current["latitude"], current["longitude"]),
            )
            implied = distance / (seconds / 3600.0) / 1.852
            implied_speeds.append(implied)
            reported_speeds.append(current["speed"])
            if current["speed"] > 0.5:
                deviations.append(abs(implied - current["speed"]) / current["speed"])
    checks["trajectory_consistency"] = {
        "pairs": len(implied_speeds),
        "implied_speed": describe(implied_speeds),
        "reported_speed": describe(reported_speeds),
        "relative_deviation_share": describe([v * 100 for v in deviations]) if deviations else {"n": 0},
        "note_zh": "推算航速由相邻报位距离除以时间得到；受不规则间隔与定位噪声影响，与报位航速存在差异属预期现象。",
    }
    if deviations:
        median_deviation = sorted(deviations)[len(deviations) // 2]
        if median_deviation > 0.60:
            warn("轨迹一致性", f"推算航速与报位航速中位相对偏差 {median_deviation:.2%} 偏大")

    # ---------- land intersection ----------
    for row in positions:
        if land.is_land(row["longitude"], row["latitude"]):
            landing_count += 1
            if len(landing) < 20:
                landing.add(row["temp_ship_id"])
    raw_landing = sum(1 for row in raw if land.is_land(row["longitude"], row["latitude"]))
    checks["land_check"] = {
        "clean_positions_on_land": landing_count,
        "raw_positions_on_land": raw_landing,
        "clean_on_land_ratio": round(landing_count / max(1, len(positions)), 6),
        "affected_ship_ids_sample": sorted(landing)[:20],
        "reference": "Natural Earth 1:10m land polygons",
        "precision_note_zh": "1:10m 概化岸线，近岸精度数百米至 1 km，缺失防波堤、填海区、极小岛礁。只能筛查明显穿越陆地，不等于航道级验证。",
    }
    if landing_count:
        fail("陆地相交", f"数据库兼容文件中有 {landing_count} 个点落在参考陆地上")

    # ---------- daily counts vs playback limits ----------
    daily = defaultdict(int)
    for row in positions:
        daily[row["recorded_at"][:10]] += 1
    daily_checks = {}
    for date_key in sorted(daily):
        daily_checks[date_key] = {
            "positions": daily[date_key],
            "within_24h_limit": True,
            "within_point_limit": daily[date_key] <= PLAYBACK_MAX_POINTS,
        }
    checks["playback_limits"] = {
        "max_range_hours": PLAYBACK_MAX_RANGE_HOURS,
        "max_points": PLAYBACK_MAX_POINTS,
        "daily": daily_checks,
        "all_days_within_point_limit": all(v["within_point_limit"] for v in daily_checks.values()),
        "note_zh": "分片粒度为 UTC 自然日（24 小时），因此每次回放请求天然满足 24 小时上限；每片点数须不超过 50,000。",
    }
    if not checks["playback_limits"]["all_days_within_point_limit"]:
        fail("回放限制", "存在单日点数超过 50,000 的分片")

    # ---------- phase / behaviour correspondence ----------
    phases = [
        {**phase, "start": parse_ts(phase["start_utc"]), "end": parse_ts(phase["end_utc"])}
        for phase in cfg["scenario_phases"]
    ]
    phase_stats = {}
    strait_box = (26.20, 26.95, 56.15, 56.75)
    for phase in phases:
        speeds = []
        anchored = 0
        total = 0
        ships_seen = set()
        ships_anchored = set()
        strait_ships = set()
        for row in positions:
            moment = parse_ts(row["recorded_at"])
            if not (phase["start"] <= moment < phase["end"]):
                continue
            total += 1
            speeds.append(row["speed"])
            if (row.get("nav_status") or "") in ANCHORED_STATUS:
                anchored += 1
                ships_anchored.add(row["temp_ship_id"])
            ships_seen.add(row["temp_ship_id"])
            if (strait_box[0] <= row["latitude"] <= strait_box[1]
                    and strait_box[2] <= row["longitude"] <= strait_box[3]):
                strait_ships.add(row["temp_ship_id"])
        phase_stats[phase["id"]] = {
            "label_zh": phase["label_zh"],
            "evidence": phase["evidence"],
            "window_utc": [phase["start_utc"], phase["end_utc"]],
            "reports": total,
            "distinct_ships": len(ships_seen),
            "ships_ever_anchored": len(ships_anchored),
            "ships_ever_anchored_share": round(len(ships_anchored) / len(ships), 4) if ships else None,
            "ships_active_in_strait_box": len(strait_ships),
            "mean_speed_kn": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "median_speed_kn": round(quantile(sorted(speeds), 0.5), 2) if speeds else None,
            "anchored_report_share": round(anchored / total, 4) if total else None,
            "below_1kn_report_share": round(
                sum(1 for s in speeds if s < 1.0) / total, 4
            ) if total else None,
        }
    checks["phase_behaviour"] = phase_stats
    checks["phase_behaviour_note_zh"] = (
        "ships_active_in_strait_box 统计在 26.20-26.95°N / 56.15-56.75°E 参考框内至少报位一次的模拟船数量，"
        "是过境活跃度的近似指标，不是官方过境统计。锚泊比例按报位条数加权，锚泊船报位更稀疏，"
        "因此该比例低于“曾经锚泊的船数占比”。"
    )

    # ---------- strait throughput (过境数量) ----------
    checks["strait_throughput"] = measure_strait_throughput(outdir, by_ship, phases)

    # ---------- reproducibility ----------
    manifest_path = outdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    present: dict[str, Path] = {}
    for path in outdir.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".jsonl"):
            present.setdefault(path.name, path)
    declared = manifest.get("files", {})
    recomputed = {name: hash_text(present[name]) for name in declared if name in present}
    missing = sorted(name for name in declared if name not in present)
    mismatches = [name for name, digest in recomputed.items() if declared[name] != digest]
    checks["reproducibility"] = {
        "manifest_declared_files": len(declared),
        "recomputed_files": len(recomputed),
        "missing_declared_files": missing,
        "hash_mismatches": mismatches,
        "declared_payload_sha256": manifest.get("deterministic_payload_sha256"),
        "note_zh": "文件摘要与 manifest 一致说明产物未被修改。同种子同配置的可重复性需要另外运行 generate.py --repeat-check 验证。",
    }
    if mismatches:
        fail("可重复性", f"文件摘要与 manifest 不一致：{mismatches[:5]}")
    if missing:
        fail("可重复性", f"manifest 声明的文件缺失：{missing[:5]}")

    # ---------- model-side statistics ----------
    checks["model_side_statistics"] = {
        "note_zh": "以下数字只在生成过程中存在，用于对比“缺报前生成间隔”与“缺报后实际观测间隔”，属于模型侧统计，不是从交付文件读取。",
        "available": bool(model_stats),
    }
    if model_stats:
        checks["model_side_statistics"].update({
            "generated_interval_mean_underway_s": model_stats.get("generated_underway"),
            "generated_interval_mean_anchored_s": model_stats.get("generated_anchored"),
            "generated_interval_all": model_stats.get("generated_all"),
            "design_mean_underway_s": model_stats.get("design_mean_underway_s"),
            "design_mean_anchored_s": model_stats.get("design_mean_anchored_s"),
            "sigma_log_space": model_stats.get("sigma_log_space"),
            "truncation": model_stats.get("truncation"),
            "clamped_reports": model_stats.get("clamped_reports"),
            "voyages": model_stats.get("voyages"),
            "off_area_hours_total": model_stats.get("off_area_hours"),
            "phase_mode_distribution": model_stats.get("phase_modes"),
            "mode_hours": model_stats.get("mode_hours"),
            "injected_anomalies": model_stats.get("injected_anomalies"),
            "cleaning": model_stats.get("cleaning"),
            "database_verified": model_stats.get("database_verified"),
            "database_notes": model_stats.get("database_notes"),
            "identity_check": model_stats.get("identity_check"),
        })

    # ---------- verification source separation ----------
    checks["verification_scope"] = {
        "actual_database_verified": model_stats.get("database_verified", False) if model_stats else False,
        "actual_database_notes": model_stats.get("database_notes", []) if model_stats else [],
        "model_only_checks": [
            "间隔均值设计值（在航 900 秒 / 锚泊 2700 秒）与实际观测均值的对比",
            "异常注入数量（dropout / blackout / duplicate / out-of-order / jump）",
            "陆地修剪（land clamp）触发次数",
            "阶段与行为的内部判定过程",
        ],
        "file_only_checks": [
            "字段类型、必填项、长度、外键映射",
            "标识唯一性、UTC 与 Unix 秒一致性、坐标与方向取值区间",
            "实际观测间隔统计（在航 / 锚泊 / 状态切换）",
            "不规则性与异步性证据",
            "文件侧异常计数（重复、乱序、跳点、字段缺失）",
            "轨迹一致性、陆地相交、每日点数与回放限制",
            "阶段与观测航速、锚泊比例的对应关系",
            "文件摘要与 manifest 一致性",
        ],
        "news_snapshot_available": news_snapshot_available,
    }

    report["summary"] = {
        "ships": len(ships),
        "positions": len(positions),
        "raw_records": len(raw),
        "days": len(daily),
        "failures": len(report["failures"]),
        "warnings": len(report["warnings"]),
    }
    return report


def hash_text(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


# Strait of Hormuz crossing measurement.
# A crossing is counted when two consecutive reports of the same ship straddle the
# strait band, i.e. the track passes from west of 56.20E to east of 56.70E (or the
# reverse) while staying inside 26.10-27.10N. Requiring both reports to be at or above
# a minimum speed keeps anchored or slowly drifting ships out of the count.
STRAIT_WEST_LON = 56.20
STRAIT_EAST_LON = 56.70
STRAIT_LAT_MIN = 26.10
STRAIT_LAT_MAX = 27.10
CROSSING_MIN_SPEED_KN = 3.0


def measure_strait_throughput(outdir: Path, by_ship: dict, phases: list[dict]) -> dict:
    """Count strait crossings and attribute them to reacting vs unaffected ships."""
    crossings: list[tuple[str, int, int]] = []
    for ship_id, rows in by_ship.items():
        for a, b in zip(rows, rows[1:]):
            if min(a["speed"], b["speed"]) < CROSSING_MIN_SPEED_KN:
                continue
            if not (STRAIT_LAT_MIN <= a["latitude"] <= STRAIT_LAT_MAX
                    and STRAIT_LAT_MIN <= b["latitude"] <= STRAIT_LAT_MAX):
                continue
            eastbound = a["longitude"] < STRAIT_WEST_LON <= b["longitude"]
            westbound = a["longitude"] > STRAIT_EAST_LON >= b["longitude"]
            if eastbound or westbound:
                crossings.append((a["recorded_at"], ship_id, 1 if eastbound else -1))
    crossings.sort()

    unaffected: set[int] = set()
    links_path = outdir / "scenario_links.json"
    if links_path.exists():
        links = json.loads(links_path.read_text(encoding="utf-8"))
        unaffected = {
            item["temp_ship_id"] for item in links.get("participating_ships", [])
            if item.get("unaffected_background_ship")
        }

    by_phase = {}
    for phase in phases:
        start, end = phase["start"], phase["end"]
        hours = (end - start).total_seconds() / 3600.0
        inside = [c for c in crossings if start <= parse_ts(c[0]) < end]
        unaff = [c for c in inside if c[1] in unaffected]
        by_phase[phase["id"]] = {
            "label_zh": phase["label_zh"],
            "evidence": phase["evidence"],
            "hours": round(hours, 1),
            "crossings": len(inside),
            "crossings_per_day": round(len(inside) / hours * 24, 2) if hours else None,
            "distinct_ships": len({c[1] for c in inside}),
            "eastbound": sum(1 for c in inside if c[2] == 1),
            "westbound": sum(1 for c in inside if c[2] == -1),
            "crossings_by_unaffected_ships": len(unaff),
            "crossings_by_unaffected_share": round(len(unaff) / len(inside), 4) if inside else None,
        }

    per_day: dict[str, int] = {}
    for when, _ship, _direction in crossings:
        per_day[when[:10]] = per_day.get(when[:10], 0) + 1

    baseline = next((v for k, v in by_phase.items() if k.startswith("P0")), None)
    peak = next((v for k, v in by_phase.items() if k.startswith("P2")), None)
    drop = None
    if baseline and peak and baseline["crossings_per_day"]:
        drop = round(1 - peak["crossings_per_day"] / baseline["crossings_per_day"], 4)

    return {
        "definition_zh": (
            f"同一船舶相邻两条报位跨越海峡带（经度从 <{STRAIT_WEST_LON} 到 >{STRAIT_EAST_LON}，或反向，"
            f"且两条报位纬度都在 {STRAIT_LAT_MIN}-{STRAIT_LAT_MAX}N、航速都不低于 "
            f"{CROSSING_MIN_SPEED_KN} 节）即计一次过境。"
        ),
        "min_speed_kn": CROSSING_MIN_SPEED_KN,
        "total_crossings": len(crossings),
        "total_distinct_ships": len({c[1] for c in crossings}),
        "total_crossings_by_unaffected_ships": sum(1 for c in crossings if c[1] in unaffected),
        "unaffected_ship_count": len(unaffected),
        "per_day": per_day,
        "per_phase": by_phase,
        "peak_vs_baseline_drop": drop,
        "note_zh": (
            "本项只统计被观测到的过境。船舶在出境时段或长空窗期间穿越海峡不会被计入，"
            "因此这是过境量的下限估计，不是官方过境统计。"
            "crossings_by_unaffected_ships 指情景中被设定为“任何阶段都不响应”的背景船所贡献的过境次数，"
            "用于判断残余通行量中有多少来自刻意保留的不响应船。"
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="对已生成的模拟 AIS 批次执行验收")
    parser.add_argument("--config", default=str(ROOT / "config" / "scenario_config.json"))
    parser.add_argument("--outdir", default=str(ROOT / "output"))
    parser.add_argument("--report", default=None)
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = run_acceptance(Path(args.outdir), cfg)
    target = Path(args.report) if args.report else Path(args.outdir) / "acceptance_report.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = report["summary"]
    print(f"船舶 {summary['ships']}，船位 {summary['positions']}，原始 {summary['raw_records']}，天数 {summary['days']}")
    print(f"失败 {summary['failures']} 项，警告 {summary['warnings']} 项")
    for item in report["failures"]:
        print(f"  [失败] {item}")
    for item in report["warnings"]:
        print(f"  [警告] {item}")
    print(f"报告：{target}")
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
