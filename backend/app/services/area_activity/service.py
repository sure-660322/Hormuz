"""区域船舶活动与进出分析：共享业务服务。

手动界面与（后续的）智能体业务工具都调用本模块，筛选、状态转换、分窗与比较只在
服务端做一次；路由只做参数校验。算法与边界见 docs/area_activity.md。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.services.area_activity import algorithm, boundaries, params, repository
from backend.app.services.area_activity.boundaries import AreaBounds

STANDING_LIMITATIONS = [
    "默认区域是项目分析区域，不是官方航道（TAS/TSS）边界；结果回显 area_id/version/basis",
    "报位是历史观测：时刻在场所给位置不保证该时刻的真实位置，过期报位不计入在场",
    "出现去重船数不等于进出次数，也不等于连续在场人数；报位频率差异不能换算成交通量",
    "缺报区间不计入停留时长，不做任何插值；采样漏检可能漏掉短暂穿越",
    "观测进入次数不要求等于离开次数：窗外进入、窗内离开与缺报都会造成差额",
    "AIS 来源授权与区域覆盖尚未核实；批次 1–7 为逐日文件，批次 8 为北极案例单船",
]


class AreaActivityError(ValueError):
    """参数或上限错误；路由映射为 422。"""


def _require_aware(value: datetime, name: str) -> None:
    if value is None:
        raise AreaActivityError(f"{name} 必填")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AreaActivityError(f"{name} 必须包含显式时区（带时区的 ISO 8601 时间）")


def _validate_window(start: datetime, end: datetime, label: str = "窗口") -> None:
    _require_aware(start, f"{label}开始时间")
    _require_aware(end, f"{label}结束时间")
    if not start < end:
        raise AreaActivityError(f"{label}必须满足 start < end")
    if end - start > params.MAX_WINDOW:
        raise AreaActivityError(
            f"{label}最长 {params.MAX_WINDOW_DAYS} 天（当前 {end - start}），请缩小范围"
        )


def _resolve_filters(
    ship_type_values: list[str] | None,
    batch_ids: list[int] | None,
) -> dict:
    types, _explicit_all = boundaries.split_ship_types(ship_type_values)
    include_missing = bool(types and params.SHIP_TYPE_MISSING in types)
    include_unknown = bool(types and params.SHIP_TYPE_UNKNOWN in types)
    concrete = [
        value for value in (types or [])
        if value not in (params.SHIP_TYPE_MISSING, params.SHIP_TYPE_UNKNOWN)
    ]
    applied = types is not None
    if batch_ids:
        for value in batch_ids:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise AreaActivityError("batch_ids 必须是正整数")
    return {
        "applied": applied,
        "ship_types": concrete or None,
        "include_missing": include_missing,
        "include_unknown": include_unknown,
        "unknown_label": "未知",
        "raw": ship_type_values or None,
        "batch_ids": list(batch_ids) if batch_ids else None,
    }


def _limit(value: int, default: int, maximum: int, name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AreaActivityError(f"{name} 必须是正整数")
    if value > maximum:
        raise AreaActivityError(f"{name} 最大 {maximum}")
    return value


def _coverage(
    db: Session,
    *,
    source: str,
    batch_ids,
    scope,
    stats: dict | None = None,
) -> dict:
    batches = repository.fetch_batch_coverage(db, source=source, batch_ids=batch_ids)
    payload = {
        "source": source,
        "batch_ids": [row["id"] for row in batches],
        "batch_days": [row["source_day"].isoformat() for row in batches],
    }
    if scope is not None:
        payload["scope_start"] = scope[0]
        payload["scope_end"] = scope[1]
    if stats is not None:
        payload.update({
            "scoped_fix_count": int(stats["scoped_fix_count"]),
            "region_fix_count": int(stats["region_fix_count"]),
            "window_region_fix_count": int(stats["window_region_fix_count"]),
            "first_fix_at": stats["first_fix_at"],
            "last_fix_at": stats["last_fix_at"],
        })
    payload["note"] = (
        "覆盖描述的是本次读取范围（来源与批次过滤后的报位），"
        "不代表 AIS 原始覆盖完整，也不代表区域内船舶都被观测到"
    )
    return payload


def default_area_payload() -> dict:
    bounds = boundaries.default_bounds()
    return {
        "area": boundaries.describe_area(bounds, is_default=True),
        "algorithm": params.algorithm_descriptor(),
        "limitations": list(STANDING_LIMITATIONS),
    }


def query_snapshot(
    db: Session,
    *,
    at: datetime,
    bounds: AreaBounds,
    is_default: bool,
    ship_type_values: list[str] | None = None,
    freshness_seconds: int | None = None,
    limit: int | None = None,
    source: str = params.SOURCE,
) -> dict:
    """时刻在场：每船最新有效报位判定，不用更早的区域内点兜底。"""
    _require_aware(at, "at")
    bounds.validate()
    freshness = params.FRESHNESS_SECONDS if freshness_seconds is None else freshness_seconds
    if isinstance(freshness, bool) or not isinstance(freshness, int) or freshness < 1:
        raise AreaActivityError("freshness_seconds 必须是正整数")
    if freshness > 86_400:
        raise AreaActivityError("freshness_seconds 最大 86400")
    output_limit = _limit(limit, params.DEFAULT_SNAPSHOT_LIMIT, params.MAX_SNAPSHOT_SHIPS, "limit")
    filters = _resolve_filters(ship_type_values, None)

    repository.apply_session_settings(
        db, params.STATEMENT_TIMEOUT_MS, params.WORK_MEM_MB
    )
    rows = repository.fetch_latest_fixes(
        db, at=at, source=source, batch_ids=None,
        limit=params.MAX_SNAPSHOT_SHIPS + 1,
        ship_type_filter=filters["applied"],
        ship_types=filters["ship_types"],
        include_missing=filters["include_missing"],
        include_unknown=filters["include_unknown"],
        unknown_label=filters["unknown_label"],
    )
    if len(rows) > params.MAX_SNAPSHOT_SHIPS:
        raise AreaActivityError(
            f"参与判定的船舶超过 {params.MAX_SNAPSHOT_SHIPS} 艘，请缩小矩形或船型范围"
        )

    in_area: list[dict] = []
    out_of_area = 0
    stale = 0
    for row in rows:
        age = (at - row["recorded_at"]).total_seconds()
        if age > freshness:
            stale += 1
            continue
        inside = bounds.contains(row["latitude"], row["longitude"])
        if not inside:
            out_of_area += 1
            continue
        in_area.append({
            "ship_id": row["ship_id"],
            "name": row["name"],
            "mmsi": row["mmsi"],
            "ship_type": row["ship_type"],
            "flag": row["flag"],
            "fix_id": row["fix_id"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "speed": row["speed"],
            "recorded_at": row["recorded_at"],
            "age_seconds": round(age, 3),
            "fresh": True,
            "inside": True,
        })

    return {
        "status": "ok" if rows else "no_data",
        "area": boundaries.describe_area(bounds, is_default=is_default),
        "query": {
            "mode": "snapshot",
            "time_zone": params.DAY_TIME_ZONE,
            "at": at,
            "filters": {
                "ship_types": filters["raw"],
                "include_missing": filters["include_missing"],
                "include_unknown": filters["include_unknown"],
                "source": source,
            },
        },
        "algorithm": params.algorithm_descriptor(),
        "coverage": _coverage(db, source=source, batch_ids=None, scope=None),
        "summary": {
            "in_area_count": len(in_area),
            "out_of_area_fresh_count": out_of_area,
            "stale_fix_count": stale,
            "evaluated_ship_count": len(rows),
            "freshness_seconds": freshness,
        },
        "ships": in_area[:output_limit],
        "limits": {
            "max_snapshot_ships": params.MAX_SNAPSHOT_SHIPS,
            "evaluated_ship_count": len(rows),
            "returned_ship_count": min(len(in_area), output_limit),
            "list_truncated": len(in_area) > output_limit,
        },
        "limitations": list(STANDING_LIMITATIONS) + [
            f"仅使用 {at.isoformat()} 之前 {freshness} 秒内的最新报位；"
            "过期报位不作为在场，也不会回退到更早的区域内报位",
        ],
    }


def query_activity(
    db: Session,
    *,
    start: datetime,
    end: datetime,
    bounds: AreaBounds,
    is_default: bool,
    ship_type_values: list[str] | None = None,
    batch_ids: list[int] | None = None,
    lookback_seconds: int | None = None,
    lookahead_seconds: int | None = None,
    visit_limit: int | None = None,
    source: str = params.SOURCE,
    include_detail: bool = True,
) -> dict:
    """时段出现、进出与停留：一次扫描完成状态转换、分窗与按日汇总。"""
    _validate_window(start, end)
    bounds.validate()
    lookback = params.STATE_LOOKBACK_SECONDS if lookback_seconds is None else lookback_seconds
    lookahead = params.STATE_LOOKAHEAD_SECONDS if lookahead_seconds is None else lookahead_seconds
    for name, value in (("state_lookback_seconds", lookback), ("state_lookahead_seconds", lookahead)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AreaActivityError(f"{name} 必须是非负整数")
        if value > params.MAX_LOOKBACK_SECONDS:
            raise AreaActivityError(f"{name} 最大 {params.MAX_LOOKBACK_SECONDS}")
    limit = _limit(visit_limit, params.DEFAULT_VISIT_LIMIT, params.MAX_VISIT_ROWS, "visit_limit")
    filters = _resolve_filters(ship_type_values, batch_ids)

    scope_start = start - timedelta(seconds=lookback)
    scope_end = end + timedelta(seconds=lookahead)
    context = bounds.expanded(params.CONTEXT_MARGIN_DEG)

    repository.apply_session_settings(
        db, params.STATEMENT_TIMEOUT_MS, params.WORK_MEM_MB
    )
    rows = repository.fetch_activity_boundaries(
        db,
        start=start, end=end, scope_start=scope_start, scope_end=scope_end,
        source=source, batch_ids=filters["batch_ids"], bounds=bounds, context=context,
        gap_seconds=params.GAP_SECONDS, jump_kn=params.JUMP_SPEED_KN,
        boundary_limit=params.MAX_BOUNDARY_ROWS + 1,
        ship_type_filter=filters["applied"],
        ship_types=filters["ship_types"],
        include_missing=filters["include_missing"],
        include_unknown=filters["include_unknown"],
        unknown_label=filters["unknown_label"],
    )
    if len(rows) > params.MAX_BOUNDARY_ROWS:
        raise AreaActivityError(
            "访问明细超过上限，请缩小矩形或时间范围；汇总没有被截断"
        )
    stats = dict(rows[0]) if rows else _fallback_stats(
        db, start=start, end=end, scope_start=scope_start, scope_end=scope_end,
        source=source, bounds=bounds, context=context,
        ship_type_filter=filters["applied"], filters=filters,
    )
    if stats["scoped_fix_count"] > params.MAX_SCANNED_FIXES:
        raise AreaActivityError(
            f"读取范围报位数 {stats['scoped_fix_count']} 超过上限 "
            f"{params.MAX_SCANNED_FIXES}，请缩小矩形或时间范围；结果没有被截断"
        )
    candidate_ships = len({row["ship_id"] for row in rows})
    if candidate_ships > params.MAX_CANDIDATE_SHIPS:
        raise AreaActivityError(
            f"候选船数 {candidate_ships} 超过上限 {params.MAX_CANDIDATE_SHIPS}，请缩小范围"
        )

    visits = algorithm.assemble_visits(rows, bounds, params.GAP_SECONDS)
    touching = algorithm.visits_touching(visits, start, end)
    summary = algorithm.summarize(visits, start, end)
    daily = algorithm.daily_breakdown(visits, start, end)
    uncertainty = sum(
        1 for visit in touching if visit.flags or visit.prior_state == "unknown"
    )
    detail_truncated = len(touching) > limit
    status = "no_data" if not stats["scoped_fix_count"] else (
        "partial" if (uncertainty or detail_truncated) else "ok"
    )
    limitations = list(STANDING_LIMITATIONS) + [
        f"观测上下文为分析区外扩 {params.CONTEXT_MARGIN_DEG}°，"
        f"窗口前后各回看 {lookback}/{lookahead} 秒；超出范围的区外报位不参与状态判定",
        f"缺报断开阈值 {params.GAP_SECONDS} 秒、跳点阈值 {params.JUMP_SPEED_KN} 节为 v1 默认值，"
        "尚未用全部七日样本独立校准",
    ]
    if not stats["scoped_fix_count"]:
        limitations.append("读取范围内没有任何 nnu_ais 报位，无法判定该窗口的活动")
    elif not stats["window_region_fix_count"]:
        limitations.append("读取范围内有报位，但窗口内没有区域内报位：这是有效零结果，不是数据缺失")
    if uncertainty:
        limitations.append(f"{uncertainty} 次访问带缺报/跳点/边界近邻/前置状态未知等质量标记")

    payload = {
        "status": status,
        "area": boundaries.describe_area(bounds, is_default=is_default),
        "query": {
            "mode": "activity",
            "time_zone": params.DAY_TIME_ZONE,
            "window": {
                "start": start, "end": end,
                "days": len(algorithm.day_starts(start, end)),
                "length_hours": round((end - start).total_seconds() / 3600.0, 4),
                "length_days": round((end - start).total_seconds() / 86_400.0, 6),
            },
            "state_scope": {
                "start": scope_start, "end": scope_end,
                "lookback_seconds": lookback, "lookahead_seconds": lookahead,
            },
            "context_bounds": context.as_dict(),
            "filters": {
                "ship_types": filters["raw"],
                "include_missing": filters["include_missing"],
                "include_unknown": filters["include_unknown"],
                "source": source,
                "batch_ids": filters["batch_ids"],
            },
        },
        "algorithm": params.algorithm_descriptor(),
        "coverage": _coverage(
            db, source=source, batch_ids=filters["batch_ids"],
            scope=(scope_start, scope_end), stats=stats,
        ),
        "summary": summary,
        "daily": daily,
        "limits": {
            "max_scanned_fixes": params.MAX_SCANNED_FIXES,
            "scanned_fix_count": int(stats["scoped_fix_count"]),
            "max_candidate_ships": params.MAX_CANDIDATE_SHIPS,
            "candidate_ship_count": candidate_ships,
            "max_visit_rows": params.MAX_VISIT_ROWS,
            "visit_limit": limit,
            "returned_visit_count": min(len(touching), limit),
            "detail_truncated": detail_truncated,
        },
        "limitations": limitations,
    }
    if include_detail:
        payload["visits"] = [
            algorithm.visit_payload(visit, start, end) for visit in touching[:limit]
        ]
    return payload


def _fallback_stats(
    db: Session,
    *,
    start,
    end,
    scope_start,
    scope_end,
    source,
    bounds: AreaBounds,
    context: AreaBounds,
    ship_type_filter: bool,
    filters: dict,
) -> dict:
    """没有任何边界行时单独取覆盖统计，用于区分 no_data 与有效零结果。"""
    row = repository.fetch_scope_stats(
        db,
        start=start, end=end, scope_start=scope_start, scope_end=scope_end,
        source=source, batch_ids=filters["batch_ids"], bounds=bounds, context=context,
        ship_type_filter=ship_type_filter,
        ship_types=filters["ship_types"],
        include_missing=filters["include_missing"],
        include_unknown=filters["include_unknown"],
        unknown_label=filters["unknown_label"],
    )
    return dict(row)


def compare_activity(
    db: Session,
    *,
    start_a: datetime,
    end_a: datetime,
    start_b: datetime,
    end_b: datetime,
    bounds: AreaBounds,
    is_default: bool,
    ship_type_values: list[str] | None = None,
    batch_ids: list[int] | None = None,
    lookback_seconds: int | None = None,
    lookahead_seconds: int | None = None,
    visit_limit: int | None = None,
    source: str = params.SOURCE,
) -> dict:
    """同一区域、同一筛选、同一算法版本下的两时段比较。"""
    _validate_window(start_a, end_a, "A 窗口")
    _validate_window(start_b, end_b, "B 窗口")
    common = dict(
        bounds=bounds, is_default=is_default, ship_type_values=ship_type_values,
        batch_ids=batch_ids, lookback_seconds=lookback_seconds,
        lookahead_seconds=lookahead_seconds, visit_limit=visit_limit, source=source,
    )
    payload_a = query_activity(db, start=start_a, end=end_a, **common)
    payload_b = query_activity(db, start=start_b, end=end_b, **common)
    days_a = payload_a["query"]["window"]["days"]
    days_b = payload_b["query"]["window"]["days"]
    length_days_a = (end_a - start_a).total_seconds() / 86_400.0
    length_days_b = (end_b - start_b).total_seconds() / 86_400.0
    metrics = algorithm.compare_metrics(
        payload_a["summary"], payload_b["summary"], length_days_a, length_days_b
    )

    warnings = []
    if (end_a - start_a) != (end_b - start_b):
        warnings.append(
            f"两期长度不同（A {length_days_a:.2f} 天 / B {length_days_b:.2f} 天）："
            "已给出按实际窗口长度的日均指标，绝对差仍是总量差，解释活动增减时需注明分母"
        )
    if payload_a["status"] == "no_data" or payload_b["status"] == "no_data":
        warnings.append("至少一期在读取范围内没有报位，两期不可比，不能据此判断活动增减")
    if set(payload_a["coverage"]["batch_ids"]) != set(payload_b["coverage"]["batch_ids"]):
        warnings.append("两期使用的来源批次不同，覆盖可比性不足")
    if payload_a["limits"]["detail_truncated"] or payload_b["limits"]["detail_truncated"]:
        warnings.append("至少一期明细被截断（汇总仍完整），明细列表不可直接逐条比较")

    statuses = {payload_a["status"], payload_b["status"]}
    status = "no_data" if statuses == {"no_data"} else ("partial" if "partial" in statuses else "ok")
    return {
        "status": status,
        "area": boundaries.describe_area(bounds, is_default=is_default),
        "algorithm": params.algorithm_descriptor(),
        "windows": {
            "a": {
                "start": start_a, "end": end_a, "days": days_a,
                "length_hours": round((end_a - start_a).total_seconds() / 3600.0, 4),
            },
            "b": {
                "start": start_b, "end": end_b, "days": days_b,
                "length_hours": round((end_b - start_b).total_seconds() / 3600.0, 4),
            },
        },
        "comparability": {
            "same_area": True,
            "same_filters": True,
            "same_algorithm": True,
            "equal_length": (end_a - start_a) == (end_b - start_b),
            "window_days_a": days_a,
            "window_days_b": days_b,
            "window_length_days_a": round(length_days_a, 6),
            "window_length_days_b": round(length_days_b, 6),
            "per_day_denominator": "窗口实际长度（含小数天），不是自然日个数",
            "warnings": warnings,
        },
        "metrics": metrics,
        "a": {
            "status": payload_a["status"], "summary": payload_a["summary"],
            "coverage": payload_a["coverage"], "daily": payload_a["daily"],
        },
        "b": {
            "status": payload_b["status"], "summary": payload_b["summary"],
            "coverage": payload_b["coverage"], "daily": payload_b["daily"],
        },
        "limitations": list(STANDING_LIMITATIONS) + [
            "基期为 0 时变化率为 null 并单独说明；无观测不回填为 0",
            "两期覆盖不一致时，不输出无条件的真实活动增减结论",
            "两期分别在两个语句中读取；业务库当前不并发写入，若同时存在写入，"
            "两期可能不是同一快照，请先比较两期 coverage.batch_ids 是否一致",
        ] + warnings,
    }
