"""验收项 2/5：把独立复算结果与 8031 的实际 HTTP 响应逐字段比对。

读取 output/acceptance/independent_recompute.json（独立复算，期望值来源），对同一组参数请求
http://127.0.0.1:8031/api/area-activity/*，逐字段核对：
  快照：in_area_count / out_of_area_fresh_count / stale_fix_count / evaluated_ship_count
  活动：ships_observed / observed_entry_count / observed_exit_count / observed_ship_hours / visit_count
        以及 daily[] 的 date / ships_observed / entry / exit / ship_seconds
  比较：metrics 的 a / b / delta / change_rate
**期望值只来自独立复算 JSON，不调用后端函数。**

运行：
    & .\\backend\\.venv\\Scripts\\python.exe -X utf8 scripts\\verify_area_activity_api_recompute.py
输出：output/acceptance/api_vs_recompute.json（另打印逐项差异）
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "output/acceptance"
HERE.mkdir(parents=True, exist_ok=True)
RECOMPUTE = HERE / "independent_recompute.json"
OUT = HERE / "api_vs_recompute_current.json"
parser = argparse.ArgumentParser()
parser.add_argument("--base", default="http://127.0.0.1:8032")
BASE = parser.parse_args().base.rstrip("/")
TOL_HOURS = 0.01        # 船时容差（小时）
TOL_SECONDS = 1.0       # 每日船秒容差


def get(path: str, params: dict) -> dict:
    qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    with urllib.request.urlopen(url, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bounds_params(area: dict) -> dict:
    if area.get("area_id") == "hormuz_core_v1":
        return {}
    return {"west": area["west"], "south": area["south"], "east": area["east"], "north": area["north"]}


def cmp_num(name: str, expected, actual, tol=0.0) -> dict:
    if expected is None or actual is None:
        ok = expected == actual
    elif isinstance(expected, float) or isinstance(actual, float):
        ok = abs(float(expected) - float(actual)) <= tol
    else:
        ok = int(expected) == int(actual)
    return {"field": name, "expected": expected, "actual": actual, "ok": bool(ok), "tol": tol}


def compare_snapshot(scn: dict) -> list[dict]:
    resp = get("/api/area-activity/snapshot", {
        "at": scn["query"]["at"], "freshness_seconds": scn["query"]["freshness_seconds"],
        **bounds_params(scn["area"]),
    })
    out = []
    for f in ("in_area_count", "out_of_area_fresh_count", "stale_fix_count", "evaluated_ship_count"):
        out.append(cmp_num(f, scn["summary"][f], resp["summary"].get(f)))
    out.append(cmp_num("status_is_ok", True, resp.get("status") in ("ok", "partial")))
    return out, resp


def compare_activity(scn: dict) -> tuple[list[dict], dict]:
    params = {"start": scn["query"]["start"], "end": scn["query"]["end"],
              **bounds_params(scn["area"])}
    if scn["query"].get("batch_ids"):
        params["batch_ids"] = scn["query"]["batch_ids"]
    if scn["query"].get("ship_type"):
        params["ship_type"] = scn["query"]["ship_type"]   # urllib doseq 展开为重复参数
    resp = get("/api/area-activity/activity", params)
    out = []
    summ = resp.get("summary", {})
    mapping = {
        "ships_observed": ("ships_observed", 0),
        "observed_entry_count": ("observed_entry_count", 0),
        "observed_exit_count": ("observed_exit_count", 0),
        "observed_ship_hours": ("observed_ship_hours", TOL_HOURS),
        "visit_count": ("visit_count", 0),
    }
    for exp_key, (api_key, tol) in mapping.items():
        out.append(cmp_num(exp_key, scn["summary"][exp_key], summ.get(api_key), tol))
    api_daily = {d["date"]: d for d in resp.get("daily", [])}
    for d in scn["daily"]:
        ad = api_daily.get(d["date"])
        if ad is None:
            out.append({"field": f"daily[{d['date']}]", "expected": "present", "actual": None, "ok": False})
            continue
        for f, tol in (("ships_observed", 0), ("observed_entry_count", 0),
                       ("observed_exit_count", 0), ("observed_ship_seconds", TOL_SECONDS),
                       ("visits_touching_day", 0)):
            out.append(cmp_num(f"daily[{d['date']}].{f}", d[f], ad.get(f), tol))
    return out, resp


COMPARE_CASES = [
    # recompute 的 compare key -> (A 场景名, B 场景名)；两期必须同一矩形（§2.5）
    ("default_prev1d_vs_1d", "activity_default_prev1d_2026-02-27", "activity_default_1d_2026-02-28"),
    ("rectA_prev1d_vs_1d", "activity_rectA_west_prev1d", "activity_rectA_west_1d"),
    ("rectB_prev1d_vs_1d", "activity_rectB_east_prev1d", "activity_rectB_east_1d"),
]


def compare_ab(rec: dict, key: str, name_a: str, name_b: str) -> tuple[list[dict], dict]:
    a, b = rec["scenarios"][name_a], rec["scenarios"][name_b]
    assert a["area"] == b["area"], f"{key}: 两期区域不一致，不能与 /compare 比对"
    resp = get("/api/area-activity/compare", {
        "start_a": a["query"]["start"], "end_a": a["query"]["end"],
        "start_b": b["query"]["start"], "end_b": b["query"]["end"],
        **bounds_params(a["area"]),
    })
    api_metrics = {m["key"]: m for m in resp.get("metrics", [])}
    out = []
    for m in rec["compare"][key]["metrics"]:
        metric = m["metric"]
        am = api_metrics.get(metric)
        if am is None:
            out.append({"field": f"metrics.{metric}", "expected": "present", "actual": None, "ok": False})
            continue
        for f, tol in (("a", TOL_HOURS if "hours" in metric else 0),
                       ("b", TOL_HOURS if "hours" in metric else 0),
                       ("delta", TOL_HOURS if "hours" in metric else 0)):
            out.append(cmp_num(f"metrics[{metric}].{f}", m[f], am.get(f), tol))
        exp_rate, act_rate = m["change_rate"], am.get("change_rate")
        # 实测 API 把 change_rate 四舍五入到 4 位小数（如 0.46078431 -> 0.4608），
        # 因此按 4 位小数舍入误差判定，并单独记录是否为 round(exp, 4)。
        if exp_rate is None:
            ok = act_rate is None
            rounded = act_rate is None
        else:
            ok = act_rate is not None and abs(act_rate - exp_rate) <= 5.1e-5
            rounded = act_rate is not None and abs(act_rate - round(exp_rate, 4)) <= 1e-12
        out.append({"field": f"metrics[{metric}].change_rate", "expected": exp_rate,
                    "actual": act_rate, "ok": bool(ok), "tol": 5.1e-5,
                    "equals_round_4dp": bool(rounded)})
    return out, resp


def main() -> int:
    rec = json.loads(RECOMPUTE.read_text(encoding="utf-8"))
    payload = {"base": BASE, "source": str(RECOMPUTE), "checks": {}, "failures": []}
    for name, scn in rec["scenarios"].items():
        try:
            if name.startswith("snapshot"):
                checks, resp = compare_snapshot(scn)
            else:
                checks, resp = compare_activity(scn)
        except Exception as exc:  # noqa: BLE001
            payload["checks"][name] = {"error": f"{type(exc).__name__}: {exc}"}
            payload["failures"].append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"ERROR {name}: {exc}")
            continue
        bad = [c for c in checks if not c["ok"]]
        payload["checks"][name] = {"checks": checks, "failed": bad, "api_status": resp.get("status")}
        if bad:
            payload["failures"].append(f"{name}: {len(bad)} 项不一致")
        print(f"{'OK  ' if not bad else 'DIFF'} {name}: {len(checks) - len(bad)}/{len(checks)} 一致"
              + ("" if not bad else f" | 差异: {json.dumps(bad, ensure_ascii=False)}"))
    for key, name_a, name_b in COMPARE_CASES:
        try:
            checks, resp = compare_ab(rec, key, name_a, name_b)
            bad = [c for c in checks if not c["ok"]]
            payload["checks"][f"compare_{key}"] = {"checks": checks, "failed": bad,
                                                   "api_status": resp.get("status")}
            if bad:
                payload["failures"].append(f"compare_{key}: {len(bad)} 项不一致")
            print(f"{'OK  ' if not bad else 'DIFF'} compare_{key}: "
                  f"{len(checks) - len(bad)}/{len(checks)} 一致"
                  + ("" if not bad else f" | 差异: {json.dumps(bad, ensure_ascii=False)}"))
        except Exception as exc:  # noqa: BLE001
            payload["failures"].append(f"compare_{key}: {type(exc).__name__}: {exc}")
            print(f"ERROR compare_{key}: {exc}")
    payload["not_api_comparable"] = {
        "rectA_vs_rectB_same_window": "§2.5 要求两期同一矩形；跨矩形同窗口仅在独立复算里作几何对照"
    }
    payload["passed"] = not payload["failures"]
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'PASS' if payload['passed'] else 'FAIL'} -> {OUT}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
