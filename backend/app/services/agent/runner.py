"""智能体编排 runner：模型工具调用循环 + 后端只读查询 + 响应组装。

严格遵守 docs/agent_integration.md（契约 v3）的预算与规则：
整体 60 秒、最多 4 轮模型请求、3 次业务工具执行；
结构化船只、计数和证据直接来自后端工具结果，不经模型。
"""
import json
import time
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from typing import Any, Callable

from openai import APITimeoutError
from sqlalchemy.orm import Session

from backend.app.services import data_health as health_service
from backend.app.services.agent.config import (
    DEFAULT_CLOSURE_AT,
    DEFAULT_CLOSURE_SOURCE,
    DEFAULT_WINDOW,
    SCHEMA_VERSION,
)
from backend.app.services.agent.event_context import get_event_context
from backend.app.services.agent.model_client import default_model
from backend.app.services.agent.ship_search import (
    MAX_LIMIT as SHIP_SEARCH_MAX_LIMIT,
    search_ships,
)
from backend.app.services.agent.ship_tracks import get_ship_track
from backend.app.services.agent.strait_passages import (
    PassageEvidence,
    StraitPassageResult,
    query_strait_passages,
)

OVERALL_BUDGET_SECONDS = 60.0
MAX_MODEL_ROUNDS = 4
MAX_TOOL_EXECUTIONS = 3
MAX_INVALID_CORRECTIONS = 2  # 未知工具/参数解析失败等允许的有限纠正次数
MAX_HISTORY_TURNS = 10  # 多轮 history 最多携带的轮数（user/assistant 各算一轮）

PASSAGE_RULE = (
    "完整穿越判定：纬度 25.8–27.1°N 带内，经度从 56.2°E 一侧变为 56.7°E 另一侧"
    "（门线之间保留状态），完成侧首个报位时间 ∈ [closure_at, end_at)；"
    "口径出处 sim_ais_demo/tools/verify_news_alignment.py"
)
BATCH_DESCRIPTION = "当前教学模拟批次 sim_ais_demo/output_news_aligned（ship_data_source=simulation）"

# get_data_health 随结果返回的固定限制（AG-02）：stale 只是时间启发式，
# 不能包装成完整数据一致性证明；来源缺失不等于真实数量为零；工具只读。
DATA_HEALTH_LIMITATIONS = [
    "stale 仅为时间启发式（派生层 built_at 早于最新源报位），不检测历史数据更正或删除",
    "stale=false 不证明历史数据未被修改",
    "来源列表未包含的来源表示该来源未导入或无记录，不能解释为真实数量为零",
    "本工具只读：不触发迁移、数据导入或派生层重建",
]


class AgentTimeoutError(RuntimeError):
    """整体执行超时（映射 504 AGENT_TIMEOUT）。"""


class AgentInvalidResponseError(RuntimeError):
    """模型调用或回答反复不符合契约（映射 502 AGENT_INVALID_RESPONSE）。"""


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _parse_time_arg(raw) -> datetime | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("时间参数必须是 ISO 8601 字符串")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间参数必须带时区（统一 UTC）")
    return parsed


@dataclass
class AgentTool:
    """白名单工具定义：模型可见的 schema + 后端执行函数。

    execute 接收解析后的参数，返回工具结果对象；参数不合法时抛 ValueError，
    由循环回传纠正消息给模型。windowed=True 的工具接受请求强制的时间窗。
    """

    name: str
    description: str
    parameters: dict  # JSON Schema（properties + required）
    windowed: bool
    execute: Callable[..., Any]


def _run_passage(db: Session, args: dict, closure_at: datetime, end_at: datetime):
    return query_strait_passages(db, closure_at, end_at)


def _run_ship_search(db: Session, args: dict, closure_at: datetime, end_at: datetime):
    keyword = args.get("keyword")
    if not isinstance(keyword, str) or not keyword.strip():
        raise ValueError("keyword 必填（船舶名称/MMSI/IMO/船型/船旗关键字）")
    limit = args.get("limit")
    if limit is None:
        limit = 10
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit 必须是整数")
    return search_ships(db, keyword=keyword, limit=limit)


