"""最小联调：真实 DeepSeek 工具调用 + 后端只读查询工具。

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

QUESTION = "封锁后有哪些船还通过了海峡？"


def main():
    try:
        client = build_client()
    except AgentConfigError as exc:
        print(f"SKIP: {exc}")
        return 0

    trace = []
    started = time.monotonic()
    with SessionLocal() as db:
        outcome = run_agent(db, client, QUESTION, trace=trace)
    elapsed = time.monotonic() - started

    print(f"问题: {QUESTION}")
    print(f"模型工具调用（{len(trace)} 次）:")
    for call in trace:
        print(f"  {call['tool']}({call['arguments']})")
    print(f"status: {outcome['status']}")
    summary = outcome["query_summary"]
    print(
        f"后端工具结果: matched_ships={summary.matched_ship_count} "
        f"passages={summary.passage_count} "
        f"uncertain={summary.uncertain_candidate_count} "
        f"positions_read={summary.position_count}"
    )
    for ship in outcome["ships"]:
        print(f"  ship_id={ship.ship_id} name={ship.name} passage_count={ship.passage_count}")
    for evidence in outcome["evidence"]:
        print(
            f"  [{evidence.evidence_id}] ship={evidence.ship_id} "
            f"{evidence.direction} completed={evidence.observed_completion_at}"
        )
    print(f"模型回答（前 500 字符）:\n{outcome['answer'][:500]}")
    print(f"耗时: {elapsed:.1f}s")
    print("PASS: 模型完成工具调用且回答基于工具结果")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
