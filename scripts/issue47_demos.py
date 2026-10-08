"""Issue #47 三组「对话→分析→证据→地图」演示验收脚本。

真实模型经工作树后端（默认 http://localhost:8033）执行多轮问答；
每组含至少一条条件修改追问；同条件手动 API 与智能体工具结果对账。
输出原始 JSON 到 output/issue47/，控制台只打摘要。

用法: python scripts/issue47_demos.py [--base http://localhost:8033]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "issue47"


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def get(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def analyze(base: str, question: str, history: list[dict], extra: dict | None = None) -> dict:
    payload = {"question": question, "history": history[-10:]}
    if extra:
        payload.update(extra)
    started = time.monotonic()
    status, body = post(base, "/agent/analyze", payload)
    elapsed = time.monotonic() - started
    return {
        "question": question,
        "http_status": status,
        "elapsed_seconds": round(elapsed, 2),
        "request": payload,
        "response": body,
    }


def summarize(run: dict) -> str:
    resp = run["response"]
    if run["http_status"] != 200:
        return f"HTTP {run['http_status']}: {json.dumps(resp, ensure_ascii=False)[:300]}"
    tools = resp.get("tools_used", [])
    results = resp.get("results", {})
    parts = [f"status={resp.get('status')}", f"tools={tools}"]
    for call_id, result in results.items():
        name = result.get("tool_name")
        line = f"  {name}[{result.get('status')}]"
        if name in ("compare_strait_passage_statistics", "query_strait_passage_statistics"):
            q = result.get("query", {})
            line += f" window={q.get('a_start') or q.get('start_at')}..{q.get('b_end') or q.get('end_at')} types={q.get('ship_types')} dir={q.get('direction')}"
            summary = result.get("summary", {})
            line += f" summary_keys={list(summary.keys())[:6]}"
        elif name in ("query_area_ship_activity", "compare_area_ship_activity", "query_area_ship_snapshot"):
            q = result.get("query", {})
            area = result.get("area", {})
            line += f" area={area.get('area_id')} v{area.get('version')} default={area.get('is_default')} types={q.get('filters', {}).get('ship_types') if isinstance(q.get('filters'), dict) else q.get('ship_types')}"
            if name == "query_area_ship_activity":
                line += f" visits={result.get('summary', {}).get('visit_count')} ships={result.get('summary', {}).get('unique_ship_count')}"
        elif name == "get_ship_track":
            line += f" ship={result.get('ship_id')} fixes={result.get('fix_count')} coverage={result.get('coverage_start')}..{result.get('coverage_end')}"
        parts.append(line)
    actions = resp.get("analysis_actions", []) or []
    if actions:
        parts.append(f"  analysis_actions={[a.get('type') + ':' + str(a.get('mode')) for a in actions]}")
    maps = resp.get("map_actions", []) or []
    if maps:
        parts.append(f"  map_actions={[m.get('type') + '/' + m.get('trigger') for m in maps]}")
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8033")
    parser.add_argument("--group", default="all", choices=["all", "1", "2", "3"])
    args = parser.parse_args()
    base = args.base
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript: list[dict] = []

    def save(name: str) -> None:
        path = OUT_DIR / f"{stamp}_{name}.json"
        path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[saved] {path}")

    history: list[dict] = []

    # ---------- 组 1：同船型/方向的两期通行比较 + 追问 ----------
    if args.group in ("all", "1"):
        print("=== 组 1：通行两期比较（油轮，全方向） ===")
        runs = []
        runs.append(analyze(base, "比较 2026-02-25 全天和 2026-02-28 全天油轮通过霍尔木兹海峡的次数变化", history))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "那货船呢？", history))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "还是油轮，但只看东向西方向呢？", history))
        print(summarize(runs[-1]))
        transcript.append({"group": 1, "runs": runs})
        save("group1")

        # 同条件手动 API 对账（取组 1 第一轮工具实际参数）
        manual = []
        for run in runs:
            for result in (run["response"].get("results") or {}).values():
                if result.get("tool_name") == "compare_strait_passage_statistics" and result.get("status") == "ok":
                    q = result["query"]
                    payload = {
                        "a_start_at": q["a_start"], "a_end_at": q["a_end"],
                        "b_start_at": q["b_start"], "b_end_at": q["b_end"],
                        "ship_types": q.get("ship_types"), "direction": q.get("direction"),
                    }
                    status, body = post(base, "/api/strait-passages/compare", payload)
                    manual.append({"tool_query": q, "http_status": status, "manual_response": body})
        transcript.append({"group": 1, "manual_compare": manual})
        save("group1_with_manual")

    # ---------- 组 2：默认区 → 用户矩形 → 区域两期比较 → 恢复默认 ----------
    if args.group in ("all", "2"):
        print("=== 组 2：区域活动（默认区→圈选矩形→两期比较→恢复默认） ===")
        history = []
        custom_area = {"west": 56.2, "south": 26.1, "east": 56.7, "north": 26.7, "area_id": "custom", "label": "用户圈选矩形A"}
        runs = []
        runs.append(analyze(base, "2026-02-27 0 点到 2026-02-28 0 点，默认分析区域里有多少艘船出现过、观测进出多少次？", history))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "同样的问题，在我刚圈选的矩形区域里呢？", history, {"area_context": custom_area}))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "比较 2026-02-26 和 2026-02-28 两天这个区域内的船只活动", history, {"area_context": custom_area}))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "恢复默认区域，再比较同样的两天", history))
        print(summarize(runs[-1]))
        transcript.append({"group": 2, "runs": runs})
        save("group2")

        manual = []
        for run in runs:
            for result in (run["response"].get("results") or {}).values():
                if result.get("tool_name") == "compare_area_ship_activity" and result.get("status") == "ok":
                    q = result["query"]
                    payload = {
                        "start_a": q["start_a"], "end_a": q["end_a"],
                        "start_b": q["start_b"], "end_b": q["end_b"],
                        "ship_type": (q.get("filters") or {}).get("ship_types"),
                    }
                    if not result.get("area", {}).get("is_default"):
                        b = result["area"].get("bounds", {})
                        payload.update({"west": b.get("west"), "south": b.get("south"), "east": b.get("east"), "north": b.get("north")})
                    status, body = post(base, "/api/area-activity/compare", payload)
                    manual.append({"tool_query": q, "http_status": status, "manual_response": body})
        transcript.append({"group": 2, "manual_compare": manual})
        save("group2_with_manual")

    # ---------- 组 3：并列分析 + 证据单船轨迹 ----------
    if args.group in ("all", "3"):
        print("=== 组 3：通行与区域并列分析 + 证据轨迹 ===")
        history = []
        runs = []
        runs.append(analyze(base, "2026-02-28 这一天，油轮通过海峡的情况和默认分析区域的活动情况分别是什么样的？", history))
        print(summarize(runs[-1]))
        resp = runs[-1]["response"]
        if resp.get("answer"):
            history += [
                {"role": "user", "content": runs[-1]["question"]},
                {"role": "assistant", "content": resp["answer"]},
            ]
        runs.append(analyze(base, "把刚才通过海峡的一艘油轮的轨迹在地图上显示出来", history))
        print(summarize(runs[-1]))
        transcript.append({"group": 3, "runs": runs})
        save("group3")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