def _run_ship_track(db: Session, args: dict, closure_at: datetime, end_at: datetime):
    ship_id = args.get("ship_id")
    if not isinstance(ship_id, int) or isinstance(ship_id, bool):
        raise ValueError("ship_id 必填（整数；可先用 search_ships 按船名检索）")
    return get_ship_track(db, ship_id=ship_id, start_at=closure_at, end_at=end_at)


def _run_event_context(db: Session, args: dict, closure_at: datetime, end_at: datetime):
    event_id = args.get("event_id")
    if event_id is not None and not isinstance(event_id, str):
        raise ValueError("event_id 必须是字符串（如 evt_001）")
    keyword = args.get("keyword")
    if keyword is not None and not isinstance(keyword, str):
        raise ValueError("keyword 必须是字符串")
    return get_event_context(
        db,
        event_id=event_id,
        keyword=keyword,
        start_at=closure_at,
        end_at=end_at,
    )


def _run_data_health(db: Session, args: dict, closure_at: datetime, end_at: datetime):
    if args:
        raise ValueError("get_data_health 不接受参数")
    # 复用 P5 /api/data-health 的服务与 repository，不重写数据健康算法
    result = health_service.get_data_health(db)
    return {**result, "limitations": list(DATA_HEALTH_LIMITATIONS)}


TOOL_REGISTRY: dict[str, AgentTool] = {
    tool.name: tool
    for tool in [
        AgentTool(
            name="query_strait_passages",
            description=(
                "查询数据库中在 [closure_at, end_at) 窗口内观测完成的海峡完整通行"
                "（仅当前教学模拟批次，只读查询）"
            ),
            parameters={
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
            windowed=True,
            execute=_run_passage,
        ),
        AgentTool(
            name="search_ships",
            description=(
                "按关键字检索教学模拟批次的船舶（匹配船名/MMSI/IMO/callsign/船型/船旗），"
                "返回 ship_id 等字段；轨迹或通行问题先用它确认船 ID"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "检索关键字，如船名片段、MMSI、IMO、船型（如 Tanker）或船旗",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"返回条数上限，默认 10，最大 {SHIP_SEARCH_MAX_LIMIT}",
                    },
                },
                "required": ["keyword"],
            },
            windowed=False,
            execute=_run_ship_search,
        ),
        AgentTool(
            name="get_ship_track",
            description=(
                "查询指定模拟船只在 [start_at, end_at) 窗口内的全部轨迹报位"
                "（时间/经纬度/航速/航向，只读）"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ship_id": {
                        "type": "integer",
                        "description": "船 ID（ships.id；先用 search_ships 检索确认）",
                    },
                    "start_at": {
                        "type": "string",
                        "description": (
                            "窗口开始时刻，ISO 8601，必须带时区（统一 UTC）；"
                            "省略时用后端默认封锁时刻"
                        ),
                    },
                    "end_at": {
                        "type": "string",
                        "description": (
                            "窗口结束时刻，ISO 8601，必须带时区（统一 UTC）；"
                            "省略时取开始时刻后 24 小时；窗口最长 24 小时"
                        ),
                    },
                },
                "required": ["ship_id"],
            },
            windowed=True,
            execute=_run_ship_track,
        ),
        AgentTool(
            name="get_event_context",
            description=(
                "查询新闻聚合事件及关联真实报道（事件 ID 精确查询或关键字模糊查询）；"
                "事件是真实新闻数据，与模拟船相互独立，不得按船名关联"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "事件 ID（如 evt_001），与 keyword 二选一",
                    },
                    "keyword": {
                        "type": "string",
                        "description": (
                            "检索关键字（匹配事件标题/摘要/位置文本），与 event_id 二选一"
                        ),
                    },
                    "start_at": {
                        "type": "string",
                        "description": (
                            "可选时间窗开始（按事件时间过滤，日级叙述事件按报道日期兜底），"
                            "ISO 8601，必须带时区"
                        ),
                    },
                    "end_at": {
                        "type": "string",
                        "description": "可选时间窗结束，ISO 8601，必须带时区",
                    },
                },
            },
            windowed=True,
            execute=_run_event_context,
        ),
        AgentTool(
            name="get_data_health",
            description=(
                "只读查询数据健康：各 data_source 的报位数/船数/覆盖区间/中位间隔，"
                "以及 ship_tracks/ship_dwell/encounters/event_ship_links 四张派生表的"
                "行数、构建时间、构建参数和 stale 状态（stale 仅为时间启发式）；"
                "不触发迁移、导入或派生层重建"
            ),
            parameters={"type": "object", "properties": {}},
            windowed=False,
            execute=_run_data_health,
        ),
    ]
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
    for tool in TOOL_REGISTRY.values()
]

