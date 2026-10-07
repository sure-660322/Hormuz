"""阶段三（issue #41）：区域船舶活动与进出的三个只读智能体工具。

与手动 REST 入口共用同一个 service（backend/app/services/area_activity/service.py）：
工具只做「参数解析 + 当前区域上下文解析 + 明细列表裁剪 + 口径说明」，不重写任何算法；
同一参数下手动 API 与工具走同一 service 调用与同一版本化参数，结果一致。

三个工具：
- query_area_ship_snapshot    某历史时刻在分析区域内的船（有界列表 ≤50 艘）；
- query_area_ship_activity    时段内出现、观测进入/离开、累计船时与访问明细（≤30 条）；
- compare_area_ship_activity  同一区域同筛选的两期比较（指标/delta/change_rate/comparability）。

区域来源：本轮请求区域（area_context，来自前端面板）为权威值；工具显式给出
west/south/east/north 时只作用于该次调用，不改变前端当前区域。矩形跨度、跨 180°、
窗口长度等业务校验全部由 service 执行（与 REST 同口径，拒绝而不是截断）。

结果统一经 _execute_guarded 记录 envelope（status 沿用 ok/partial/no_data/error）；
参数与上限错误降级为 error envelope，不产生未处理异常。
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from backend.app.services.agent.business_tools import _execute_guarded, args_model
from backend.app.services.agent.results import parse_time_arg
from backend.app.services.area_activity import params as area_params
from backend.app.services.area_activity import service as area_service
from backend.app.services.area_activity.context import (
    AreaContext,
    area_context_payload,
    bounds_from_arguments,
)

# 工具返回给模型的明细上限（汇总不受影响；裁剪数量在 limits 中说明）
AGENT_SNAPSHOT_SHIP_LIMIT = 50
AGENT_VISIT_LIMIT = 30

_RECT_PARAM = {
    "type": "number",
    "description": (
        "分析矩形边界（度，半开：西/南含，东/北不含）；"
        "四个边界必须同时给出或同时省略，省略时使用当前请求区域"
    ),
}
_TIME_PARAM = {
    "type": "string",
    "description": "ISO 8601，必须带时区（统一 UTC），如 2026-02-28T15:00:00+00:00",
}
_SHIP_TYPE_PARAM = {
    "type": "array",
    "description": (
        "船型筛选，默认全部（不传）；用真实船型名（如 Tanker、油轮，精确匹配），"
        "或保留值 \"__missing__\"（船型缺失）、\"__unknown__\"（船型未知）、\"all\"（显式全部）；"
        "回答里把保留值表述为「缺失」「未知」，不要原样输出 __missing__/__unknown__"
    ),
}

# 船型保留值的解释口径：数据库真实取值可能是「未知」，与保留值字符串不同。
_SHIP_TYPE_NOTE = (
    "船型参数支持真实船型名与保留值（__missing__=船型缺失、__unknown__=船型未知、all=显式全部）；"
    "回答中把保留值表述为「缺失」「未知」，不要原样输出保留值字符串"
)

_RECT_PROPERTIES = {
    "west": {**_RECT_PARAM, "description": "西边界经度（-180..180）：" + _RECT_PARAM["description"]},
    "south": {**_RECT_PARAM, "description": "南边界纬度（-90..90）：" + _RECT_PARAM["description"]},
    "east": {**_RECT_PARAM, "description": "东边界经度（-180..180）：" + _RECT_PARAM["description"]},
    "north": {**_RECT_PARAM, "description": "北边界纬度（-90..90）：" + _RECT_PARAM["description"]},
}

_AGENT_NOTE = (
    "工具与手动 /api/area-activity 接口共用同一 service 与算法版本，同一参数结果一致；"
    "只做有界只读查询，不写入任何数据"
)


def _flatten(*groups: list[str]) -> list[str]:
    """合并口径说明并去重（保持首次出现顺序）。"""
    merged: list[str] = []
    for group in groups:
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged


def _area_block(ctx: AreaContext) -> dict:
    """结果中回显实际生效区域（含 area_id/version/is_default 与来源）。"""
    return area_context_payload(ctx)


def _flat_area_keys(ctx: AreaContext) -> dict:
    """query 中平铺的区域标识，便于前端与文档逐字段核对。"""
    return {
        "area_id": ctx.area_id,
        "area_version": ctx.version,
        "area_is_default": ctx.is_default,
    }


def _snapshot_envelope(payload: dict, ctx: AreaContext) -> dict:
    limits = payload["limits"]
    summary = payload["summary"]
    listed = limits["returned_ship_count"]
    unlisted = max(0, int(summary["in_area_count"]) - int(listed))
    return {
        "status": payload["status"],
        "mode": "snapshot",
        "area": _area_block(ctx),
        "query": {
            "mode": "snapshot",
            **_flat_area_keys(ctx),
            "time_zone": area_params.DAY_TIME_ZONE,
            "at": payload["query"]["at"],
            "filters": {
                "ship_types": payload["query"]["filters"]["ship_types"],
                "freshness_seconds": summary["freshness_seconds"],
                "source": payload["query"]["filters"]["source"],
            },
        },
        "summary": {
            **summary,
            "listed_ship_count": listed,
            "unlisted_ship_count": unlisted,
        },
        "ships": payload["ships"],
        "limits": {
            **limits,
            "agent_ship_limit": AGENT_SNAPSHOT_SHIP_LIMIT,
            "unlisted_ship_count": unlisted,
        },
        "coverage": payload["coverage"],
        "algorithm": payload["algorithm"],
        "limitations": _flatten(
            payload["limitations"],
            [
                f"工具明细最多列出 {AGENT_SNAPSHOT_SHIP_LIMIT} 艘在场船（只裁剪明细，"
                f"汇总不裁剪）；还有 {unlisted} 艘未列出，见 limits.unlisted_ship_count",
                "status=no_data 表示读取范围内没有可用报位/可判定船舶，不等于该区域没有船；"
                "status=ok 且 in_area_count=0 才是有效零结果",
                "结果只是历史报位的复述，不构成通行统计，也不推断船舶意图或事件因果",
                _SHIP_TYPE_NOTE,
                _AGENT_NOTE,
            ],
        ),
    }


def _activity_envelope(payload: dict, ctx: AreaContext) -> dict:
    limits = payload["limits"]
    summary = payload["summary"]
    shown = limits["returned_visit_count"]
    not_shown = max(0, int(summary["visit_count"]) - int(shown))
    window = payload["query"]["window"]
    return {
        "status": payload["status"],
        "mode": "activity",
        "area": _area_block(ctx),
        "query": {
            "mode": "activity",
            **_flat_area_keys(ctx),
            "time_zone": payload["query"]["time_zone"],
            "start_at": window["start"],
            "end_at": window["end"],
            "window": window,
            "state_scope": payload["query"]["state_scope"],
            "context_bounds": payload["query"]["context_bounds"],
            "filters": payload["query"]["filters"],
        },
        "summary": summary,
        "daily": payload["daily"],
        "visits": payload["visits"],
        "limits": {
            **limits,
            "agent_visit_limit": AGENT_VISIT_LIMIT,
            "visits_not_shown": not_shown,
        },
        "coverage": payload["coverage"],
        "algorithm": payload["algorithm"],
        "limitations": _flatten(
            payload["limitations"],
            [
                f"工具明细最多列出 {AGENT_VISIT_LIMIT} 条访问（汇总与每日汇总基于全部访问计算，"
                f"不裁剪）；还有 {not_shown} 条未列出，见 limits.visits_not_shown",
                "status=no_data 只表示读取范围内没有 nnu_ais 报位；窗口内有报位但没有区域内报位"
                "是有效零结果（不是数据缺失），不能把 no_data 说成「零船」",
                "出现去重船数不是交通量，也不等于连续在场人数；缺报区间不计入船时，不做插值",
                _SHIP_TYPE_NOTE,
                _AGENT_NOTE,
            ],
        ),
    }


def _compare_envelope(payload: dict, ctx: AreaContext) -> dict:
    comparability = payload["comparability"]
    metrics = payload["metrics"]
    summary_a = payload["a"]["summary"]
    summary_b = payload["b"]["summary"]
    return {
        "status": payload["status"],
        "mode": "compare",
        "area": _area_block(ctx),
        "query": {
            "mode": "compare",
            **_flat_area_keys(ctx),
            "time_zone": area_params.DAY_TIME_ZONE,
            "start_a": payload["windows"]["a"]["start"],
            "end_a": payload["windows"]["a"]["end"],
            "start_b": payload["windows"]["b"]["start"],
            "end_b": payload["windows"]["b"]["end"],
            "windows": payload["windows"],
            "comparability": comparability,
        },
        "summary": {
            "a": summary_a,
            "b": summary_b,
            "delta": {item["key"]: item["delta"] for item in metrics},
            "change_rate": {item["key"]: item["change_rate"] for item in metrics},
        },
        "metrics": metrics,
        "a": payload["a"],
        "b": payload["b"],
        "limits": {
            "max_window_days": area_params.MAX_WINDOW_DAYS,
            "max_rect_span_deg": area_params.MAX_RECT_SPAN_DEG,
            "detail_returned": False,
            "note": "compare 只返回两期汇总、每日汇总与指标，不返回逐次访问明细；"
                    "需要明细请对单期调用 query_area_ship_activity",
        },
        "algorithm": payload["algorithm"],
        "limitations": _flatten(
            payload["limitations"],
            [
                "change_rate=null 表示基期该指标为 0，变化率无法定义并已单独说明；"
                "null 不是 0，也不表示没有变化",
                "两期窗口长度或来源批次不一致时不可比（见 comparability.warnings），"
                "不输出无条件的活动增减结论",
                "只返回聚合指标，不返回逐次访问明细；指标随两期 coverage 与算法版本一起解读",
                _SHIP_TYPE_NOTE,
                _AGENT_NOTE,
            ],
        ),
    }


def make_area_tools(
    db: Session,
    state: dict,
    current_area: AreaContext,
) -> list[StructuredTool]:
    """构造三个区域活动工具；db/state/当前请求区域绑定到当前请求。"""

    def _query_area_ship_snapshot(
        at: str,
        west: float | None = None,
        south: float | None = None,
        east: float | None = None,
        north: float | None = None,
        ship_type: list[str] | None = None,
        freshness_seconds: int | None = None,
    ) -> str:
        def run() -> dict:
            if not isinstance(at, str) or not at.strip():
                raise ValueError(
                    "at 必填：请给出需要判定的历史时刻（带时区的 ISO 8601），"
                    "不得用当前时间或默认封锁时刻猜测"
                )
            at_value = parse_time_arg(at)
            ctx = bounds_from_arguments(west, south, east, north, None, current_area)
            payload = area_service.query_snapshot(
                db,
                at=at_value,
                bounds=ctx.bounds,
                is_default=ctx.is_default,
                ship_type_values=ship_type,
                freshness_seconds=freshness_seconds,
                limit=AGENT_SNAPSHOT_SHIP_LIMIT,
            )
            return _snapshot_envelope(payload, ctx)

        return _execute_guarded(state, "query_area_ship_snapshot", run)

    def _query_area_ship_activity(
        start_at: str,
        end_at: str,
        west: float | None = None,
        south: float | None = None,
        east: float | None = None,
        north: float | None = None,
        ship_type: list[str] | None = None,
        batch_ids: list[int] | None = None,
    ) -> str:
        def run() -> dict:
            start_value = parse_time_arg(start_at)
            end_value = parse_time_arg(end_at)
            if start_value is None or end_value is None:
                raise ValueError(
                    "start_at 与 end_at 必填：请给出带时区的 ISO 8601 窗口"
                )
            ctx = bounds_from_arguments(west, south, east, north, None, current_area)
            payload = area_service.query_activity(
                db,
                start=start_value,
                end=end_value,
                bounds=ctx.bounds,
                is_default=ctx.is_default,
                ship_type_values=ship_type,
                batch_ids=batch_ids,
                visit_limit=AGENT_VISIT_LIMIT,
            )
            return _activity_envelope(payload, ctx)

        return _execute_guarded(state, "query_area_ship_activity", run)

    def _compare_area_ship_activity(
        start_a: str,
        end_a: str,
        start_b: str,
        end_b: str,
        west: float | None = None,
        south: float | None = None,
        east: float | None = None,
        north: float | None = None,
        ship_type: list[str] | None = None,
        batch_ids: list[int] | None = None,
    ) -> str:
        def run() -> dict:
            windows: dict[str, Any] = {}
            for label, raw in (("start_a", start_a), ("end_a", end_a),
                               ("start_b", start_b), ("end_b", end_b)):
                value = parse_time_arg(raw)
                if value is None:
                    raise ValueError(f"{label} 必填：请给出带时区的 ISO 8601 窗口")
                windows[label] = value
            ctx = bounds_from_arguments(west, south, east, north, None, current_area)
            payload = area_service.compare_activity(
                db,
                start_a=windows["start_a"],
                end_a=windows["end_a"],
                start_b=windows["start_b"],
                end_b=windows["end_b"],
                bounds=ctx.bounds,
                is_default=ctx.is_default,
                ship_type_values=ship_type,
                batch_ids=batch_ids,
            )
            return _compare_envelope(payload, ctx)

        return _execute_guarded(state, "compare_area_ship_activity", run)

    return [
        StructuredTool.from_function(
            func=_query_area_ship_snapshot,
            name="query_area_ship_snapshot",
            description=(
                "只读查询某一历史时刻在分析区域内的船（每船最新有效报位判定，过期报位不计入在场）；"
                "矩形参数省略时使用当前请求区域。用于「这个区域此刻有哪些船」类问题；"
                "历史观测的复述，不等于该时刻真实位置，也不表示区域外没有船"
            ),
            args_schema=args_model("query_area_ship_snapshot", {
                "type": "object",
                "properties": {
                    "at": {**_TIME_PARAM, "description": "判定时刻，ISO 8601 且必须带时区；必填，不要用当前时间猜测"},
                    **_RECT_PROPERTIES,
                    "ship_type": _SHIP_TYPE_PARAM,
                    "freshness_seconds": {
                        "type": "integer",
                        "description": "报位新鲜度上限（秒，1..86400），默认 3600；超过该时长的报位不算在场",
                    },
                },
                "required": ["at"],
            }),
        ),
        StructuredTool.from_function(
            func=_query_area_ship_activity,
            name="query_area_ship_activity",
            description=(
                "只读查询时段的区域船舶活动：出现去重船数、观测进入/离开次数、累计船时、"
                "每日汇总与有界访问明细；矩形参数省略时使用当前请求区域。窗口最长 7 天。"
                "出现去重船数不是交通量；no_data 表示读取范围内没有报位，不能当作「零船」"
            ),
            args_schema=args_model("query_area_ship_activity", {
                "type": "object",
                "properties": {
                    "start_at": {**_TIME_PARAM, "description": "窗口开始（含），ISO 8601 且必须带时区"},
                    "end_at": {**_TIME_PARAM, "description": "窗口结束（不含），ISO 8601 且必须带时区；必须晚于 start_at，窗口最长 7 天"},
                    **_RECT_PROPERTIES,
                    "ship_type": _SHIP_TYPE_PARAM,
                    "batch_ids": {
                        "type": "array",
                        "description": "来源批次筛选（正整数列表，如 [4]）；省略表示全部批次，批次与来源授权尚未核实",
                    },
                },
                "required": ["start_at", "end_at"],
            }),
        ),
        StructuredTool.from_function(
            func=_compare_area_ship_activity,
            name="compare_area_ship_activity",
            description=(
                "只读比较同一区域、同一筛选下的两个时段（每期最长 7 天）：两期指标、绝对差 delta "
                "与变化率 change_rate（基期为 0 时为 null 并单独说明）、comparability 与 warnings；"
                "矩形参数省略时使用当前请求区域。两期长度或覆盖不一致时不可比"
            ),
            args_schema=args_model("compare_area_ship_activity", {
                "type": "object",
                "properties": {
                    "start_a": {**_TIME_PARAM, "description": "A 期开始（含）"},
                    "end_a": {**_TIME_PARAM, "description": "A 期结束（不含），必须晚于 start_a，最长 7 天"},
                    "start_b": {**_TIME_PARAM, "description": "B 期开始（含）"},
                    "end_b": {**_TIME_PARAM, "description": "B 期结束（不含），必须晚于 start_b，最长 7 天"},
                    **_RECT_PROPERTIES,
                    "ship_type": _SHIP_TYPE_PARAM,
                    "batch_ids": {
                        "type": "array",
                        "description": "来源批次筛选（正整数列表）；两期使用同一筛选，省略表示全部批次",
                    },
                },
                "required": ["start_a", "end_a", "start_b", "end_b"],
            }),
        ),
    ]
