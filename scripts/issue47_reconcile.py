"""Issue #47 对账脚本：读取 issue47_demos.py 的转录，用同条件手动 API 复核工具结果。

不调用模型；只依据转录中工具实际生效的参数重放手动接口并逐项比对。
用法: python scripts/issue47_reconcile.py [--base http://localhost:8033] [--glob output/issue47/*_group*.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import urllib.request
from pathlib import Path


def post(base: str, path: str, payload: dict):
    req = urllib.request.Request(
        base + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        return exc.code, json.loads(exc.read().decode("utf-8", "replace"))


def check(label: str, tool_value, manual_value, mismatches: list[str]) -> None:
    if tool_value == manual_value:
        print(f"  OK  {label}: {tool_value}")
    else:
        mismatches.append(f"{label}: tool={tool_value} manual={manual_value}")
        print(f"  MISMATCH {label}: tool={tool_value} manual={manual_value}")


def reconcile_passage(base: str, transcript: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for item in transcript:
        for run in item.get("runs", []):
            for result in (run["response"].get("results") or {}).values():
                if result.get("tool_name") != "compare_strait_passage_statistics":
                    continue
                if result.get("status") not in ("ok", "partial"):
                    continue
                a, b = result["a_period"], result["b_period"]
                status, manual = post(base, "/api/strait-passages/compare", {
                    "a_start_at": a["start_at"], "a_end_at": a["end_at"],
                    "b_start_at": b["start_at"], "b_end_at": b["end_at"],
                    "ship_types": result.get("ship_types"), "direction": result.get("direction"),
                })
                print(f"[passage] {a['start_at']} vs {b['start_at']} types={result.get('ship_types')} dir={result.get('direction')} http={status}")
                if status != 200:
                    mismatches.append(f"passage manual http {status}")
                    continue
                for period_key, manual_side in (("a_period", "a"), ("b_period", "b")):
                    for metric in result.get("metrics", []):
                        name = metric["metric"]
                        tool_val = (result[period_key]["window"] or {}).get(name)
                        manual_val = (manual.get(manual_side, {}).get("window") or {}).get(name)
                        check(f"{period_key}.{name}", tool_val, manual_val, mismatches)
    return mismatches


def get_qs(base: str, path: str, params: dict):
    from urllib.parse import urlencode
    qs = urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    try:
        with urllib.request.urlopen(f"{base}{path}?{qs}", timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        return exc.code, json.loads(exc.read().decode("utf-8", "replace"))


def reconcile_area(base: str, transcript: list[dict]) -> list[str]:
    mismatches: list[str] = []
    for item in transcript:
        for run in item.get("runs", []):
            for result in (run["response"].get("results") or {}).values():
                name = result.get("tool_name")
                if name == "compare_area_ship_activity" and result.get("status") in ("ok", "partial"):
                    q = result["query"]
                    params = {
                        "start_a": q["start_a"], "end_a": q["end_a"],
                        "start_b": q["start_b"], "end_b": q["end_b"],
                        "ship_type": (q.get("filters") or {}).get("ship_types"),
                    }
                    if not result.get("area", {}).get("is_default"):
                        area_block = result["area"]
                        params.update({k: area_block.get(k) for k in ("west", "south", "east", "north")})
                    status, manual = get_qs(base, "/api/area-activity/compare", params)
                    print(f"[area-compare] {q['start_a']} vs {q['start_b']} default={result['area'].get('is_default')} http={status}")
                    if status != 200:
                        mismatches.append(f"area compare manual http {status}")
                        continue
                    for side in ("a", "b"):
                        tool_summary = result[side]["summary"]
                        manual_summary = manual[side]["summary"]
                        for key in ("visit_count", "unique_ship_count", "total_ship_hours"):
                            if key in tool_summary or key in manual_summary:
                                check(f"{side}.{key}", tool_summary.get(key), manual_summary.get(key), mismatches)
                elif name == "query_area_ship_activity" and result.get("status") in ("ok", "partial"):
                    q = result["query"]
                    params = {
                        "start": q["start_at"], "end": q["end_at"],
                        "ship_type": (q.get("filters") or {}).get("ship_types"),
                    }
                    if not result.get("area", {}).get("is_default"):
                        area_block = result["area"]
                        params.update({k: area_block.get(k) for k in ("west", "south", "east", "north")})
                    status, manual = get_qs(base, "/api/area-activity/activity", params)
                    print(f"[area-activity] {q['start_at']}..{q['end_at']} default={result['area'].get('is_default')} http={status}")
                    if status != 200:
                        mismatches.append(f"area activity manual http {status}")
                        continue
                    tool_summary = result["summary"]
                    manual_summary = manual["summary"]
                    for key in ("visit_count", "unique_ship_count", "total_ship_hours"):
                        if key in tool_summary or key in manual_summary:
                            check(key, tool_summary.get(key), manual_summary.get(key), mismatches)
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8033")
    parser.add_argument("--pattern", default="output/issue47/*group*.json")
    args = parser.parse_args()

    mismatches: list[str] = []
    for path in sorted(glob.glob(args.pattern), key=lambda p: Path(p).stat().st_mtime):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        print(f"== {path}")
        mismatches += reconcile_passage(args.base, data)
        mismatches += reconcile_area(args.base, data)
    print()
    if mismatches:
        print(f"MISMATCHES: {len(mismatches)}")
        for m in mismatches:
            print(" -", m)
        return 1
    print("ALL CONSISTENT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
