"""Deterministic generator for teaching-grade simulated AIS position data.

Strait of Hormuz demonstration batch. Standard library only.

Pipeline
--------
1. identities : 150 simulated ships, unique 9-digit MMSI, Chinese ship types
2. motion     : continuous physical transit simulation on coastline-validated centre-lines
3. behaviour  : phase-driven slowdown / holding / anchoring, per ship, asynchronous
4. reporting  : irregular asynchronous sampling with log-normal intervals
5. anomalies  : dropouts, blackouts, noise, duplicates, reordering, isolated jumps
6. cleaning   : dedupe, quarantine physically impossible jumps, sort - no interpolation
7. export     : JSONL ships / positions by UTC date / raw observations / labels / manifest

Run:
    python tools/generate.py --config config/scenario_config.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT))  # so the read-only MMSI conflict check can import the app

from geo import (  # noqa: E402
    Route,
    haversine_km,
    knots_to_km_per_second,
    offset_point,
)
from land_check import LandChecker  # noqa: E402

OUTSIDE_DESTINATIONS = [
    "印度 维沙卡帕特南", "印度 贾姆讷格尔", "中国 宁波舟山", "新加坡",
    "日本 千叶", "韩国 蔚山", "阿曼 苏哈尔", "印度 帕拉迪普",
]
GULF_DESTINATIONS = [
    "沙特 拉斯坦努拉", "阿联酋 杰贝阿里", "卡塔尔 拉斯拉凡", "科威特 舒艾巴",
    "伊拉克 乌姆卡斯尔", "巴林 锡特拉", "阿联酋 富查伊拉", "沙特 朱拜勒",
]
WAITING_AREAS = [
    {"id": "wait_gulf_oman_fujairah", "name_zh": "阿曼湾富查伊拉以东等待区",
     "lat": [25.10, 25.80], "lon": [56.55, 57.10]},
    {"id": "wait_gulf_oman_east", "name_zh": "阿曼湾东部等待区",
     "lat": [25.20, 26.00], "lon": [57.10, 57.95]},
    {"id": "wait_hormuz_west", "name_zh": "海峡以西（穆桑代姆以北）等待区",
     "lat": [26.28, 26.58], "lon": [55.55, 56.30]},
    {"id": "wait_persian_gulf_dubai", "name_zh": "波斯湾迪拜—杰贝阿里外等待区",
     "lat": [25.25, 25.80], "lon": [54.40, 55.25]},
]


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
def parse_utc(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def lognormal_draw(rng: random.Random, mean_seconds: float, sigma: float) -> float:
    """Log-normal sample whose ARITHMETIC mean is mean_seconds."""
    mu = math.log(mean_seconds) - sigma * sigma / 2.0
    return math.exp(rng.gauss(mu, sigma))


def pick_waiting_area(lat: float, lon: float) -> str | None:
    for area in WAITING_AREAS:
        if area["lat"][0] <= lat <= area["lat"][1] and area["lon"][0] <= lon <= area["lon"][1]:
            return area["name_zh"]
    return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 1. identities
# --------------------------------------------------------------------------
def build_ships(cfg: dict, rng: random.Random,
                existing_ships: dict[str, dict] | None = None) -> tuple[list[dict], dict]:
    """Build the batch identities.

    ``existing_ships`` maps an MMSI already present in the database to its stored
    name/callsign. A collision with a DIFFERENT identity is a hard error. A collision
    with an identical identity means this very batch was imported before, which is not
    an identity conflict, so generation continues and the situation is reported.
    """
    spec = cfg["ships"]
    existing_ships = existing_ships or {}
    plan: list[dict] = []
    for entry in spec["type_mix"]:
        plan.extend([entry] * entry["count"])
    rng.shuffle(plan)

    prefix = spec["mmsi_prefix"]
    digits = spec["mmsi_digits"]
    ships: list[dict] = []
    seen_in_db_same = 0
    conflicts: list[dict] = []

    for index, entry in enumerate(plan, start=1):
        mmsi = f"{prefix}{index:0{digits - len(prefix)}d}"
        if len(mmsi) != digits:
            raise ValueError(f"MMSI 长度错误：{mmsi}")
        name = spec["name_template"].format(ship_type_zh=entry["ship_type"], index=index)
        callsign = spec["callsign_template"].format(index=index)

        existing = existing_ships.get(mmsi)
        if existing is not None:
            if existing.get("name") == name and existing.get("callsign") == callsign:
                seen_in_db_same += 1
            else:
                conflicts.append({
                    "mmsi": mmsi,
                    "batch_name": name,
                    "db_name": existing.get("name"),
                    "db_callsign": existing.get("callsign"),
                })

        length_m = rng.uniform(*entry["length_m"])
        ratio = rng.uniform(6.2, 7.6) if length_m > 100 else rng.uniform(2.8, 3.6)
        width_m = clamp(length_m / ratio, entry["width_m"][0], entry["width_m"][1])
        ships.append({
            "temp_ship_id": index,
            "mmsi": mmsi,
            "name": name,
            "ship_type": entry["ship_type"],
            "ais_type": entry["ais_type"],
            "flag": spec["flag_pool"][(index - 1) % len(spec["flag_pool"])],
            "imo": spec["imo"],
            "callsign": callsign,
            "length_m": round(length_m, 1),
            "width_m": round(width_m, 1),
            "draught_m": round(rng.uniform(*entry["draught_m"]), 1),
            "speed_kn_range": entry["speed_kn"],
            "impact_weight": entry["impact_weight"],
        })

    if conflicts:
        raise ValueError(
            f"MMSI 与现有数据库中的其它身份冲突 {len(conflicts)} 条，例如：{conflicts[:3]}"
        )
    if len({s["mmsi"] for s in ships}) != len(ships):
        raise ValueError("批次内 MMSI 不唯一")

    report = {
        "matches_an_existing_row": seen_in_db_same,
        "conflicts": len(conflicts),
        "interpretation_zh": (
            "存在同名同呼号的既有记录，说明本批次很可能此前已导入过；"
            "这不构成身份冲突，本次仅生成文件，不写数据库。"
            if seen_in_db_same else "批次身份在现有数据库中不存在。"
        ),
    }
    return ships, report


def assign_ship_parameters(ships: list[dict], cfg: dict, rng: random.Random) -> None:
    """Assign route plans.

    Transit ships alternate between the two directional routes, so a ship that leaves
    at the Persian Gulf end re-enters at the same end and sails back out again. The
    turnaround happens while the ship is outside the simulated water, which keeps each
    track continuous instead of teleporting from one end of the corridor to the other.
    """
    motion = cfg["motion"]
    tugs = [s for s in ships if s["ship_type"] == "拖轮"]
    transiting = [s for s in ships if s["ship_type"] != "拖轮"]
    rng.shuffle(transiting)

    internal_count = max(len(tugs), int(len(transiting) * 0.25))
    internal = transiting[:internal_count] + tugs
    remaining = transiting[internal_count:]
    half = len(remaining) // 2
    groups = (
        (internal, ["gulf_internal", "gulf_internal_reversed"]),
        (remaining[:half], ["inbound_to_gulf", "outbound_from_gulf"]),
        (remaining[half:], ["outbound_from_gulf", "inbound_to_gulf"]),
    )
    for group, plan in groups:
        for ship in group:
            ship["route_name"] = plan[0]
            ship["route_plan"] = plan
            ship["route_start_km"] = rng.uniform(*motion["route_start_offset_km"])
            ship["lateral_amplitude_km"] = rng.uniform(*motion["lateral_offset_km"])
            ship["lateral_wavelength_km"] = rng.uniform(*motion["lateral_offset_wavelength_km"])
            ship["lateral_phase"] = rng.uniform(0, 2 * math.pi)
            ship["speed_wave_amplitude"] = motion["speed_variation_amplitude"] * rng.uniform(0.4, 1.2)
            ship["speed_wave_period_h"] = rng.uniform(*motion["speed_variation_period_hours"])
            ship["speed_wave_phase"] = rng.uniform(0, 2 * math.pi)
            ship["base_speed_kn"] = rng.uniform(*ship["speed_kn_range"])
            ship["departure_offset_h"] = rng.uniform(*motion["departure_window_hours"])
            ship["turnaround_h"] = rng.uniform(*motion["turnaround_hours"])
            ship["max_voyages"] = 7 if plan[0] != "gulf_internal" else 5


def assign_reaction_parameters(ships: list[dict], cfg: dict, rng: random.Random) -> None:
    model = cfg["reaction_model"]
    for ship in ships:
        ship["unaffected"] = rng.random() < model["unaffected_ship_fraction"]
        ship["response_delay_h"] = min(
            18.0,
            math.exp(
                math.log(model["response_delay_hours_median"])
                + rng.gauss(0, model["response_delay_sigma_log_space"])
            ),
        )
        ship["personality"] = rng.uniform(0.55, 1.25)
        ship["recovery_factor"] = rng.uniform(0.12, 0.66)
        ship["hold_speed_kn"] = rng.uniform(*model["hold_speed_kn"])
        ship["anchor_speed_kn"] = rng.uniform(*model["anchor_speed_kn"])
        ship["slow_factor"] = rng.uniform(*model["slow_speed_factor"])
        ship["clearance_km"] = rng.uniform(*model["lane_clearance_offset_km"])
        ship["clearance_sign"] = 1.0 if rng.random() < 0.5 else -1.0
        ship["tidal_semi_major_m"] = rng.uniform(*model["tidal_sway_semi_major_m"])
        ship["tidal_phase"] = rng.uniform(0, 2 * math.pi)


# --------------------------------------------------------------------------
# 2. scenario / behaviour model
# --------------------------------------------------------------------------
class Scenario:
    def __init__(self, cfg: dict, ships: list[dict], routes: dict[str, Route]):
        self.cfg = cfg
        self.routes = routes
        self.model = cfg["reaction_model"]
        self.window_start = parse_utc(cfg["time_window"]["start_utc"])
        self.window_end = parse_utc(cfg["time_window"]["end_utc"])
        self.phases = [
            {**phase, "start": parse_utc(phase["start_utc"]), "end": parse_utc(phase["end_utc"])}
            for phase in cfg["scenario_phases"]
        ]
        ref = cfg["geography"]["strait_reference_point"]
        self.strait = (ref["lat"], ref["lon"])

    def phase_at(self, moment: datetime) -> dict:
        for phase in self.phases:
            if phase["start"] <= moment < phase["end"]:
                return phase
        return self.phases[-1]

    def score(self, ship: dict, phase: dict, lat: float, lon: float, role: str | None = None) -> float:
        if ship["unaffected"] or phase["impact_scale"] <= 0.0:
            return 0.0
        distance_km = haversine_km((lat, lon), self.strait)
        near, far = self.model["near_strait_km"], self.model["far_from_strait_km"]
        proximity = clamp(1.0 - (distance_km - near) / (far - near), self.model["min_distance_factor"], 1.0)
        role = role or ship["route_name"]
        if role == "outbound_from_gulf":
            direction = self.model["outbound_extra_factor"]
        elif role == "inbound_to_gulf":
            direction = self.model["inbound_extra_factor"]
        else:
            direction = 0.75
        passed = self.model["already_passed_factor"] if lon < self.strait[1] - 0.25 else 1.0
        return (proximity * direction * passed * ship["impact_weight"] * ship["personality"]
                * phase["impact_scale"] * self.model.get("score_gain", 1.0))

    def destination_pool(self, role: str) -> list[str]:
        return OUTSIDE_DESTINATIONS if role == "outbound_from_gulf" else GULF_DESTINATIONS

    def behaviour(self, score: float) -> str:
        thresholds = self.model["behaviour_thresholds"]
        if score >= thresholds["anchor"]:
            return "anchor"
        if score >= thresholds["hold"]:
            return "hold"
        if score >= thresholds["slow"]:
            return "slow"
        return "transit"


# --------------------------------------------------------------------------
# 3. forward simulation with irregular reporting
# --------------------------------------------------------------------------
SAFETY_MARGIN_KM = 0.8


def prepare_land_clamp(land: LandChecker, route: Route, distance_km: float, bearing: float,
                       lateral_km: float) -> tuple[float, float, bool]:
    """Place a point, backing the lateral offset off until it clears the coastline.

    A point is accepted only when it and a small ring around it are water, so that
    the positioning noise added later cannot push a report onto the reference land.
    """
    lat, lon = route.point_at(distance_km)
    if abs(lateral_km) > 1e-9:
        lat, lon = offset_point(lat, lon, bearing, lateral_km)
    if land.is_water_with_margin(lon, lat, SAFETY_MARGIN_KM):
        return lat, lon, False
    for factor in (0.75, 0.5, 0.28, 0.1, 0.0):
        test_lat, test_lon = route.point_at(distance_km)
        if abs(lateral_km * factor) > 1e-9:
            test_lat, test_lon = offset_point(test_lat, test_lon, bearing, lateral_km * factor)
        if land.is_water_with_margin(test_lon, test_lat, SAFETY_MARGIN_KM):
            return test_lat, test_lon, True
    base = route.point_at(distance_km)
    return base[0], base[1], True


def simulate_ship(ship: dict, scenario: Scenario, cfg: dict, land: LandChecker,
                  rng: random.Random) -> tuple[list[dict], dict]:
    plan = ship["route_plan"]
    active_role = plan[0]
    route = scenario.routes[active_role]
    reporting = cfg["reporting"]
    sigma = reporting["sigma_log_space"]
    underway_mean = reporting["underway_mean_interval_seconds"]
    anchored_mean = reporting["anchored_mean_interval_seconds"]
    min_interval = reporting["min_interval_seconds"]
    max_interval = reporting["max_interval_seconds"]
    threshold_kn = reporting["underway_speed_threshold_kn"]

    dt = float(cfg["motion"]["integration_step_seconds"])
    steps = int((scenario.window_end - scenario.window_start).total_seconds() // dt)
    tau = 1800.0
    base_speed = ship["base_speed_kn"]
    wave_period_s = ship["speed_wave_period_h"] * 3600.0
    delay_s = ship["response_delay_h"] * 3600.0

    reports: list[dict] = []
    diagnostics = {"voyages": 0, "off_area_seconds": 0.0, "clamped_reports": 0,
                   "phase_modes": {}, "mode_seconds": defaultdict(float),
                   "off_area_windows": []}

    in_area = False
    next_entry_s = ship["departure_offset_h"] * 3600.0
    off_area_start_s: float | None = 0.0
    distance_km = ship["route_start_km"]
    speed_kn = 0.0
    next_report_s: float | None = None
    voyage_index = 0
    destination = rng.choice(scenario.destination_pool(plan[0]))
    previous_destination = destination
    stale_until_s = -1.0
    generated_intervals: list[float] = []

    mode = "transit"
    pending_phase: dict | None = None
    pending_time_s = 0.0
    last_phase_id: str | None = None
    mode_started_s = 0.0
    last_step_s = 0.0
    closure = cfg.get("closure_policy")
    closure_start = parse_utc(closure["warning_start_utc"]) if closure else None
    closure_decision = None

    for step in range(steps + 1):
        t_s = step * dt
        moment = scenario.window_start + timedelta(seconds=t_s)
        phase = scenario.phase_at(moment)

        if not in_area:
            if t_s >= next_entry_s:
                in_area = True
                voyage_index += 1
                diagnostics["voyages"] += 1
                if off_area_start_s is not None:
                    diagnostics["off_area_windows"].append((off_area_start_s, t_s))
                off_area_start_s = None
                distance_km = 0.0
                # the ship enters the simulated water already making way
                speed_kn = ship["base_speed_kn"]
                next_report_s = t_s + rng.uniform(*reporting["first_report_phase_seconds"])
                active_role = plan[(voyage_index - 1) % len(plan)]
                route = scenario.routes[active_role]
                previous_destination = destination
                destination = rng.choice(scenario.destination_pool(active_role))
                stale_until_s = t_s + rng.uniform(1.5, 6.0) * 3600.0 if rng.random() < 0.35 else -1.0
                last_phase_id = None
                mode = "transit"
                closure_decision = None
            else:
                diagnostics["off_area_seconds"] += dt
                last_step_s = t_s
                continue

        lat_now, lon_now = route.point_at(distance_km)

        if phase["id"] != last_phase_id:
            last_phase_id = phase["id"]
            if phase["impact_scale"] <= 0.0:
                mode = "transit"
                pending_phase = None
                mode_started_s = t_s
            else:
                pending_phase = phase
                pending_time_s = t_s + delay_s
        if pending_phase is not None and t_s >= pending_time_s:
            chosen = scenario.behaviour(scenario.score(ship, pending_phase, lat_now, lon_now, active_role))
            if chosen != mode:
                mode = chosen
                mode_started_s = t_s
            diagnostics["phase_modes"][pending_phase["id"]] = chosen
            pending_phase = None

        # Re-evaluate every integration step, including ships arriving after the warning.
        # No distance discount or background exemption may override this restriction.
        if closure and moment >= closure_start and active_role in ("inbound_to_gulf", "outbound_from_gulf"):
            if closure_decision is None:
                inside = closure["west_lon"] < lon_now < closure["east_lon"]
                closure_decision = "clear" if inside else "wait"
            if closure_decision == "clear" and not (closure["west_lon"] < lon_now < closure["east_lon"]):
                closure_decision = "wait"
            chosen = "hold" if closure_decision == "wait" else "transit"
            if chosen != mode:
                mode_started_s = t_s
            mode = chosen
            pending_phase = None
            diagnostics["phase_modes"][phase["id"]] = mode
        elif closure and active_role.startswith("gulf_internal"):
            mode = "transit"
            pending_phase = None
            diagnostics["phase_modes"][phase["id"]] = mode

        effective_mode = mode

        wave = 1.0 + ship["speed_wave_amplitude"] * math.sin(
            2 * math.pi * t_s / wave_period_s + ship["speed_wave_phase"]
        )
        if effective_mode == "transit":
            target_speed = base_speed * wave
        elif effective_mode == "slow":
            target_speed = base_speed * ship["slow_factor"] * wave
        elif effective_mode == "hold":
            target_speed = 0.0 if closure else ship["hold_speed_kn"]
        else:
            target_speed = ship["anchor_speed_kn"]

        speed_kn += (target_speed - speed_kn) * min(1.0, dt / tau)
        speed_kn = max(0.0, speed_kn)
        distance_km += knots_to_km_per_second(speed_kn) * dt
        diagnostics["mode_seconds"][effective_mode] += dt

        if distance_km >= route.length_km:
            in_area = False
            next_report_s = None
            mode = "transit"
            last_phase_id = None
            diagnostics["off_area_seconds"] += dt
            off_area_start_s = t_s
            next_entry_s = t_s + ship["turnaround_h"] * 3600.0
            if diagnostics["voyages"] >= ship["max_voyages"]:
                next_entry_s = float("inf")
            last_step_s = t_s
            continue

        while next_report_s is not None and next_report_s <= t_s:
            report_time_s = float(round(next_report_s))
            state = "underway" if speed_kn > threshold_kn else "anchored"
            bearing = route.bearing_at(distance_km)
            lateral = ship["lateral_amplitude_km"] * math.sin(
                2 * math.pi * distance_km / ship["lateral_wavelength_km"] + ship["lateral_phase"]
            )
            if effective_mode in ("hold", "anchor") and report_time_s >= mode_started_s:
                ramp = min(1.0, (report_time_s - mode_started_s) / (3 * 3600.0))
                lateral += ship["clearance_km"] * ship["clearance_sign"] * ramp

            lat, lon, clamped = prepare_land_clamp(land, route, distance_km, bearing, lateral)

            if effective_mode in ("hold", "anchor"):
                angular = 2 * math.pi / (12.42 * 3600.0)
                phase_angle = angular * report_time_s + ship["tidal_phase"]
                swing_km = ship["tidal_semi_major_m"] / 1000.0
                lat, lon = offset_point(lat, lon, 0.0 if closure else (report_time_s / 60.0) % 360.0,
                                        swing_km * math.sin(phase_angle))
                lat, lon = offset_point(lat, lon, 90.0 if closure else ((report_time_s / 90.0) + 123.0) % 360.0,
                                        0.55 * swing_km * math.cos(phase_angle))
                if land.is_land(lon, lat) or not land.is_water_with_margin(lon, lat, SAFETY_MARGIN_KM):
                    lat, lon, _ = prepare_land_clamp(land, route, distance_km, bearing, lateral)

            if clamped:
                diagnostics["clamped_reports"] += 1

            reported_destination = previous_destination if report_time_s < stale_until_s else destination
            nav_status = "在航" if state == "underway" else ("漂航" if speed_kn > 0.15 else "锚泊")
            if closure and effective_mode == "hold" and state != "underway":
                nav_status = "漂航"
            if state == "underway" and rng.random() < 0.05:
                nav_status = "操纵受限"

            reports.append({
                "temp_ship_id": ship["temp_ship_id"],
                "record_time_s": report_time_s,
                "recorded_at": scenario.window_start + timedelta(seconds=report_time_s),
                "true_latitude": lat,
                "true_longitude": lon,
                "true_speed_kn": speed_kn,
                "true_course": bearing,
                "state": state,
                "mode": effective_mode,
                "nav_status": nav_status,
                "destination": reported_destination,
                "destination_stale": report_time_s < stale_until_s,
                "waiting_area": pick_waiting_area(lat, lon),
                "voyage_index": voyage_index,
                "active_role": active_role,
                "clamped": clamped,
            })

            interval = lognormal_draw(
                rng, underway_mean if state == "underway" else anchored_mean, sigma
            )
            if min_interval is not None:
                interval = max(interval, float(min_interval))
            if max_interval is not None:
                interval = min(interval, float(max_interval))
            generated_intervals.append((state, interval))
            next_report_s = report_time_s + interval

        last_step_s = t_s

    diagnostics["generated_intervals"] = generated_intervals
    diagnostics["final_isolation"] = mode if in_area else None
    return reports, diagnostics


# --------------------------------------------------------------------------
# 4. anomaly injection
# --------------------------------------------------------------------------
def inject_anomalies(reports: list[dict], cfg: dict, rng: random.Random) -> tuple[list[dict], dict]:
    spec = cfg["anomalies"]
    labels: dict = {"enabled": bool(spec["enabled"]), "by_type": {}, "blackout_windows": [],
                    "position_jump_records": [], "duplicate_records": [], "field_missing_records": []}
    if not spec["enabled"]:
        return [dict(r) for r in reports], labels

    by_ship: dict[int, list[int]] = defaultdict(list)
    for index, report in enumerate(reports):
        by_ship[report["temp_ship_id"]].append(index)

    dropped: set[int] = set()
    dropout_count = 0
    for index in range(len(reports)):
        if rng.random() < spec["dropout_probability"]:
            dropped.add(index)
            dropout_count += 1

    ship_ids = sorted(by_ship)
    blackout_ships = rng.sample(ship_ids, k=max(1, int(round(len(ship_ids) * spec["blackout_ship_fraction"]))))
    blackout_suppressed = 0
    for ship_id in blackout_ships:
        indices = by_ship[ship_id]
        if len(indices) < 4:
            continue
        hours = rng.uniform(*spec["blackout_hours"])
        start_index = indices[int(len(indices) * rng.uniform(0.15, 0.7))]
        start = reports[start_index]["recorded_at"]
        end = start + timedelta(hours=hours)
        suppressed = 0
        for index in indices:
            if index in dropped:
                continue
            if start <= reports[index]["recorded_at"] < end:
                dropped.add(index)
                suppressed += 1
        blackout_suppressed += suppressed
        labels["blackout_windows"].append({
            "temp_ship_id": ship_id,
            "start_utc": iso_utc(start),
            "end_utc": iso_utc(end),
            "hours": round(hours, 2),
            "suppressed_reports": suppressed,
        })

    kept = [dict(r) for index, r in enumerate(reports) if index not in dropped]

    noise_std = spec["position_noise_std_deg"]
    duplicates = 0
    heading_missing = 0
    destination_stale = 0
    jumps = 0
    raw: list[dict] = []

    for report in kept:
        latitude = report["true_latitude"] + rng.gauss(0, noise_std)
        longitude = report["true_longitude"] + rng.gauss(0, noise_std)
        speed = max(0.0, report["true_speed_kn"] + rng.gauss(0, spec["speed_noise_kn"] * 0.5))
        course = (report["true_course"] + rng.gauss(0, spec["course_noise_deg"] * 0.5)) % 360.0
        heading = (course + rng.gauss(0, 4.0)) % 360.0

        anomalies: list[str] = []
        if rng.random() < spec["heading_missing_probability"]:
            heading = None
            anomalies.append("heading_missing")
            heading_missing += 1
        if report["destination_stale"]:
            anomalies.append("destination_stale")
            destination_stale += 1

        if rng.random() < spec["position_jump_probability"]:
            magnitude = rng.uniform(*spec["position_jump_km"])
            jump_lat, jump_lon = offset_point(latitude, longitude, rng.uniform(0, 360), magnitude)
            latitude, longitude = jump_lat, jump_lon
            anomalies.append("position_jump")
            jumps += 1
            labels["position_jump_records"].append({
                "temp_ship_id": report["temp_ship_id"],
                "recorded_at": iso_utc(report["recorded_at"]),
                "offset_km": round(magnitude, 2),
            })

        item = {
            "temp_ship_id": report["temp_ship_id"],
            "latitude": round(latitude, 6),
            "longitude": round(longitude, 6),
            "speed": round(speed, 2),
            "course": round(course, 2),
            "heading": None if heading is None else round(heading, 2),
            "recorded_at": report["recorded_at"],
            "unix_time": int(report["recorded_at"].timestamp()),
            "nav_status": report["nav_status"],
            "rot": None,
            "draught_m": report["draught_m"],
            "destination": report["destination"],
            "ais_type": report["ais_type"],
            "data_source": cfg["data_source_value"],
            "_true_lat": report["true_latitude"],
            "_true_lon": report["true_longitude"],
            "_true_speed": round(report["true_speed_kn"], 4),
            "_true_course": round(report["true_course"], 4),
            "_state": report["state"],
            "_mode": report["mode"],
            "_voyage": report["voyage_index"],
            "_waiting_area": report["waiting_area"],
            "_anomalies": anomalies,
        }
        raw.append(item)

        if rng.random() < spec["duplicate_probability"]:
            clone = dict(item)
            clone["_anomalies"] = list(anomalies) + ["duplicate"]
            raw.append(clone)
            duplicates += 1
            labels["duplicate_records"].append({
                "temp_ship_id": item["temp_ship_id"],
                "recorded_at": iso_utc(item["recorded_at"]),
            })

    out_of_order = 0
    for item in raw:
        delay = rng.uniform(1.0, 90.0)
        if rng.random() < spec["out_of_order_probability"]:
            delay += rng.uniform(240.0, 3600.0)
            item["_anomalies"].append("out_of_order")
            out_of_order += 1
        item["received_at"] = item["recorded_at"] + timedelta(seconds=delay)

    raw.sort(key=lambda r: (r["received_at"], r["temp_ship_id"]))
    for sequence, item in enumerate(raw):
        item["arrival_seq"] = sequence

    labels["by_type"] = {
        "dropout_random": {"unit": "report", "injected": dropout_count,
                           "note_zh": "按固定概率逐一丢弃基础报位，不重新排布剩余时间。"},
        "blackout": {"unit": "window", "injected": len(labels["blackout_windows"]),
                     "suppressed_reports": blackout_suppressed,
                     "note_zh": "受影响船在 1-4 小时内全部报位丢失。"},
        "duplicate": {"unit": "report", "injected": duplicates,
                      "note_zh": "字段与 recorded_at 完全相同的重复报文。"},
        "out_of_order": {"unit": "report", "injected": out_of_order,
                         "note_zh": "接收时间被额外延迟，原始文件按到达顺序排列，记录时间非单调。"},
        "position_jump": {"unit": "report", "injected": jumps,
                          "note_zh": "孤立位置跳点，瞬时偏移 30-120 km，不影响相邻真实船位。"},
        "position_noise": {"unit": "report", "sigma_deg": noise_std,
                           "note_zh": "叠加到全部原始报位的高斯定位噪声。"},
        "speed_noise": {"unit": "report", "sigma_kn_half": spec["speed_noise_kn"] * 0.5},
        "course_noise": {"unit": "report", "sigma_deg_half": spec["course_noise_deg"] * 0.5},
        "heading_missing": {"unit": "report", "injected": heading_missing,
                            "note_zh": "航首向字段偶发缺失，course 不受影响。"},
        "destination_stale": {"unit": "report", "injected": destination_stale,
                              "note_zh": "航次切换后目的地字段短暂滞后于上一航次。"},
    }
    labels["clean_report_total"] = len(reports)
    labels["raw_record_total"] = len(raw)
    return raw, labels


# --------------------------------------------------------------------------
# 5. cleaning
# --------------------------------------------------------------------------
def _implied_speed_kn(a: dict, b: dict) -> float | None:
    seconds = (b["recorded_at"] - a["recorded_at"]).total_seconds()
    if seconds <= 0:
        return None
    distance = haversine_km((a["latitude"], a["longitude"]), (b["latitude"], b["longitude"]))
    return distance / (seconds / 3600.0) / 1.852


def clean_records(raw: list[dict], cfg: dict) -> tuple[list[dict], list[dict], dict]:
    """Deduplicate, quarantine isolated position spikes, sort by ship and time.

    Two independent, hidden-truth-free rules are used. Neither rule knows which
    records were injected, so the labels file is only used afterwards for scoring:

    1. interpolation spike test - a point far from the straight line between its
       time-interpolated neighbours is a spike regardless of how long the gap is;
    2. implied-speed cap - the implied speed between consecutive points must stay
       below max(absolute_min_kn, ratio * the ship's own median implied speed).
    """
    cleaning = cfg["cleaning"]
    speed_ratio = cleaning.get("quarantine_speed_ratio", 1.6)
    speed_margin = cleaning.get("quarantine_speed_margin_kn", 4.0)
    speed_floor = cleaning.get("quarantine_speed_floor_kn", 6.0)
    spike_slope = cleaning.get("quarantine_spike_km_per_minute", 0.22)
    spike_min_km = cleaning.get("quarantine_spike_min_km", 3.0)
    spike_max_km = cleaning.get("quarantine_spike_max_km", 25.0)
    spike_max_span_min = cleaning.get("quarantine_spike_max_span_minutes", 240.0)

    seen: set[tuple] = set()
    deduped: list[dict] = []
    duplicates_removed = 0
    for item in raw:
        key = (item["temp_ship_id"], item["recorded_at"], item["latitude"], item["longitude"])
        if key in seen:
            duplicates_removed += 1
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda r: (r["temp_ship_id"], r["recorded_at"], r["arrival_seq"]))

    by_ship: dict[int, list[dict]] = defaultdict(list)
    for item in deduped:
        by_ship[item["temp_ship_id"]].append(item)

    quarantined: list[dict] = []
    clean: list[dict] = []
    true_positives = false_positives = 0
    spike_hits = speed_hits = 0

    for ship_id, rows in by_ship.items():
        remaining = list(rows)

        def pair_limit(a: dict, b: dict) -> float:
            """How fast the ship could plausibly have closed the gap between two reports.

            Uses the two reported speeds of the pair rather than a global constant, so a
            drifting ship is judged against drifting speeds and a 20-knot ship against
            20-knot speeds. Reported speeds carry their own noise, hence ratio + margin.
            """
            return max(speed_ratio * max(a["speed"], b["speed"]) + speed_margin, speed_floor)

        # Remove the single worst violation at a time. Deleting every flagged point in
        # one sweep would also delete the innocent neighbours of a spike, because those
        # neighbours look wrong too until the spike itself has been removed.
        while True:
            worst_index = None
            worst_score = 1.0
            worst_kind = None
            for index in range(len(remaining)):
                item = remaining[index]
                if index > 0:
                    previous_item = remaining[index - 1]
                    implied = _implied_speed_kn(previous_item, item)
                    if implied is not None:
                        limit = pair_limit(previous_item, item)
                        if implied > limit:
                            score = implied / limit
                            if score > worst_score:
                                worst_index, worst_score, worst_kind = index, score, "implied_speed"
                elif index + 1 < len(remaining):
                    # a ship's very first report has no earlier neighbour, so it would
                    # otherwise escape every neighbour-based rule
                    next_item = remaining[index + 1]
                    implied = _implied_speed_kn(item, next_item)
                    if implied is not None:
                        limit = pair_limit(item, next_item)
                        if implied > limit:
                            score = implied / limit
                            if score > worst_score:
                                worst_index, worst_score, worst_kind = index, score, "implied_speed"
                if 0 < index < len(remaining) - 1:
                    previous, following = remaining[index - 1], remaining[index + 1]
                    span = (following["recorded_at"] - previous["recorded_at"]).total_seconds()
                    if 0 < span <= spike_max_span_min * 60:
                        weight = (item["recorded_at"] - previous["recorded_at"]).total_seconds() / span
                        if 0.0 < weight < 1.0:
                            predicted_lat = previous["latitude"] + (following["latitude"] - previous["latitude"]) * weight
                            predicted_lon = previous["longitude"] + (following["longitude"] - previous["longitude"]) * weight
                            deviation = haversine_km(
                                (predicted_lat, predicted_lon), (item["latitude"], item["longitude"])
                            )
                            allowed = min(spike_max_km, max(spike_min_km, spike_slope * span / 60.0))
                            if deviation > allowed:
                                score = deviation / allowed
                                if score > worst_score:
                                    worst_index, worst_score, worst_kind = index, score, "interpolation_spike"
            if worst_index is None:
                break
            item = remaining.pop(worst_index)
            positive = "position_jump" in item["_anomalies"]
            if positive:
                true_positives += 1
            else:
                false_positives += 1
            if worst_kind == "interpolation_spike":
                spike_hits += 1
            else:
                speed_hits += 1
            quarantined.append({
                "reason": worst_kind,
                "violation_ratio": round(worst_score, 3),
                "injected_position_jump": positive,
                "record": {
                    k: (iso_utc(v) if isinstance(v, datetime) else v)
                    for k, v in item.items() if not k.startswith("_")
                },
            })

        remaining.sort(key=lambda r: (r["recorded_at"], r["arrival_seq"]))
        clean.extend(remaining)

    clean.sort(key=lambda r: (r["temp_ship_id"], r["recorded_at"], r["arrival_seq"]))

    stats = {
        "input_records": len(raw),
        "duplicates_removed": duplicates_removed,
        "quarantined_records": len(quarantined),
        "quarantine_true_positives": true_positives,
        "quarantine_false_positives": false_positives,
        "spike_rule_first_round_hits": spike_hits,
        "speed_rule_first_round_hits": speed_hits,
        "rule_speed_zh": (
            f"相邻报文推算航速 > max({speed_ratio} × 两条报文自身航速较大者 + "
            f"{speed_margin} 节, {speed_floor} 节)"
        ),
        "rule_spike_zh": (
            f"某点距前后两点按时间插值位置的偏差 > min({spike_max_km} km, "
            f"max({spike_min_km} km, {spike_slope} km/min × 前后时间跨度))；"
            f"前后跨度 > {spike_max_span_min} 分钟时不判定"
        ),
        "note_zh": "两条规则都不使用注入记录；注入标签只用于事后统计命中率。",
    }
    return clean, quarantined, stats


# --------------------------------------------------------------------------
# 6. export
# --------------------------------------------------------------------------
PUBLIC_POSITION_FIELDS = [
    "temp_ship_id", "latitude", "longitude", "speed", "course", "heading",
    "recorded_at", "unix_time", "nav_status", "rot", "draught_m", "destination",
    "ais_type", "data_source",
]
PUBLIC_SHIP_FIELDS = [
    "temp_ship_id", "mmsi", "name", "ship_type", "flag", "imo", "callsign",
    "length_m", "width_m",
]


def position_row(item: dict) -> dict:
    row = {}
    for field in PUBLIC_POSITION_FIELDS:
        value = item[field]
        row[field] = iso_utc(value) if isinstance(value, datetime) else value
    return row


def raw_row(item: dict) -> dict:
    row = position_row(item)
    row["received_at"] = iso_utc(item["received_at"])
    row["arrival_seq"] = item["arrival_seq"]
    return row


def write_jsonl(path: Path, rows) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count, path.stat().st_size


# --------------------------------------------------------------------------
# 7. driver
# --------------------------------------------------------------------------
def generate_batch(cfg: dict, seed: int, outdir: Path, land: LandChecker,
                   land_stats: dict, reserved_mmsi: set[str] | None = None,
                   reserved_reason: str | None = None) -> dict:
    rng = random.Random(seed)
    reserved_mmsi = reserved_mmsi or set()
    window_start = parse_utc(cfg["time_window"]["start_utc"])
    window_end = parse_utc(cfg["time_window"]["end_utc"])

    ships, identity_report = build_ships(cfg, rng, reserved_mmsi)
    assign_ship_parameters(ships, cfg, rng)
    assign_reaction_parameters(ships, cfg, rng)
    routes = {name: Route([tuple(p) for p in spec["waypoints_lat_lon"]])
              for name, spec in cfg["geography"]["routes"].items()}
    # a reversed variant lets Gulf-internal ships shuttle without leaving the area
    routes["gulf_internal_reversed"] = Route(list(reversed(routes["gulf_internal"].points)))
    scenario = Scenario(cfg, ships, routes)

    # --- route validation happens before any motion so failures are explicit ---
    route_reports = {}
    for name, route in routes.items():
        report = land.check_route(route.points, sample_km=0.2)
        route_reports[name] = report

    all_reports: list[dict] = []
    diagnostics_by_ship: dict[int, dict] = {}
    for ship in ships:
        reports, diagnostics = simulate_ship(ship, scenario, cfg, land, rng)
        for report in reports:
            report["draught_m"] = ship["draught_m"]
            report["ais_type"] = ship["ais_type"]
        all_reports.extend(reports)
        diagnostics_by_ship[ship["temp_ship_id"]] = diagnostics
        ship["voyage_count"] = diagnostics["voyages"]
        ship["behaviour_by_phase"] = diagnostics["phase_modes"]
        ship["position_count"] = len(reports)

    all_reports.sort(key=lambda r: (r["temp_ship_id"], r["record_time_s"]))

    raw, labels = inject_anomalies(all_reports, cfg, rng)
    clean, quarantined, cleaning_stats = clean_records(raw, cfg)

    # out-of-area gaps are a scenario feature, not an anomaly: record them so that
    # long gaps can be attributed instead of being mistaken for signal loss.
    out_of_area = []
    for ship in ships:
        for start_s, end_s in diagnostics_by_ship[ship["temp_ship_id"]]["off_area_windows"]:
            if end_s - start_s < 1800:
                continue
            out_of_area.append({
                "temp_ship_id": ship["temp_ship_id"],
                "start_utc": iso_utc(window_start + timedelta(seconds=start_s)),
                "end_utc": iso_utc(window_start + timedelta(seconds=end_s)),
                "hours": round((end_s - start_s) / 3600.0, 2),
                "meaning_zh": "该船在此期间已驶离模拟水域（非信号丢失）。",
            })
    labels["scenario_features"] = {
        "out_of_area_windows": out_of_area,
        "out_of_area_note_zh": (
            "船舶驶出模拟水域后不再产生报位，随后重新进入。这是情景允许的进出区域行为，"
            "不是注入的异常；判断长间隔原因时请先对照此表。"
        ),
    }

    # ---- write files ----
    outdir.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    counts: dict[str, int] = {}

    ships_path = outdir / "ships.jsonl"
    counts["ships"], _ = write_jsonl(
        ships_path, ({k: ship[k] for k in PUBLIC_SHIP_FIELDS} for ship in ships)
    )
    files["ships.jsonl"] = sha256_text(ships_path.read_text(encoding="utf-8"))

    positions_dir = outdir / cfg["output"]["positions_subdir"]
    raw_dir = outdir / cfg["output"]["raw_subdir"]
    quarantine_dir = outdir / cfg["output"]["quarantine_subdir"]

    by_date_clean: dict[str, list[dict]] = defaultdict(list)
    for item in clean:
        key = item["recorded_at"].astimezone(timezone.utc).strftime("%Y-%m-%d")
        by_date_clean[key].append(item)
    by_date_raw: dict[str, list[dict]] = defaultdict(list)
    for item in raw:
        key = item["recorded_at"].astimezone(timezone.utc).strftime("%Y-%m-%d")
        by_date_raw[key].append(item)

    daily_counts = {}
    for date_key in sorted(by_date_clean):
        rows = sorted(by_date_clean[date_key], key=lambda r: (r["temp_ship_id"], r["recorded_at"]))
        path = positions_dir / f"positions_{date_key}.jsonl"
        counts[f"positions_{date_key}"], _ = write_jsonl(path, (position_row(r) for r in rows))
        files[path.name] = sha256_text(path.read_text(encoding="utf-8"))
        daily_counts[date_key] = counts[f"positions_{date_key}"]

    raw_daily_counts = {}
    for date_key in sorted(by_date_raw):
        rows = sorted(by_date_raw[date_key], key=lambda r: r["arrival_seq"])
        path = raw_dir / f"raw_{date_key}.jsonl"
        counts[f"raw_{date_key}"], _ = write_jsonl(path, (raw_row(r) for r in rows))
        files[path.name] = sha256_text(path.read_text(encoding="utf-8"))
        raw_daily_counts[date_key] = counts[f"raw_{date_key}"]

    if quarantined:
        path = quarantine_dir / "quarantined_records.jsonl"
        counts["quarantined"], _ = write_jsonl(path, (q for q in quarantined))
        files[path.name] = sha256_text(path.read_text(encoding="utf-8"))

    labels_path = outdir / "anomaly_labels.json"
    labels_path.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files["anomaly_labels.json"] = sha256_text(labels_path.read_text(encoding="utf-8"))

    # ---- scenario links (news basis vs simulation assumptions) ----
    observed_phases = observe_phase_behaviour(clean, cfg)
    scenario_links = build_scenario_links(cfg, ships, observed_phases, seed, cleaning_stats,
                                          diagnostics_by_ship, route_reports)
    if cfg.get("closure_policy"):
        scenario_links["closure_policy"] = cfg["closure_policy"]
        # Replace legacy narrative about partial reopening; keep source event records.
        for phase in scenario_links["phases"]:
            phase["simulation_assumptions_zh"] = [next(p["traffic_intent_zh"] for p in cfg["scenario_phases"] if p["id"] == phase["id"])]
        for value in scenario_links.values():
            if isinstance(value, dict) and "simulated_assumptions_zh" in value:
                value["simulated_assumptions_zh"] = cfg["closure_policy"]["assumptions_zh"]
            if isinstance(value, dict) and "recovery_mode_zh" in value:
                value["recovery_mode_zh"] = "本批次不设复航。禁行响应逐步积分检查，两侧待命，内部先驶离；湾内支线继续。"
    links_path = outdir / "scenario_links.json"
    links_path.write_text(json.dumps(scenario_links, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files["scenario_links.json"] = sha256_text(links_path.read_text(encoding="utf-8"))

    model_stats = build_model_stats(cfg, ships, diagnostics_by_ship, labels, cleaning_stats,
                                    reserved_mmsi, reserved_reason, identity_report)
    digest = sha256_text(json.dumps(files, sort_keys=True))

    manifest = {
        "batch_id": cfg["batch_id"],
        "config_version": cfg["config_version"],
        "random_seed": seed,
        "data_source_value": cfg["data_source_value"],
        "time_window": {"start_utc": iso_utc(window_start), "end_utc": iso_utc(window_end),
                        "days": cfg["time_window"]["days"]},
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "deterministic_payload_sha256": digest,
        "deterministic_payload_note_zh": "该摘要只覆盖数据文件（ships/positions/raw/quarantine/anomaly_labels/scenario_links），用于同种子同配置的重复性验证；manifest.json 与 acceptance_report.json 含生成时间，不参与该摘要。",
        "ship_count": len(ships),
        "clean_position_count": len(clean),
        "raw_position_count": len(raw),
        "quarantined_record_count": len(quarantined),
        "daily_clean_counts": daily_counts,
        "daily_raw_counts": raw_daily_counts,
        "route_validation": {
            name: {
                "length_km": rep["length_km"],
                "samples": rep["samples"],
                "land_samples": rep["land_samples"],
                "clean": rep["clean"],
            } for name, rep in route_reports.items()
        },
        "land_reference": {
            "file": "reference/ne_10m_land.geojson",
            "dataset": "Natural Earth 1:10m Physical Vectors - Land (public domain)",
            "sha256": "1ac90796408bc6ad6911d69448485d3c4dbf2190370080368a09976e1c9f7416",
            "precision_note_zh": "1:10m 制图概化数据，近岸精度约数百米至 1 km，缺失防波堤、填海区与极小岛礁。仅用于筛查航线是否明显穿越陆地，不构成航道级安全验证。",
            "edge_index": land_stats,
        },
        "route_definition_note_zh": cfg["geography"]["source_note_zh"],
        "playback_note_zh": "船位按 UTC 自然日分片；每片不超过 24 小时，用于满足回放接口的单次 24 小时 / 50,000 点限制。",
        "files": files,
    }

    manifest_path = outdir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ---- independent acceptance pass over the written files ----
    import acceptance  # noqa: PLC0415
    acceptance_report = acceptance.run_acceptance(
        outdir, cfg, model_stats=model_stats,
        news_snapshot_available=bool(load_news_snapshot()),
    )
    acceptance_path = outdir / "acceptance_report.json"
    acceptance_path.write_text(
        json.dumps(acceptance_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "combined_sha256": digest,
        "files": files,
        "outdir": str(outdir),
        "ships": ships,
        "clean": clean,
        "raw": raw,
        "quarantined": quarantined,
        "labels": labels,
        "cleaning_stats": cleaning_stats,
        "diagnostics_by_ship": diagnostics_by_ship,
        "routes": routes,
        "route_reports": route_reports,
        "scenario": scenario,
        "manifest": manifest,
        "scenario_links": scenario_links,
        "acceptance_report": acceptance_report,
        "model_stats": model_stats,
    }


def observe_phase_behaviour(clean: list[dict], cfg: dict) -> dict:
    """Observed mean speed and anchor share per scenario phase, from the clean records."""
    phases = [
        {**phase, "start": parse_utc(phase["start_utc"]), "end": parse_utc(phase["end_utc"])}
        for phase in cfg["scenario_phases"]
    ]
    result: dict[str, dict] = {}
    for phase in phases:
        speeds: list[float] = []
        anchored = 0
        ships = set()
        for item in clean:
            moment = item["recorded_at"]
            if not (phase["start"] <= moment < phase["end"]):
                continue
            speeds.append(item["_true_speed"])
            if item["_state"] == "anchored":
                anchored += 1
            ships.add(item["temp_ship_id"])
        ordered = sorted(speeds)
        result[phase["id"]] = {
            "reports": len(speeds),
            "distinct_ships": len(ships),
            "mean_speed_kn": round(sum(speeds) / len(speeds), 2) if speeds else None,
            "median_speed_kn": round(ordered[len(ordered) // 2], 2) if ordered else None,
            "anchored_report_share": round(anchored / len(speeds), 4) if speeds else None,
        }
    return result


def load_news_snapshot() -> dict | None:
    path = ROOT / "reference" / "news_snapshot.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


PHASE_ASSUMPTIONS = {
    "P0_pre_incident": [
        "“通航正常”是本情景的基线设定，用于与后续阶段对比；新闻只说明局势紧张，没有给出当日具体通行量。",
    ],
    "P1_onset": [
        "“海峡附近部分船舶提前减速”是教学假设，用于表现影响开始出现；新闻没有给出逐船航速。",
        "减速幅度 0.72 倍、锚泊倾向系数 0.35 均为模拟参数。",
    ],
    "P2_peak": [
        "“大量等待与锚泊、通行量显著下降”是对新闻描述（数百艘船滞留、航运近乎停摆）的模拟表达，具体船舶数量与位置为模拟值。",
        "减速幅度 0.32 倍、锚泊倾向系数 1.0 均为模拟参数。",
        "本批次没有模拟袭击、爆炸、沉船或人员伤亡；新闻提到的涉事船名不出现在模拟船队中。",
    ],
    "P3_simulated_partial_recovery": [
        "该阶段没有新闻报道支持，完全是为教学补充的假设情景。",
        "“部分滞留船恢复航行、通行量回升但低于事发前”是模拟假设，不是已报道事实。",
        "时间上限取新闻 evt_049 所述的战争险撤保伦敦生效时刻（2026-03-05T00:00Z），仅作为窗口终点锚点。",
    ],
}


def build_scenario_links(cfg, ships, observed_phases, seed, cleaning_stats,
                         diagnostics_by_ship, route_reports) -> dict:
    snapshot = load_news_snapshot() or {}
    events_by_id = {item["event_id"]: item for item in snapshot.get("events", [])}
    ref = cfg["geography"]["strait_reference_point"]

    event_links = []
    for phase in cfg["scenario_phases"]:
        for biz_id in phase["news_refs"]:
            event = events_by_id.get(biz_id)
            if event is None:
                event_links.append({
                    "biz_event_id": biz_id,
                    "snapshot_available": False,
                    "scenario_phase_ids": [phase["id"]],
                    "note_zh": "快照中没有该业务事件编号，生成阶段无法引用其内容。",
                })
                continue
            linked_news = event.get("linked_news", [])
            event_links.append({
                "biz_event_id": event["event_id"],
                "db_numeric_id": event.get("id"),
                "title_zh": event.get("title_zh"),
                "event_type": event.get("event_type"),
                "event_datetime": event.get("event_datetime"),
                "event_time_text": event.get("event_time_text"),
                "event_time_precision_zh": (
                    "event_datetime 可取值为日期级占位（00:00:00Z），不代表核实的精确发生时刻；"
                    "以 event_time_text 的原始文字为准。"
                ),
                "event_location_text": event.get("event_location_text"),
                "event_region": event.get("event_region"),
                "representative_point": {
                    "lat": event.get("event_lat"),
                    "lng": event.get("event_lng"),
                    "geo_method": event.get("geo_method"),
                    "note_zh": "代表点由地理编码或区域质心得到，不等于核实的精确事发坐标。",
                },
                "mentioned_vessels": event.get("mentioned_vessels") or [],
                "mentioned_vessels_note_zh": (
                    "只是报道中提到的船名。本批次模拟船队与这些真实船舶不存在任何关联，"
                    "也没有把提到船名的事件当作涉事船的航行记录。"
                ),
                "publish_date_min": event.get("publish_date_min"),
                "publish_date_max": event.get("publish_date_max"),
                "coverage_count": event.get("coverage_count"),
                "linked_news_count": len(linked_news),
                "linked_story_ids": [n.get("story_id") for n in linked_news],
                "linked_news_sample": [
                    {
                        "story_id": n.get("story_id"),
                        "publish_date": n.get("publish_date"),
                        "media_name": n.get("media_name"),
                        "perspective": n.get("perspective"),
                        "canonical_url": n.get("canonical_url"),
                    }
                    for n in linked_news[:5]
                ],
                "scenario_phase_ids": [phase["id"]],
                "used_as_zh": phase["traffic_intent_zh"],
            })

    phases = []
    for phase in cfg["scenario_phases"]:
        phases.append({
            "id": phase["id"],
            "label_zh": phase["label_zh"],
            "start_utc": phase["start_utc"],
            "end_utc": phase["end_utc"],
            "evidence": phase["evidence"],
            "basis_biz_event_ids": phase["news_refs"],
            "traffic_intent_zh": phase["traffic_intent_zh"],
            "speed_multiplier": phase["speed_multiplier"],
            "speed_multiplier_kind": "simulation_assumption",
            "impact_scale": phase["impact_scale"],
            "observed_in_generated_data": observed_phases.get(phase["id"], {}),
            "simulation_assumptions_zh": PHASE_ASSUMPTIONS.get(phase["id"], []),
        })

    participating = []
    for ship in ships:
        modes = diagnostics_by_ship[ship["temp_ship_id"]]["phase_modes"]
        participating.append({
            "temp_ship_id": ship["temp_ship_id"],
            "mmsi": ship["mmsi"],
            "name": ship["name"],
            "ship_type": ship["ship_type"],
            "route": ship["route_name"],
            "unaffected_background_ship": ship["unaffected"],
            "impact_weight": ship["impact_weight"],
            "response_delay_hours": round(ship["response_delay_h"],
                                          2) if not ship["unaffected"] else None,
            "recovery_factor": round(ship["recovery_factor"], 2) if not ship["unaffected"] else None,
            "behaviour_by_phase": modes,
            "voyage_count": ship["voyage_count"],
            "position_count": ship["position_count"],
        })

    unaffected_count = sum(1 for s in ships if s["unaffected"])
    anchored_like = sum(
        1 for s in participating
        if "anchor" in s["behaviour_by_phase"].values() or "hold" in s["behaviour_by_phase"].values()
    )

    return {
        "batch_id": cfg["batch_id"],
        "random_seed": seed,
        "data_source": cfg["data_source_value"],
        "purpose_zh": "教学演示用的模拟船舶 AIS 报位数据。不是实际接收的 AIS，也不是新闻所涉真实船舶的历史轨迹。",
        "news_snapshot": {
            "file": "reference/news_snapshot.json",
            "available": bool(snapshot),
            "exported_at_utc": snapshot.get("exported_at_utc"),
            "source": snapshot.get("source"),
            "access": snapshot.get("access"),
            "event_count": len(snapshot.get("events", [])),
            "linked_news_total": snapshot.get("linked_news_total"),
            "notes_zh": snapshot.get("notes_zh", []),
        },
        "id_semantics_zh": [
            "news.event_id 是指向 events.id 的数值外键；events.event_id 是业务字符串编号（evt_xxx）。两者不可混用。",
            "publish_date 是报道日期，不等于事件发生时间。",
            "event_datetime 可为空；为空时不回填虚构的精确发生时间。",
            "区域代表点不等于精确事发坐标。",
        ],
        "time_window_utc": [cfg["time_window"]["start_utc"], cfg["time_window"]["end_utc"]],
        "window_rationale_zh": cfg["time_window"]["rationale_zh"],
        "phases": phases,
        "event_links": event_links,
        "impact_zone": {
            "reference_point": ref,
            "near_strait_km": cfg["reaction_model"]["near_strait_km"],
            "far_from_strait_km": cfg["reaction_model"]["far_from_strait_km"],
            "min_distance_factor": cfg["reaction_model"]["min_distance_factor"],
            "waiting_areas": WAITING_AREAS,
            "note_zh": "影响强度按船舶与海峡参考点的实际大圆距离衰减，并对驶出方向的船舶加权、对已通过海峡的船舶减权。等待区为模拟命名区域，不是官方锚地边界。",
        },
        "response_model": {
            "unaffected_background_ships": unaffected_count,
            "unaffected_ship_fraction_config": cfg["reaction_model"]["unaffected_ship_fraction"],
            "ships_with_hold_or_anchor_behaviour": anchored_like,
            "response_delay_median_hours_config": cfg["reaction_model"]["response_delay_hours_median"],
            "response_delay_range_hours_observed": [
                round(min((s["response_delay_h"] for s in ships if not s["unaffected"]), default=0), 2),
                round(max((s["response_delay_h"] for s in ships if not s["unaffected"]), default=0), 2),
            ],
            "recovery_mode_zh": "恢复方式为：在 P3 阶段按每船 recovery_factor 降低影响分，影响分低于阈值即回到“减速”或“正常通行”；未设定统一时刻恢复。",
            "assumption_note_zh": "响应延迟、影响强度、恢复方式、阈值全部为教学模拟参数，没有新闻报道支持其具体数值。",
        },
        "participating_ships": participating,
        "route_validation": {
            name: {
                "length_km": rep["length_km"],
                "land_samples": rep["land_samples"],
                "clean": rep["clean"],
            } for name, rep in route_reports.items()
        },
        "cleaning": cleaning_stats,
        "reported_vs_assumed": {
            "reported_facts_zh": [
                "2026-02-26 至 02-27：美伊核谈未果、兵力集结、外界猜测打击（evt_001/evt_003/evt_004/evt_005）。",
                "2026-02-28：美以大规模空袭开始（evt_009），伊朗宣布报复行动（evt_008），海湾空域关闭（evt_011）。",
                "2026-02-28 晚至 03-01：伊朗方面警告船只禁行并宣布关闭海峡，航运近乎停摆、数百艘船滞留（evt_007）。",
                "2026-03-01 至 03-02：多艘油轮遇袭（evt_028/evt_065），印度航运要求船舶避行、27 艘印籍船滞留（evt_040）。",
                "2026-03-02：市场震荡、油价上涨与战争险撤保（evt_024/evt_029/evt_049）。",
            ],
            "simulated_assumptions_zh": [
                "逐船航速、等待时长、锚泊比例、过境数量变化全部为模拟值。",
                "响应延迟、影响强度、影响距离衰减、恢复方式全部为模拟参数。",
                "P3（03-03 至 03-04）的“有限复航与试探性通行”没有新闻支持，属教学补充。",
                "船队规模 150 艘、船型构成与船名均为模拟设定。",
            ],
            "not_claimed_zh": [
                "没有为任何新闻标题补充“海峡全面封锁”之外的结论，也没有把分析性标题当作既成事实。",
                "没有编造袭击、沉船、伤亡等事件，也没有把新闻提到的船名映射到模拟船。",
                "没有声称页面已经实现新闻与船位联动；本批次只交付数据与生成工具。",
                "没有把本批次数据描述为真实 AIS 或真实海上态势。",
            ],
        },
        "replay_compatibility_zh": [
            "回放接口单次最多 24 小时、50,000 个位置点；本批次按 UTC 自然日分片，每片天然满足 24 小时上限。",
            "当前 /simulation/meta 使用固定 300 秒帧间隔，而本批次真实报位间隔不固定；页面的播放步长是展示概念，与实际报位间隔互不影响，本批次没有为了时间轴把船位重采样成均匀间隔。",
            "当前新闻浏览与模拟船位回放彼此独立，导入本批次数据不会自动产生新闻联动。",
        ],
    }


def build_model_stats(cfg, ships, diagnostics_by_ship, labels, cleaning_stats,
                      reserved_mmsi, reserved_reason=None, identity_report=None) -> dict:
    underway: list[float] = []
    anchored: list[float] = []
    every: list[float] = []
    clamped = 0
    voyages = 0
    off_area_seconds = 0.0
    mode_seconds: dict[str, float] = defaultdict(float)
    phase_modes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ship_id, diagnostics in diagnostics_by_ship.items():
        clamped += diagnostics["clamped_reports"]
        voyages += diagnostics["voyages"]
        off_area_seconds += diagnostics["off_area_seconds"]
        for state, interval in diagnostics["generated_intervals"]:
            every.append(interval)
            (underway if state == "underway" else anchored).append(interval)
        for mode, seconds in diagnostics["mode_seconds"].items():
            mode_seconds[mode] += seconds
        for phase_id, mode in diagnostics["phase_modes"].items():
            phase_modes[phase_id][mode] += 1

    def describe(values: list[float]) -> dict:
        if not values:
            return {"n": 0}
        ordered = sorted(values)
        return {
            "n": len(ordered),
            "mean": round(sum(ordered) / len(ordered), 2),
            "median": round(ordered[len(ordered) // 2], 2),
            "p10": round(ordered[int(0.1 * (len(ordered) - 1))], 2),
            "p90": round(ordered[int(0.9 * (len(ordered) - 1))], 2),
            "max": round(ordered[-1], 2),
        }

    return {
        "database_verified": bool(reserved_mmsi),
        "database_notes": (
            [f"已通过现有数据库连接只读查询 ships 表，共 {len(reserved_mmsi)} 条记录，用作身份冲突检查。"]
            if reserved_mmsi else
            [f"本次未取得现有数据库的船舶清单，因此只能按批次内唯一性校验。原因：{reserved_reason or '只读查询返回空集'}"]
        ),
        "identity_check": identity_report or {},
        "generated_all": describe(every),
        "generated_underway": describe(underway),
        "generated_anchored": describe(anchored),
        "generated_mean_underway_s": round(sum(underway) / len(underway), 2) if underway else None,
        "generated_mean_anchored_s": round(sum(anchored) / len(anchored), 2) if anchored else None,
        "design_mean_underway_s": cfg["reporting"]["underway_mean_interval_seconds"],
        "design_mean_anchored_s": cfg["reporting"]["anchored_mean_interval_seconds"],
        "sigma_log_space": cfg["reporting"]["sigma_log_space"],
        "truncation": {
            "min_interval_seconds": cfg["reporting"]["min_interval_seconds"],
            "max_interval_seconds": cfg["reporting"]["max_interval_seconds"],
            "note_zh": "默认未设置最小/最大间隔，因此没有截断，生成间隔的算术均值等于设计均值（在航 900 秒、锚泊 2700 秒）。",
        },
        "clamped_reports": clamped,
        "voyages": voyages,
        "off_area_hours": round(off_area_seconds / 3600.0, 1),
        "mode_hours": {k: round(v / 3600.0, 1) for k, v in sorted(mode_seconds.items())},
        "phase_modes": {k: dict(sorted(v.items(), key=lambda kv: -kv[1])) for k, v in phase_modes.items()},
        "injected_anomalies": labels.get("by_type", {}),
        "cleaning": cleaning_stats,
    }


def default_reserved_mmsi() -> tuple[dict, str | None]:
    """Read existing ship identities from the database, read-only.

    Returns {mmsi: {"name": ..., "callsign": ...}} plus a reason string when the read
    failed, so the acceptance report can say why database verification was or was not
    performed instead of guessing.
    """
    try:
        from sqlalchemy import text
        from backend.app.database import SessionLocal
        with SessionLocal() as session:
            rows = session.execute(text("SELECT mmsi, name, callsign FROM ships")).mappings().all()
        values = {row["mmsi"]: {"name": row["name"], "callsign": row["callsign"]} for row in rows}
        if not values:
            return {}, "已连接数据库，但 ships 表当前没有记录。"
        return values, None
    except Exception as exc:  # noqa: BLE001
        return {}, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成霍尔木兹海峡教学模拟 AIS 数据")
    parser.add_argument("--config", default=str(ROOT / "config" / "scenario_config.json"))
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--no-db-check", action="store_true",
                        help="跳过与现有数据库 MMSI 的只读冲突检查")
    parser.add_argument("--repeat-check", action="store_true",
                        help="用相同种子再生成一次并比较内容摘要")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    seed = args.seed if args.seed is not None else cfg["random_seed"]
    outdir = Path(args.outdir) if args.outdir else ROOT / cfg["output"]["directory"]

    land = LandChecker.from_geojson(ROOT / "reference" / "ne_10m_land.geojson")
    land_stats = land.build()

    if args.no_db_check:
        reserved, reserved_reason = {}, "本次使用了 --no-db-check，跳过了与现有数据库的身份只读比对。"
    else:
        reserved, reserved_reason = default_reserved_mmsi()
    print(f"现有库船舶记录数：{len(reserved)}")
    if reserved_reason:
        print(f"数据库只读检查说明：{reserved_reason}")

    result = generate_batch(cfg, seed, outdir, land, land_stats, reserved, reserved_reason)
    print(f"输出目录：{outdir}")
    print(f"船舶：{result['manifest']['ship_count']}")
    print(f"数据库兼容船位：{result['manifest']['clean_position_count']}")
    print(f"原始观测船位：{result['manifest']['raw_position_count']}")
    print(f"每日点数：{json.dumps(result['manifest']['daily_clean_counts'], ensure_ascii=False)}")
    print(f"内容摘要：{result['combined_sha256']}")

    if args.repeat_check:
        second_dir = outdir.parent / (outdir.name + "_repeat_check")
        second = generate_batch(cfg, seed, second_dir, land, land_stats, reserved, reserved_reason)
        same = second["combined_sha256"] == result["combined_sha256"]
        print(f"重复生成目录：{second_dir}")
        print(f"同种子同配置结果一致：{'是' if same else '否'}")
        if not same:
            for name, value in result["files"].items():
                if second["files"].get(name) != value:
                    print(f"  差异：{name}")
        return 0 if same else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
