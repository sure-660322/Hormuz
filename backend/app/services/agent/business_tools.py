"""LC-04：8 个现有只读业务服务包装为原生 LangChain Tools。

直接包装已验证的服务层函数（strait_passages/ship_search/ship_tracks/event_context/
data_health/dwell_query/encounters_query/event_ship_links_query），不重写业务算法；
工具描述负责告诉模型何时使用以及结果边界。执行与错误降级统一走 record_envelope。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.services import data_health as health_service
from backend.app.services.agent.config import DEFAULT_WINDOW
from backend.app.services.agent.dwell_query import run_dwell_query
from backend.app.services.agent.encounters_query import run_encounters_query
from backend.app.services.agent.event_context import get_event_context
from backend.app.services.agent.event_ship_links_query import run_event_ship_links_query
from backend.app.services.agent.results import DATA_HEALTH_LIMITATIONS, parse_time_arg, tool_payload
from backend.app.services.agent.request_guard import reserve_tool
from backend.app.services.agent.serialization import to_jsonable
from backend.app.services.agent.ship_search import (
    MAX_LIMIT as SHIP_SEARCH_MAX_LIMIT,
    search_ships,
)
from backend.app.services.agent.ship_tracks import get_ship_track
from backend.app.services.agent.track_observation import track_observation
from backend.app.services.agent.strait_passages import query_strait_passages
from backend.app.services.area_activity.context import resolve_area_context

_JSON_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def args_model(name: str, schema: dict) -> type[BaseModel]:
    """把 JSON Schema 参数定义转换为 Pydantic 模型（LangChain args_schema）。"""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    fields: dict[str, Any] = {}
    for prop, spec in properties.items():
        enum = spec.get("enum")
        if enum:
            annotation: Any = Literal[*enum]
        else:
            annotation = _JSON_TYPE_MAP.get(spec.get("type"), Any)
        if prop in required:
            default: Any = ...
        else:
            annotation = annotation | None
            default = None
        fields[prop] = (annotation, Field(default=default, description=spec.get("description", "")))
    return create_model(f"{name}_args", **fields)


def error_observation(code: str, message: str) -> str:
    """工具错误降级为可理解的 observation（docs/langchain_agent_v1_plan.md §6）。"""
    return json.dumps({"status": "error", "code": code, "message": message}, ensure_ascii=False)


def record_envelope(state: dict, tool_name: str, payload: dict) -> str:
    """统一记录工具 envelope 到 state（results/tools_used），返回 observation JSON。"""
    with state.setdefault("lock", threading.RLock()):
        state["call_sequence"] += 1
        call_id = f"call_{state['call_sequence']:03d}"
        envelope = to_jsonable({"call_id": call_id, "tool_name": tool_name, **payload})
        if tool_name not in state["tools_used"]:
            state["tools_used"].append(tool_name)
        state["results"][call_id] = envelope
    if tool_name == "get_ship_track":
        return track_observation(envelope)
    return json.dumps(envelope, ensure_ascii=False)


def _execute_guarded(state: dict, tool_name: str, func) -> str:
    """工具执行统一兜底：参数/数据库/未知异常都降级为 observation，不产生 500。"""
    denied = reserve_tool(state)
    if denied is not None:
        return record_envelope(state, tool_name, denied)
    try:
        payload = func()
    except ValueError as exc:
        return record_envelope(state, tool_name, {
            "status": "error", "code": "INVALID_TOOL_ARGS", "message": f"工具参数不合法：{exc}",
        })
    except SQLAlchemyError:
        return record_envelope(state, tool_name, {
            "status": "error", "code": "DATABASE_UNAVAILABLE", "message": "数据库暂时不可用，请稍后重试",
        })
    except Exception as exc:  # noqa: BLE001 工具内部任何异常不得导致未处理 500
        return record_envelope(state, tool_name, {
            "status": "error", "code": "TOOL_ERROR", "message": f"工具执行失败：{type(exc).__name__}",
        })
    envelope = {"status": "ok", **payload}
    return record_envelope(state, tool_name, envelope)


def _resolve_window(
    windowed: bool,
    args: dict,
    closure_at: datetime,
    end_at: datetime,
    forced_window: bool,
) -> tuple[datetime | None, datetime | None]:
    """与 v4 契约相同的时间窗语义（请求显式窗口为权威值）。"""
    if not windowed:
        return None, None
    if forced_window:
        return closure_at, end_at
    raw_start = args.get("closure_at") or args.get("start_at")
    window_start = parse_time_arg(raw_start) or closure_at
    window_end = parse_time_arg(args.get("end_at")) or (window_start + DEFAULT_WINDOW)
    return window_start, window_end


def make_business_tools(
    db: Session,
    closure_at: datetime,
    end_at: datetime,
    forced_window: bool,
    state: dict,
    area_context: object | None = None,
) -> list[StructuredTool]:
    """构造 11 个只读业务工具；db/窗口/当前区域/state 绑定到当前请求。

    area_context 为本轮请求区域（None → 版本化默认分析区域），只在请求内生效；
    工具显式给出的矩形只作用于该次调用。
    """

    def _window_args(args: dict) -> dict:
        return {key: value for key, value in args.items() if value is not None}

    def _query_strait_passages(closure_at: str | None = None, end_at: str | None = None,
                              ship_id: int | None = None) -> str:
        def run():
            args = _window_args({"closure_at": closure_at, "end_at": end_at})
            window = _resolve_window(True, args, globals_closure_at, globals_end_at, forced_window)
            return tool_payload(query_strait_passages(db, window[0], window[1], ship_id=ship_id))
        return _execute_guarded(state, "query_strait_passages", run)

    def _search_ships(keyword: str, limit: int | None = None) -> str:
        def run():
            if not keyword or not keyword.strip():
                raise ValueError("keyword 必填（船舶名称/MMSI/IMO/船型/船旗关键字）")
            return tool_payload(search_ships(db, keyword=keyword, limit=limit or 10))
        return _execute_guarded(state, "search_ships", run)

    def _get_ship_track(ship_id: int, start_at: str | None = None, end_at: str | None = None) -> str:
        def run():
            args = _window_args({"start_at": start_at, "end_at": end_at})
            window = _resolve_window(True, args, globals_closure_at, globals_end_at, forced_window)
            return tool_payload(get_ship_track(db, ship_id=ship_id, start_at=window[0], end_at=window[1]))
        return _execute_guarded(state, "get_ship_track", run)

    def _get_event_context(
        event_id: str | None = None,
        keyword: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> str:
        def run():
            args = _window_args({"start_at": start_at, "end_at": end_at})
            window = _resolve_window(True, args, globals_closure_at, globals_end_at, forced_window)
            return tool_payload(get_event_context(
                db, event_id=event_id, keyword=keyword,
                start_at=window[0], end_at=window[1],
            ))
        return _execute_guarded(state, "get_event_context", run)

    def _get_data_health() -> str:
        def run():
            result = health_service.get_data_health(db)
            return {**result, "limitations": list(DATA_HEALTH_LIMITATIONS)}
        return _execute_guarded(state, "get_data_health", run)

    def _query_ship_dwell(
        kind: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        limit: int | None = None,
    ) -> str:
        def run():
            args = _window_args({"kind": kind, "start_at": start_at, "end_at": end_at, "limit": limit})
            return tool_payload(run_dwell_query(db, args))
        return _execute_guarded(state, "query_ship_dwell", run)

    def _query_encounters(
        start_at: str | None = None,
        end_at: str | None = None,
        max_distance_nm: float | None = None,
        limit: int | None = None,
    ) -> str:
        def run():
            args = _window_args({
                "start_at": start_at, "end_at": end_at,
                "max_distance_nm": max_distance_nm, "limit": limit,
            })
            return tool_payload(run_encounters_query(db, args))
        return _execute_guarded(state, "query_encounters", run)

    def _query_event_ship_links(
        event_id: str | None = None,
        ship_id: int | None = None,
        link_type: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> str:
        def run():
            args = _window_args({
                "event_id": event_id, "ship_id": ship_id, "link_type": link_type,
                "start_at": start_at, "end_at": end_at,
            })
            return tool_payload(run_event_ship_links_query(db, args))
        return _execute_guarded(state, "query_event_ship_links", run)

    # 闭包内引用请求级窗口（避免与工具参数同名遮蔽）
    globals_closure_at, globals_end_at = closure_at, end_at

    time_param = {
        "type": "string",
        "description": "ISO 8601，必须带时区（统一 UTC）；省略时用后端默认封锁时刻与 24 小时窗口",
    }
    window_params = {
        "closure_at": {**time_param, "description": "封锁起始时刻，ISO 8601，必须带时区（统一 UTC），如 2026-02-28T15:00:00+00:00"},
        "end_at": {**time_param, "description": "窗口结束时刻，ISO 8601，必须带时区（统一 UTC）；end_at 必须晚于 closure_at，窗口最长 24 小时"},
    }
    tools = [
        StructuredTool.from_function(
            func=_query_strait_passages,
            name="query_strait_passages",
            description=(
                "以历史 AIS 报位查询 [closure_at, end_at) 内的海峡虚拟双门线观测通行"
                "（有界只读查询，疑似跳点/长间隔分列）。回答通行/「多少船通过」类问题前必须调用；"
                "用户没给时间时不要反问，不带时间参数调用，后端自动用默认封锁时刻和 24 小时窗口"
            ),
            args_schema=args_model("query_strait_passages", {
                "type": "object", "properties": {
                    **window_params,
                    "ship_id": {"type": "integer", "description": "可选：仅判断一艘数据库船；先用 search_ships 确认 ID"},
                },
            }),
        ),
        StructuredTool.from_function(
            func=_search_ships,
            name="search_ships",
            description=(
                "按关键字检索有 nnu_ais 历史 AIS 报位的船舶（匹配船名/MMSI/IMO/callsign/船型/船旗），"
                "返回 ship_id 等字段；轨迹或通行问题先用它确认船 ID"
            ),
            args_schema=args_model("search_ships", {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "检索关键字，如船名片段、MMSI、IMO、船型（如 Tanker）或船旗"},
                    "limit": {"type": "integer", "description": f"返回条数上限，默认 10，最大 {SHIP_SEARCH_MAX_LIMIT}"},
                },
                "required": ["keyword"],
            }),
        ),
        StructuredTool.from_function(
            func=_get_ship_track,
            name="get_ship_track",
            description=(
                "查询指定船只在窗口内的 nnu_ais 实测轨迹报位（时间/经纬度/航速/航向，只读）；"
                "轨迹问题先用 search_ships 拿 ship_id 再调用"
            ),
            args_schema=args_model("get_ship_track", {
                "type": "object",
                "properties": {
                    "ship_id": {"type": "integer", "description": "船 ID（ships.id；先用 search_ships 检索确认）"},
                    "start_at": time_param,
                    "end_at": time_param,
                },
                "required": ["ship_id"],
            }),
        ),
        StructuredTool.from_function(
            func=_get_event_context,
            name="get_event_context",
            description=(
                "查询新闻聚合事件及关联真实报道（事件 ID 精确查询或关键字模糊查询，"
                "可选事件时间窗）；事件为报道聚合，不能仅凭船名与 AIS 船舶关联"
            ),
            args_schema=args_model("get_event_context", {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "事件 ID（如 evt_001），与 keyword 二选一"},
                    "keyword": {"type": "string", "description": "检索关键字（匹配事件标题/摘要/位置文本），与 event_id 二选一"},
                    "start_at": {**time_param, "description": "可选时间窗开始（按事件时间过滤，日级叙述事件按报道日期兜底），ISO 8601，必须带时区"},
                    "end_at": time_param,
                },
            }),
        ),
        StructuredTool.from_function(
            func=_get_data_health,
            name="get_data_health",
            description=(
                "只读查询数据健康：各 data_source 的报位数/船数/覆盖区间/中位间隔，"
                "以及 ship_tracks/ship_dwell/encounters/event_ship_links 四张派生表的"
                "行数、构建时间、构建参数和 stale 状态（stale 仅为时间启发式）；"
                "不触发迁移、导入或派生层重建"
            ),
            args_schema=args_model("get_data_health", {"type": "object", "properties": {}}),
        ),
        StructuredTool.from_function(
            func=_query_ship_dwell,
            name="query_ship_dwell",
            description=(
                "只读查询停留派生层（ship_dwell）的预计算停留段：哪些船在何时"
                "锚泊/漂航/慢速航行及持续时长；阈值由构建参数决定，查询层不可调整，"
                "不触发任何重建；status=not_built 时表示派生层尚未构建，如实说明"
            ),
            args_schema=args_model("query_ship_dwell", {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["at_anchor", "drift", "slow_transit"],
                             "description": "停留类型：at_anchor=锚泊、drift=漂航、slow_transit=慢速航行；省略时返回全部类型"},
                    "start_at": {**time_param, "description": "可选窗口开始，与 end_at 成对，窗口最长 24 小时；省略时返回整个已构建批次"},
                    "end_at": time_param,
                    "limit": {"type": "integer", "description": "返回条数上限，默认 50，最大 500；超出的匹配保留计数并标记 truncated"},
                },
            }),
        ),
        StructuredTool.from_function(
            func=_query_encounters,
            name="query_encounters",
            description=(
                "只读查询相遇派生层（encounters）的预计算船对：哪些船在何时段内"
                "时空接近、最近距离多少；接近不等于有交互；max_distance_nm 只能小于等于"
                "构建阈值（超过会被拒绝而不是返回零结果）；只读，绝不触发相遇重建"
            ),
            args_schema=args_model("query_encounters", {
                "type": "object",
                "properties": {
                    "start_at": {**time_param, "description": "可选窗口开始，与 end_at 成对，窗口最长 24 小时；省略时返回全部已构建船对"},
                    "end_at": time_param,
                    "max_distance_nm": {"type": "number", "description": "按最小距离过滤（海里）；只能小于等于构建阈值（params.distance_nm），省略时按构建阈值不过滤"},
                    "limit": {"type": "integer", "description": "返回条数上限，默认 50，最大 500；超出的匹配保留计数并标记 truncated"},
                },
            }),
        ),
        StructuredTool.from_function(
            func=_query_event_ship_links,
            name="query_event_ship_links",
            description=(
                "只读查询事件—船舶关联派生层（event_ship_links）：按事件查原文提及船名"
                "（mentioned，文本证据，无 ship_id）或已构建的时空邻近（observed），"
                "或按船反查 observed 关联；七日 AIS 的 observed 尚未重建；只读"
            ),
            args_schema=args_model("query_event_ship_links", {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "事件 ID（如 evt_001），与 ship_id 二选一；查询该事件下的 mentioned/observed 关联"},
                    "ship_id": {"type": "integer", "description": "船 ID（ships.id，先用 search_ships 检索确认），与 event_id 二选一；反查该船被哪些事件 observed 关联"},
                    "link_type": {"type": "string", "enum": ["observed", "mentioned"],
                                  "description": "关联类型：observed=已构建轨迹时空邻近；mentioned=新闻原文船名文本（仅支持 event_id 方向）；省略默认 observed"},
                    "start_at": {**time_param, "description": "可选窗口开始，仅按船反查（ship_id）时可用，与 end_at 成对，窗口最长 24 小时"},
                    "end_at": time_param,
                },
            }),
        ),
    ]
    # 阶段三（issue #41）追加：三个区域活动工具。既有 8 个工具不改动；
    # 区域上下文在本请求内固定，延迟导入避免与 area_tools 的模块级依赖成环。
    from backend.app.services.agent.area_tools import make_area_tools

    tools.extend(make_area_tools(db, state, resolve_area_context(area_context)))
    return tools
