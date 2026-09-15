"""智能体编排 runner：模型工具调用循环 + 后端只读查询 + 响应组装。

严格遵守 docs/agent_integration.md（契约 v2）的预算与规则：
整体 60 秒、最多 4 轮模型请求、2 次业务工具执行；
结构化船只、计数和证据直接来自 query_strait_passages 的后端结果，不经模型。
"""
import json
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta

from openai import APITimeoutError
from sqlalchemy.orm import Session

from backend.app.services.agent.config import DEFAULT_CLOSURE_AT, DEFAULT_CLOSURE_SOURCE, DEFAULT_WINDOW
from backend.app.services.agent.model_client import default_model
from backend.app.services.agent.strait_passages import (
    SCHEMA_VERSION,
    PassageEvidence,
    StraitPassageResult,
    query_strait_passages,
)

OVERALL_BUDGET_SECONDS = 60.0
MAX_MODEL_ROUNDS = 4
MAX_TOOL_EXECUTIONS = 2
MAX_INVALID_CORRECTIONS = 2  # 未知工具/参数解析失败等允许的有限纠正次数

PASSAGE_RULE = (
    "完整穿越判定：纬度 25.8–27.1°N 带内，经度从 56.2°E 一侧变为 56.7°E 另一侧"
    "（门线之间保留状态），完成侧首个报位时间 ∈ [closure_at, end_at)；"
    "口径出处 sim_ais_demo/tools/verify_news_alignment.py"
)
BATCH_DESCRIPTION = "当前教学模拟批次 sim_ais_demo/output_news_aligned（ship_data_source=simulation）"


class AgentTimeoutError(RuntimeError):
    """整体执行超时（映射 504 AGENT_TIMEOUT）。"""


class AgentInvalidResponseError(RuntimeError):
    """模型调用或回答反复不符合契约（映射 502 AGENT_INVALID_RESPONSE）。"""


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_strait_passages",
        "description": (
            "查询数据库中在 [closure_at, end_at) 窗口内观测完成的海峡完整通行"
            "（仅当前教学模拟批次，只读查询）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "closure_at": {
                    "type": "string",
                    "description": (
                        "封锁起始时刻，ISO 8601，必须带时区（统一 UTC），"
                        "如 2026-02-28T15:00:00+00:00"
                    ),
                },
                "end_at": {
                    "type": "string",
                    "description": (
                        "窗口结束时刻，ISO 8601，必须带时区（统一 UTC）；"
                        "end_at 必须晚于 closure_at，窗口最长 24 小时"
                    ),
                },
            },
        },
    },
}

SYSTEM_PROMPT = """你是霍尔木兹海峡船舶回放教学项目的问答助手。请严格遵守以下边界：

1. 数据边界：所有船舶与船位都是教学模拟数据（ship_data_source=simulation），不是真实 AIS；
   不得把模拟船与真实新闻事件中的船舶按名称关联，不得推导真实因果。
2. 你只有一个工具 query_strait_passages：查询数据库中在 [closure_at, end_at) 窗口内
   观测完成的海峡完整通行（两侧门线 56.2°E / 56.7°E 之间的完整侧别变化）。
   时间必须带时区（统一 UTC），窗口最长 24 小时。
3. 工作方式（必须遵守）：回答任何通行/船舶数量问题前，你必须先调用一次
   query_strait_passages 工具。用户没有给出时间时，不要向用户反问时间，
   直接不带时间参数（或只带已知参数）调用工具，后端会自动使用默认封锁时刻
   （当前模拟批次假设的警告响应起点）和 24 小时窗口。
4. 回答必须完全基于工具返回的结果（船只 ID、名称、数量、证据编号 P1…）；
   SQL、距离和通行判断已由后端完成，你不自行计算或编造。
5. 工具返回零匹配时，如实回答“指定模拟数据范围内未发现符合规则的完整通行”，
   不得暗示封锁有效或编造船只。
6. 窗口内无报位（no_data）时，说明数据覆盖不足，不能解释成“没有船通过”。
7. 回答中保留事实边界：不虚构精确封锁时刻，不虚构新闻细节。"""


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _tool_payload(result: StraitPassageResult) -> dict:
    """回传给模型的工具结果（不含模型不可信的中间细节）。"""
    return _jsonable(
        {
            "status": result.status,
            "ships": result.ships,
            "evidence": result.evidence,
            "uncertain_candidates": result.uncertain_candidates,
            "query_summary": result.query_summary,
            "limitations": result.limitations,
        }
    )


def _parse_time_arg(raw) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("时间参数必须是 ISO 8601 字符串")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间参数必须带时区（统一 UTC）")
    return parsed


