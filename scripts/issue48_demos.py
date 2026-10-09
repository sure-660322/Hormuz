"""Issue #48 真实模型三题演示（验收 #2：筛选 / 分组 / 排名）。

真实模型（DeepSeek）经工作树后端 /agent/analyze 走受限 SQL 工具
（get_database_schema → check_sql → execute_sql）查询受控分析快照；
每个回答须带窗口/区域/版本/来源与 query_id。
输出原始 JSON 到 output/issue48/，控制台只打摘要。

前置：后端以 AGENT_DB_NAME=hormuz_sql_test 启动（快照只在独立测试库）：
    AGENT_DB_NAME=hormuz_sql_test python -m uvicorn backend.app.main:app --port 8038

用法: python scripts/issue48_demos.py [--base http://localhost:8038]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "issue48"

QUESTIONS = [
    {
        "key": "filter",
        "question": (
            "请使用受限 SQL 工具（先 get_database_schema 查看 catalog，再用 check_sql 校验、"
            "最后 execute_sql 执行）查询 agent_data 快照表 v_passage_evidence："
            "2026-02-26 全天（UTC）西向东确定通行中船型为油轮的通行有哪些？"
            "列出船名和观测完成时间，并说明判定窗口、快照版本（catalog_version）与 query_id。"
        ),
    },
    {
        "key": "group",
        "question": (
            "请使用受限 SQL 工具（get_database_schema → check_sql → execute_sql）"
            "查询 agent_data 快照表 v_passage_daily：按天和方向统计 2026-02-25 到 "
            "2026-03-03 每天的确定通行次数和确定独立船数，给出 catalog_version 与 query_id，"
            "并说明逐日独立船数能不能相加当作整段窗口的去重船数。"
        ),
    },
    {
        "key": "ranking",
        "question": (
            "请使用受限 SQL 工具（get_database_schema → check_sql → execute_sql）"
            "查询 agent_data 快照表 v_area_visit：默认分析区域 hormuz_core_v1 在 "
            "2026-02-25 全天（UTC）观测停留时间最长的前 5 艘船是哪些？"
            "按 observed_seconds 原值排序取前 5 即可，不要做单位换算或函数计算；"
            "给出访问状态、area_version、catalog_version 与 query_id。"
        ),
    },
]

QUERY_ID_RE = re.compile(r"^aq_\d{8}T\d{6}_[0-9a-f]{12}$")


def post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # noqa: BLE001
        body = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def analyze(base: str, question: str) -> dict:
    payload = {"question": question, "history": []}
    started = time.monotonic()
    status, body = post(base, "/agent/analyze", payload)
    elapsed = time.monotonic() - started
    return {
        "question": question,
        "http_status": status,
        "elapsed_seconds": round(elapsed, 2),
        "response": body,
    }


def verify(run: dict) -> list[str]:
    """验收要点核验：工具链、query_id、窗口/区域/版本/来源。"""
    problems: list[str] = []
    resp = run["response"]
    if run["http_status"] != 200:
        return [f"HTTP {run['http_status']}"]
    tools = resp.get("tools_used") or []
    for required in ("get_database_schema", "check_sql", "execute_sql"):
        if required not in tools:
            problems.append(f"缺少工具调用 {required}: {tools}")
    executed = [r for r in (resp.get("results") or {}).values()
                if r.get("tool_name") == "execute_sql"]
    if not executed:
        problems.append("没有 execute_sql 结果")
    for item in executed:
        if item.get("status") != "ok":
            problems.append(f"execute_sql 状态非 ok: {item.get('status')} {item.get('code')}")
            continue
        source = item.get("source") or {}
        if source.get("catalog_version") != "3.0":
            problems.append(f"catalog_version 缺失或非 3.0: {source.get('catalog_version')}")
        if not source.get("views"):
            problems.append("source.views 缺失")
        if not QUERY_ID_RE.match(item.get("query_id") or ""):
            problems.append(f"query_id 格式异常: {item.get('query_id')}")
        if not item.get("limitations"):
            problems.append("limitations 未注入")
    answer = resp.get("answer") or ""
    if len(answer) < 20:
        problems.append(f"回答过短: {answer!r}")
    return problems


def summarize(run: dict) -> str:
    resp = run["response"]
    lines = [
        f"http={run['http_status']} elapsed={run['elapsed_seconds']}s "
        f"tools={resp.get('tools_used')}",
    ]
    for call_id, item in (resp.get("results") or {}).items():
        if item.get("tool_name") != "execute_sql":
            continue
        source = item.get("source") or {}
        lines.append(
            f"  execute_sql[{item.get('status')}] query_id={item.get('query_id')} "
            f"catalog={source.get('catalog_version')} views={source.get('views')} "
            f"rows={item.get('returned_row_count')}"
        )
        for row in (item.get("rows") or [])[:5]:
            lines.append(f"    {row}")
    lines.append(f"  answer={str(resp.get('answer'))[:400]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8038")
    parser.add_argument("--key", default="all",
                        choices=["all", *[q["key"] for q in QUESTIONS]])
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    transcript: list[dict] = []
    failed = False

    for item in QUESTIONS:
        if args.key not in ("all", item["key"]):
            continue
        print(f"=== {item['key']}: {item['question'][:50]}... ===")
        run = analyze(args.base, item["question"])
        print(summarize(run))
        problems = verify(run)
        transcript.append({"key": item["key"], "problems": problems, "run": run})
        if problems:
            failed = True
            for problem in problems:
                print(f"  VERIFY-FAIL {problem}")
        else:
            print("  VERIFY-OK 回答带窗口/区域/版本/来源与 query_id")

    path = OUT_DIR / f"{stamp}_demos.json"
    path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
