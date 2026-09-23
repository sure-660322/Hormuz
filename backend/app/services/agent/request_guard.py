"""Request-wide tool budget and cancellation gate shared by every Agent tool."""
from __future__ import annotations

import threading
import time


def new_state(max_tool_executions: int, budget_seconds: float) -> dict:
    return {
        "tools_used": [], "results": {}, "tool_executions": 0,
        "call_sequence": 0, "max_tool_executions": max_tool_executions,
        "sql_closed": False, "sql_attempts": 0,
        "budget_exhausted": False,
        "lock": threading.RLock(), "cancel_event": threading.Event(),
        "deadline": time.monotonic() + budget_seconds,
    }


def reserve_tool(state: dict) -> dict | None:
    """Reserve one attempt atomically; denied attempts never touch a repository."""
    with state.setdefault("lock", threading.RLock()):
        cancelled = state.get("cancel_event")
        if (cancelled is not None and cancelled.is_set()) or time.monotonic() >= state.get("deadline", float("inf")):
            if cancelled is not None:
                cancelled.set()
            return {"status": "error", "code": "AGENT_TIMEOUT", "message": "智能体整体执行已超时"}
        if state["tool_executions"] >= state["max_tool_executions"]:
            state["budget_exhausted"] = True
            return {
                "status": "error", "code": "TOOL_BUDGET_EXCEEDED",
                "message": f"工具调用已达到 {state['max_tool_executions']} 次预算",
            }
        state["tool_executions"] += 1
        return None