SYSTEM_PROMPT = f"""你是霍尔木兹海峡船舶回放教学项目的问答助手。请严格遵守以下边界：

1. 数据边界：所有船舶与船位都是教学模拟数据（ship_data_source=simulation），不是真实 AIS；
   events/news 是真实新闻聚合与报道。两个数据集相互独立：不得把模拟船与真实新闻事件中的
   船舶按名称关联为同一实体，不得推导真实因果。
2. 可用工具（全部是只读查询，时间参数必须带时区、统一 UTC）：
   - query_strait_passages：窗口内观测完成的海峡完整通行（两侧门线 56.2°E / 56.7°E 之间的
     完整侧别变化）。回答任何通行/“多少船通过”类问题前必须先调用它；
     用户没给时间时不要反问，不带时间参数调用，后端自动用默认封锁时刻和 24 小时窗口。
   - search_ships：按关键字检索模拟船，返回 ship_id。涉及具体船只（轨迹、身份、船型）时先调用。
   - get_ship_track：查询指定船 ID 在窗口内的轨迹报位。轨迹问题先用 search_ships 拿 ship_id 再调用。
   - get_event_context：按事件 ID 或关键字查询新闻事件及关联真实报道。任何新闻/事件问题必须调用它；
     回答事件时保留报道来源与链接，不补充报道没有的结论。
   - get_data_health：无参数，查询数据健康（各来源覆盖统计与四张派生表的构建状态/stale）。
     数据健康、覆盖范围、派生层新旧类问题必须调用它。stale 只是时间启发式：
     stale=true 表示派生层早于最新源报位、需要重建；stale=false 不证明历史数据未被修改；
     来源列表缺失表示该来源未导入，不能答成真实数量为零；该工具只读，不触发任何重建。
3. 工作方式（必须遵守）：回答任何数据问题前必须先调用相应工具；回答必须完全基于工具返回的
   结果（船只 ID、名称、数量、证据编号 P1…、事件 ID、story_id），不自行计算或编造。
   不得仅凭对话历史中的信息回答数据问题——即使之前的回答里给过船 ID 或事件结论，
   也必须重新调用工具核对后再回答。
4. 工具返回零匹配（no_match / 数量为 0）时，如实回答“指定模拟数据范围内未发现”，
   不得暗示封锁有效或编造船只；no_data（覆盖不足）时说明数据覆盖不足，
   不能解释成“没有船通过”或“没有事件”。
5. 事件时间精度：event_datetime 经常缺失（报道仅支持日级叙述），按 event_time_text 叙述，
   不虚构精确发生时刻。
6. 多轮对话中可以引用之前回答里的船 ID 或事件 ID 继续追问，但仍须为新的数据问题调用工具。"""


def _tool_payload(result) -> dict:
    """回传给模型的工具结果。passage 结果不含模型不可信的中间细节，其余工具结果整体回传。"""
    if isinstance(result, StraitPassageResult):
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
    return _jsonable(result)


def _execute_tool(
    db: Session,
    tool: AgentTool,
    arguments: str,
    closure_at: datetime,
    end_at: datetime,
    forced_window: bool,
) -> tuple[Any | None, str | None]:
    """执行白名单工具。返回 (结果, 错误消息)；错误消息供回传模型纠正。

    时间窗解析（仅 windowed 工具）：请求显式提供时间窗时（forced_window）
    以请求为准，模型自拟的时间参数忽略；否则用模型参数，缺省回退到后端
    默认封锁时刻和 24 小时窗口（传入的 closure_at/end_at）。
    """
    try:
        args = json.loads(arguments or "{}")
        if not isinstance(args, dict):
            raise ValueError("工具参数必须是 JSON 对象")
        if tool.windowed:
            if forced_window:
                window_start, window_end = closure_at, end_at
            else:
                raw_start = args.get("closure_at") or args.get("start_at")
                window_start = _parse_time_arg(raw_start) or closure_at
                window_end = _parse_time_arg(args.get("end_at")) or (
                    window_start + DEFAULT_WINDOW
                )
            result = tool.execute(db, args, window_start, window_end)
        else:
            result = tool.execute(db, args, None, None)
        return result, None
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"工具参数解析失败或查询参数不合法：{exc}。请核对参数后重试。"


