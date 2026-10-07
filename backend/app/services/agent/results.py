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
BATCH_DESCRIPTION = "nnu_ais 历史 AIS：原七日全船批次与独立单船案例补充；实际查询覆盖以工具结果为准，不能将单船覆盖解释为海峡全量覆盖"

# get_data_health 随结果返回的固定限制（AG-02）：stale 只是时间启发式，
# 不能包装成完整数据一致性证明；来源缺失不等于真实数量为零；工具只读。
DATA_HEALTH_LIMITATIONS = [
    "stale 仅为时间启发式（派生层 built_at 早于最新源报位），不检测历史数据更正或删除",
    "stale=false 不证明历史数据未被修改",
    "来源列表未包含的来源表示该来源未导入或无记录，不能解释为真实数量为零",
    "本工具只读：不触发迁移、数据导入或派生层重建",
]

# 区域活动工具 → analysis_actions.mode（工具名与 services/agent/area_tools.py 一致）。
# 只有 status ∈ {ok, partial} 的调用才生成「查看区域分析」动作；同名工具多次调用只保留最后一次。
AREA_TOOL_MODES = {
    "query_area_ship_snapshot": "snapshot",
    "query_area_ship_activity": "activity",
    "compare_area_ship_activity": "compare",
}


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


def _area_action_query(mode: str, query: dict, area: dict) -> dict:
    """「查看区域分析」动作的查询回显：与工具结果同一区域与时间，不做二次推断。

    边界恒为实际生效的四个边界；area_id 归一化为 hormuz_core_v1（默认区域）或
    custom（自定义矩形）——面板自带的 area_id/label 仍保留在 results[call_id].area 中。
    """
    filters = query.get("filters") if isinstance(query.get("filters"), dict) else {}
    is_default = area.get("is_default", query.get("area_is_default"))
    action = {
        "west": area.get("west", query.get("west")),
        "south": area.get("south", query.get("south")),
        "east": area.get("east", query.get("east")),
        "north": area.get("north", query.get("north")),
        "area_id": area.get("area_id", query.get("area_id")) if is_default else "custom",
        "area_version": area.get("version", query.get("area_version")),
        "area_is_default": is_default,
        "ship_types": filters.get("ship_types"),
        "batch_ids": filters.get("batch_ids"),
    }
    if mode == "snapshot":
        action["at"] = query.get("at")
    elif mode == "activity":
        action["start_at"] = query.get("start_at")
        action["end_at"] = query.get("end_at")
    else:
        for key in ("start_a", "end_a", "start_b", "end_b"):
            action[key] = query.get(key)
    return action


def _area_action_summary(mode: str, envelope: dict) -> dict:
    """「查看区域分析」动作的有界摘要（完整结果仍在 results[call_id] 中）。"""
    summary = envelope.get("summary") if isinstance(envelope.get("summary"), dict) else {}
    limits = envelope.get("limits") if isinstance(envelope.get("limits"), dict) else {}
    query = envelope.get("query") if isinstance(envelope.get("query"), dict) else {}
    status = envelope.get("status")
    if mode == "snapshot":
        return {
            "status": status,
            "in_area_count": summary.get("in_area_count"),
            "listed_ship_count": summary.get("listed_ship_count"),
            "unlisted_ship_count": summary.get("unlisted_ship_count"),
            "out_of_area_fresh_count": summary.get("out_of_area_fresh_count"),
            "stale_fix_count": summary.get("stale_fix_count"),
            "freshness_seconds": summary.get("freshness_seconds"),
            "list_truncated": limits.get("list_truncated"),
        }
    if mode == "activity":
        window = query.get("window") if isinstance(query.get("window"), dict) else {}
        return {
            "status": status,
            "ships_observed": summary.get("ships_observed"),
            "observed_entry_count": summary.get("observed_entry_count"),
            "observed_exit_count": summary.get("observed_exit_count"),
            "observed_ship_hours": summary.get("observed_ship_hours"),
            "visit_count": summary.get("visit_count"),
            "window_days": window.get("days"),
            "window_length_hours": window.get("length_hours"),
            "visits_not_shown": limits.get("visits_not_shown"),
            "detail_truncated": limits.get("detail_truncated"),
        }
    metrics = {
        item.get("key"): item
        for item in (envelope.get("metrics") or [])
        if isinstance(item, dict)
    }
    comparability = query.get("comparability") if isinstance(query.get("comparability"), dict) else {}
    ships = metrics.get("ships_observed") or {}
    entries = metrics.get("observed_entry_count") or {}
    return {
        "status": status,
        "ships_observed_a": ships.get("a"),
        "ships_observed_b": ships.get("b"),
        "ships_observed_delta": ships.get("delta"),
        "ships_observed_change_rate": ships.get("change_rate"),
        "observed_entry_count_a": entries.get("a"),
        "observed_entry_count_b": entries.get("b"),
        "observed_entry_count_delta": entries.get("delta"),
        "observed_entry_count_change_rate": entries.get("change_rate"),
        "equal_length": comparability.get("equal_length"),
        "warnings": list(comparability.get("warnings") or []),
    }