def _execute_tool(
    db: Session,
    arguments: str,
    forced_closure_at: datetime | None = None,
    forced_end_at: datetime | None = None,
) -> tuple[StraitPassageResult | None, str | None]:
    """执行白名单工具。返回 (结果, 错误消息)；错误消息供回传模型纠正。

    请求显式提供时间时（forced_*），以请求为准，模型自拟的时间参数忽略。
    """
    if forced_closure_at is not None and forced_end_at is not None:
        closure_at, end_at = forced_closure_at, forced_end_at
    else:
        try:
            args = json.loads(arguments or "{}")
            if not isinstance(args, dict):
                raise ValueError("工具参数必须是 JSON 对象")
            closure_at = _parse_time_arg(args.get("closure_at"))
            end_at = _parse_time_arg(args.get("end_at"))
        except (json.JSONDecodeError, ValueError) as exc:
            return None, f"工具参数解析失败：{exc}。请用 ISO 8601 带时区时间重试。"

        if closure_at is None:
            closure_at = DEFAULT_CLOSURE_AT
        if end_at is None:
            end_at = closure_at + DEFAULT_WINDOW

    try:
        return query_strait_passages(db, closure_at, end_at), None
    except ValueError as exc:
        return None, f"查询参数不合法：{exc}"


def _build_result(
    query_result: StraitPassageResult,
    closure_at: datetime,
    end_at: datetime,
    closure_source: str,
    answer: str,
) -> dict:
    evidence = [
        PassageEvidence(
            evidence_id=item.evidence_id,
            ship_id=item.ship_id,
            direction=item.direction,
            start_fix=item.start_fix,
            completion_fix=item.completion_fix,
            observed_completion_at=item.observed_completion_at,
        )
        for item in query_result.evidence
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": query_result.status,
        "answer": answer,
        "context": {
            "schema_version": SCHEMA_VERSION,
            "batch": BATCH_DESCRIPTION,
            "ship_data_source": "simulation",
            "closure_at": closure_at,
            "end_at": end_at,
            "closure_source": closure_source,
            "passage_rule": PASSAGE_RULE,
        },
        "ships": query_result.ships,
        "evidence": evidence,
        "query_summary": query_result.query_summary,
        "limitations": query_result.limitations,
        "clarification": None,
    }


def run_agent(
    db: Session,
    client,
    question: str,
    closure_at: datetime | None = None,
    end_at: datetime | None = None,
    trace: list | None = None,
) -> dict:
    """编排一次完整问答。异常由 API 层映射为契约错误码。

    trace 可选：记录模型工具调用（工具名与原始参数），供联调脚本展示。
    """
    deadline = time.monotonic() + OVERALL_BUDGET_SECONDS

    # 请求显式提供的时间为权威值；模型参数只用于请求未提供的字段
    request_closure_at = closure_at
    request_end_at = end_at

    if closure_at is None:
        closure_at = DEFAULT_CLOSURE_AT
        closure_source = DEFAULT_CLOSURE_SOURCE
    else:
        closure_source = "用户输入"
    if end_at is None:
        end_at = closure_at + DEFAULT_WINDOW

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    tool_executions = 0
    invalid_corrections = 0
    query_result: StraitPassageResult | None = None

    for _round in range(MAX_MODEL_ROUNDS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTimeoutError("智能体执行超过 60 秒整体预算")
        try:
            completion = client.chat.completions.create(
                model=default_model(),
                messages=messages,
                tools=[TOOL_SCHEMA],
                tool_choice="auto",
                timeout=min(30.0, remaining),
            )
        except APITimeoutError as exc:
            raise AgentTimeoutError("模型请求超时") from exc

        choice = completion.choices[0]
        message = choice.message
        messages.append(message)

        if not message.tool_calls:
            # 模型最终回答：必须基于已执行的工具结果
            if query_result is None:
                raise AgentInvalidResponseError("模型未调用工具直接给出回答")
            if not message.content or not message.content.strip():
                raise AgentInvalidResponseError("模型最终回答为空")
            return _build_result(
                query_result, closure_at, end_at, closure_source, message.content.strip()
            )

        # 处理工具调用（每轮通常一个）
        for tool_call in message.tool_calls:
            if trace is not None:
                trace.append(
                    {
                        "tool": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    }
                )
            if tool_call.function.name != "query_strait_passages":
                invalid_corrections += 1
                if invalid_corrections > MAX_INVALID_CORRECTIONS:
                    raise AgentInvalidResponseError("模型反复调用未知工具")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            f"未知工具 {tool_call.function.name}。"
                            "只能调用 query_strait_passages。"
                        ),
                    }
                )
                continue
            if tool_executions >= MAX_TOOL_EXECUTIONS:
                raise AgentInvalidResponseError("工具执行次数超过 2 次预算")
            result, error = _execute_tool(
                db,
                tool_call.function.arguments,
                forced_closure_at=request_closure_at,
                forced_end_at=request_end_at,
            )
            if error is not None:
                invalid_corrections += 1
                if invalid_corrections > MAX_INVALID_CORRECTIONS:
                    raise AgentInvalidResponseError("模型工具参数反复不合法")
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": error}
                )
                continue
            tool_executions += 1
            query_result = result
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(_tool_payload(result), ensure_ascii=False),
                }
            )

    raise AgentInvalidResponseError(
        f"模型在 {MAX_MODEL_ROUNDS} 轮请求预算内未给出最终回答"
    )