def _normalize_status(tools_used: list[str], results: dict) -> str:
    """响应 status：passage 工具执行过时沿用其状态；否则按各工具状态归并。"""
    passage = results.get("query_strait_passages")
    if passage is not None:
        return passage["status"]
    statuses = [results[name]["status"] for name in tools_used if name in results]
    if statuses and all(status == "ok" for status in statuses):
        return "ok"
    if any(status == "ok" for status in statuses):
        return "partial"
    return "no_data"


def _build_result(
    tools_used: list[str],
    results: dict,
    closure_at: datetime,
    end_at: datetime,
    closure_source: str,
    answer: str,
) -> dict:
    passage = results.get("query_strait_passages")
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
    for name in tools_used:
        for item in results.get(name, {}).get("limitations", []):
            if item not in limitations:
                limitations.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": _normalize_status(tools_used, results),
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
        "ships": ships,
        "evidence": evidence,
        "query_summary": query_summary,
        "tools_used": tools_used,
        "results": results,
        "limitations": limitations,
        "clarification": None,
    }


def run_agent(
    db: Session,
    client,
    question: str,
    closure_at: datetime | None = None,
    end_at: datetime | None = None,
    history: list[dict] | None = None,
    trace: list | None = None,
) -> dict:
    """编排一次完整问答。异常由 API 层映射为契约错误码。

    history 可选：此前对话的 [{role: user|assistant, content}] 轮次，
    最多取最近 MAX_HISTORY_TURNS 轮，插在 system 与本次问题之间。
    trace 可选：记录模型工具调用（工具名与原始参数），供联调脚本展示。
    """
    deadline = time.monotonic() + OVERALL_BUDGET_SECONDS

    # 请求显式提供的时间为权威值；模型参数只用于请求未提供的字段
    forced_window = closure_at is not None and end_at is not None

    if closure_at is None:
        closure_at = DEFAULT_CLOSURE_AT
        closure_source = DEFAULT_CLOSURE_SOURCE
    else:
        closure_source = "用户输入"
    if end_at is None:
        end_at = closure_at + DEFAULT_WINDOW

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    tool_executions = 0
    invalid_corrections = 0
    tools_used: list[str] = []
    results: dict[str, Any] = {}

    for _round in range(MAX_MODEL_ROUNDS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AgentTimeoutError("智能体执行超过 60 秒整体预算")
        try:
            completion = client.chat.completions.create(
                model=default_model(),
                messages=messages,
                tools=TOOL_SCHEMAS,
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
            if not results:
                raise AgentInvalidResponseError("模型未调用工具直接给出回答")
            if not message.content or not message.content.strip():
                raise AgentInvalidResponseError("模型最终回答为空")
            return _build_result(
                tools_used,
                results,
                closure_at,
                end_at,
                closure_source,
                message.content.strip(),
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
            tool = TOOL_REGISTRY.get(tool_call.function.name)
            if tool is None:
                invalid_corrections += 1
                if invalid_corrections > MAX_INVALID_CORRECTIONS:
                    raise AgentInvalidResponseError("模型反复调用未知工具")
                available = "、".join(TOOL_REGISTRY)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            f"未知工具 {tool_call.function.name}。"
                            f"只能调用以下工具之一：{available}。"
                        ),
                    }
                )
                continue
            if tool_executions >= MAX_TOOL_EXECUTIONS:
                raise AgentInvalidResponseError("工具执行次数超过 3 次预算")
            result, error = _execute_tool(
                db,
                tool,
                tool_call.function.arguments,
                closure_at=closure_at,
                end_at=end_at,
                forced_window=forced_window,
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
            if tool.name not in tools_used:
                tools_used.append(tool.name)
            results[tool.name] = _tool_payload(result)
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