def _area_analysis_actions(results: dict) -> list[dict]:
    """区域活动工具的成功调用 → 「查看区域分析」动作。

    列表追加，不重排其它类型的动作；同名工具多次调用只保留最后一次（按调用顺序）。
    """
    actions: list[dict] = []
    for call_id, envelope in results.items():
        tool_name = envelope.get("tool_name")
        mode = AREA_TOOL_MODES.get(tool_name)
        if mode is None or envelope.get("status") not in {"ok", "partial"}:
            continue
        query = envelope.get("query") if isinstance(envelope.get("query"), dict) else {}
        area = envelope.get("area") if isinstance(envelope.get("area"), dict) else {}
        action = {
            "type": "area_activity",
            "trigger": "suggested",
            "mode": mode,
            "query": _area_action_query(mode, query, area),
            "summary": _area_action_summary(mode, envelope),
            "tool": tool_name,
            "call_id": envelope.get("call_id") or call_id,
        }
        actions = [item for item in actions if item["tool"] != tool_name]
        actions.append(action)
    return actions


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

    # issue #40：从成功的统计/比较工具结果生成「通行分析」面板动作；
    # 每个动作绑定其所属调用自己的查询参数，不使用「当前最新结果」。
    # 方向统一规范为 API 语义（inbound/outbound），模型可能使用 east_to_west 等门线侧别别名。
    def _canonical_direction(value: object) -> object:
        return {"east_to_west": "inbound", "west_to_east": "outbound"}.get(value, value)

    analysis_actions: list[dict] = []
    for result in results.values():
        if result.get("status") not in {"ok", "partial"}:
            continue
        if result.get("tool_name") == "query_strait_passage_statistics" and "window" in result:
            analysis_actions.append({
                "type": "passage_analysis",
                "trigger": "suggested",
                "query": {
                    "mode": "single",
                    "start_at": result.get("start_at"),
                    "end_at": result.get("end_at"),
                    "ship_types": result.get("ship_types"),
                    "direction": _canonical_direction(result.get("direction")),
                },
                "summary": {
                    "status": result.get("status"),
                    "window": result.get("window"),
                    "daily": result.get("daily"),
                    "determination_version": result.get("determination_version"),
                    "limitations": result.get("limitations", []),
                },
            })
        elif result.get("tool_name") == "compare_strait_passage_statistics" and "metrics" in result:
            analysis_actions.append({
                "type": "passage_analysis",
                "trigger": "suggested",
                "query": {
                    "mode": "compare",
                    "a_start_at": (result.get("a_period") or {}).get("start_at"),
                    "a_end_at": (result.get("a_period") or {}).get("end_at"),
                    "b_start_at": (result.get("b_period") or {}).get("start_at"),
                    "b_end_at": (result.get("b_period") or {}).get("end_at"),
                    "ship_types": result.get("ship_types"),
                    "direction": _canonical_direction(result.get("direction")),
                },
                "summary": {
                    "status": result.get("status"),
                    "a_period": result.get("a_period"),
                    "b_period": result.get("b_period"),
                    "metrics": result.get("metrics"),
                    "a_avg_passages_per_day": result.get("a_avg_passages_per_day"),
                    "b_avg_passages_per_day": result.get("b_avg_passages_per_day"),
                    "windows_overlap": result.get("windows_overlap"),
                    "comparability_notes": result.get("comparability_notes"),
                    "determination_version": result.get("determination_version"),
                    "limitations": result.get("limitations", []),
                },
            })
    # 列表追加：区域活动动作不重排、不覆盖其它类型（如通行分析）的动作。
    analysis_actions.extend(_area_analysis_actions(results))

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
        "map_actions": [],
        "analysis_actions": analysis_actions,
    }
