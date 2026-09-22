"""联调：真实 DeepSeek 工具调用 + 后端只读查询工具（契约 v4）。

覆盖三个场景：
1. 通行问题（v2 回归：query_strait_passages）；
2. 多工具问题（search_ships + get_ship_track）；
3. 新闻事件问题（get_event_context）。

从环境变量读取 DEEPSEEK_API_KEY（不打印密钥）；从仓库根目录运行：
    backend/.venv/Scripts/python.exe scripts/test_deepseek_toolcall.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.database import SessionLocal
from backend.app.services.agent.model_client import AgentConfigError, build_client
from backend.app.services.agent.runner import run_agent

QUESTIONS = [
    "封锁后有哪些船还通过了海峡？",
    "帮我找一下油轮 SIM V2 油轮 004，它封锁后 24 小时的轨迹大概是什么情况？",
    "evt_001 是什么事件？有哪些媒体报道了它？",
]


def run_case(client, question: str) -> bool:
    trace = []
    started = time.monotonic()
    with SessionLocal() as db:
        outcome = run_agent(db, client, question, trace=trace)
    elapsed = time.monotonic() - started

    print(f"问题: {question}")
    print(f"模型工具调用（{len(trace)} 次）:")
    for call in trace:
        print(f"  {call['tool']}({call['arguments']})")
    print(f"status: {outcome['status']}  tools_used: {outcome['tools_used']}")
    summary = outcome.get("query_summary")
    if summary:
        print(
            f"通行结果: matched_ships={summary['matched_ship_count']} "
            f"passages={summary['passage_count']} "
            f"uncertain={summary['uncertain_candidate_count']} "
            f"positions_read={summary['position_count']}"
        )
    for ship in outcome["ships"]:
        print(f"  ship_id={ship['ship_id']} name={ship['name']} passage_count={ship['passage_count']}")
    if not outcome["ships"] and not outcome["evidence"]:
        for call_id, result in outcome["results"].items():
            print(
                f"  结果[{call_id}/{result.get('tool_name')}]: "
                f"status={result.get('status')}"
            )
    print(f"模型回答（前 500 字符）:\n{outcome['answer'][:500]}")
    print(f"耗时: {elapsed:.1f}s")
    ok = bool(outcome["tools_used"]) and bool(outcome["answer"].strip())
    print("PASS" if ok else "FAIL: 缺少工具调用或回答为空")
    return ok


def main():
    try:
        client = build_client()
    except AgentConfigError as exc:
        print(f"SKIP: {exc}")
        return 0

    passed = 0
    for question in QUESTIONS:
        print("=" * 72)
        try:
            if run_case(client, question):
                passed += 1
        except Exception as exc:  # 联调脚本：打印后继续下一个场景
            print(f"ERROR: {type(exc).__name__}: {exc}")
        print()
    print(f"共 {passed}/{len(QUESTIONS)} 个场景通过")
    return 0 if passed == len(QUESTIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
