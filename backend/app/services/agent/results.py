"""智能体响应组装助手（LC-04 自 runner.py 迁移）。

承载 v4 契约（docs/agent_integration.md）的服务端组装逻辑：
状态归并、通行结果顶层字段、limitations 合并和疑似外部指令防回显门。
与编排方式（旧自定义循环或 LangChain create_agent）无关。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from backend.app.services.agent.config import SCHEMA_VERSION
from backend.app.services.agent.serialization import to_jsonable
from backend.app.services.agent.strait_passages import (
    PassageEvidence,
    StraitPassageResult,
)


class AgentTimeoutError(RuntimeError):
    """整体执行超时（映射 504 AGENT_TIMEOUT）。"""


class AgentInvalidResponseError(RuntimeError):
    """模型调用或回答反复不符合契约（映射 502 AGENT_INVALID_RESPONSE）。"""


PASSAGE_RULE = (
    "虚拟双门线观测通行：纬度 25.8–27.1°N 带内，56.2°E 西侧与 56.7°E 东侧"
    "发生侧别变化；仅纳入经度 55.8–57.1°E、来源 nnu_ais 的历史报位。"
    "门线之间保留状态，完成侧首个报位时间 ∈ [closure_at, end_at)；"
    "前置侧别最多回看 24 小时，长间隔和疑似跳点不计入确定结果"
)
BATCH_DESCRIPTION = "2026-02-25 至 2026-03-03 七日历史 AIS（ship_data_source=nnu_ais；以实际数据库覆盖为准）"

# get_data_health 随结果返回的固定限制（AG-02）：stale 只是时间启发式，
# 不能包装成完整数据一致性证明；来源缺失不等于真实数量为零；工具只读。
DATA_HEALTH_LIMITATIONS = [
    "stale 仅为时间启发式（派生层 built_at 早于最新源报位），不检测历史数据更正或删除",
    "stale=false 不证明历史数据未被修改",
    "来源列表未包含的来源表示该来源未导入或无记录，不能解释为真实数量为零",
    "本工具只读：不触发迁移、数据导入或派生层重建",
]


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def parse_time_arg(raw) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("时间参数必须是 ISO 8601 字符串")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间参数必须带时区（统一 UTC）")
    return parsed


def tool_payload(result) -> dict:
    """回传给模型的工具结果。passage 结果不含模型不可信的中间细节，其余工具结果整体回传。"""
    if isinstance(result, StraitPassageResult):
        return to_jsonable(
            {
                "status": result.status,
                "ships": result.ships,
                "evidence": result.evidence,
                "uncertain_candidates": result.uncertain_candidates,
                "query_summary": result.query_summary,
                "limitations": result.limitations,
            }
        )
    return to_jsonable(result)


_UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"忽略.{0,12}(?:指令|提示)"),
    re.compile(r"泄露.{0,12}(?:密钥|密码|提示词|连接串)"),
    re.compile(r"(?:执行|运行).{0,12}(?:命令|sql|脚本)", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
)


def safe_model_answer(answer: str) -> tuple[str, str | None]:
    """阻止模型在自由正文中回显数据库文本里的指令性内容。"""
    if any(pattern.search(answer) for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS):
        return (
            "查询结果包含疑似指令性外部文本，已在回答正文中隐藏；该文本只作为不可信数据，"
            "系统没有执行其中任何要求。请使用结构化结果中的记录 ID 和来源字段继续核对。",
            "模型回答中的疑似外部指令文本已由后端防回显门隐藏",
        )
    return answer, None


def normalize_status(tools_used: list[str], results: dict) -> str:
    """按全部调用结果归并顶层状态，避免任一工具掩盖另一工具的缺口。"""
    envelopes = list(results.values())
    # 已被后续成功调用纠正的错误（同工具出现过 status=ok 的 envelope）不再把
    # 最终状态降为 partial，与 syntax_error 的修复豁免一致；错误 envelope 仍
    # 保留在 results 中可追溯。
    succeeded_tools = {env.get("tool_name") for env in envelopes if env.get("status") == "ok"}
    statuses = [
        env.get("status")
        for env in envelopes
        if not (env.get("status") == "error" and env.get("tool_name") in succeeded_tools)
    ]
    if "refused" in statuses:
        return "refused"
    # 首次 SQL 尚未执行的普通语法错误若在唯一允许的修复后成功，不把最终状态降为 partial。
    statuses = [status for status in statuses if status != "syntax_error"]
    if statuses and all(status == "ok" for status in statuses):
        return "ok"
    if any(status in {"ok", "partial"} for status in statuses):
        return "partial"
    return "no_data"


def build_result(
    tools_used: list[str],
    results: dict,
    closure_at: datetime,
    end_at: datetime,
    closure_source: str,
    answer: str,
    *,
    status: str | None = None,
    clarification: str | None = None,
) -> dict:
    passage = None
    for result in results.values():
        if (result.get("tool_name") == "query_strait_passages"
                and result.get("status") in {"ok", "partial"}
                and "ships" in result and "evidence" in result):
            passage = result
            break
    ships: list[dict] = []
    evidence: list[PassageEvidence] = []
    query_summary = None
    if passage is not None:
        ships = passage["ships"]
        evidence = [
            PassageEvidence(
                evidence_id=item["evidence_id"],
                ship_id=item["ship_id"],
                direction=item["direction"],
                start_fix=item["start_fix"],
                completion_fix=item["completion_fix"],
                observed_completion_at=item["observed_completion_at"],
            )
            for item in passage["evidence"]
        ]
        query_summary = passage["query_summary"]

    limitations: list[str] = []
    for result in results.values():
        for item in result.get("limitations", []):
            if item not in limitations:
                limitations.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status or normalize_status(tools_used, results),
        "answer": answer,
        "context": {
            "schema_version": SCHEMA_VERSION,
            "batch": BATCH_DESCRIPTION,
            "ship_data_source": "nnu_ais",
            "closure_at": closure_at,
            "end_at": end_at,
            "closure_source": closure_source,
            "passage_rule": PASSAGE_RULE,
        },
        "ships": ships,
        "evidence": evidence,
        "query_summary": query_summary,
        "tools_used": tools_used,
        "results": results,
        "limitations": limitations,
        "clarification": clarification,
    }
