"""AG-03 query_ship_dwell 的服务适配：参数校验 + 复用 P3 dwell 服务 + 边界说明。

只读取 ship_dwell 派生层现有结果，不触发任何重建或写入：
- kind / 时间窗 / 条数限制在适配层二次校验后才调用 dwell 服务；
- 锚泊/漂航/慢速航行阈值由构建参数（track_build_manifest params 快照）决定，
  查询层不可调整，不让模型重新定义；
- 未提供时间窗时默认返回整个已构建批次（并在 limitations 中声明），
  而不是套用通行工具的默认封锁窗口。
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.repositories import dwell as dwell_repo
from backend.app.services import dwell as dwell_service

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_WINDOW = timedelta(hours=24)
KINDS = dwell_repo.KINDS  # ("at_anchor", "drift", "slow_transit")

LIMITATIONS = [
    "停留判定阈值（锚泊/漂航/慢速航行的速度与时长判据）由构建参数快照决定（见 params），"
    "查询层不能调整，不由模型重新定义",
    "结果为派生层预计算快照；stale 仅为时间启发式（built_at 早于最新源报位），"
    "stale=false 不证明历史数据未被修改",
    "教学模拟数据的停留识别结果，不代表真实锚地/漂航认定",
    "未提供时间窗时返回整个已构建批次，而非某一封锁窗口",
]


def _parse_window_args(args: dict) -> tuple[datetime | None, datetime | None]:
    """start_at/end_at 必须成对出现：都带时区、start<end、窗口 ≤24 小时。"""
    raw_start = args.get("start_at")
    raw_end = args.get("end_at")
    if (raw_start is None) != (raw_end is None):
        raise ValueError("start_at 与 end_at 必须同时提供或同时省略")
    if raw_start is None:
        return None, None
    if not isinstance(raw_start, str) or not isinstance(raw_end, str):
        raise ValueError("start_at/end_at 必须是 ISO 8601 字符串")
    try:
        start = datetime.fromisoformat(raw_start)
        end = datetime.fromisoformat(raw_end)
    except ValueError:
        raise ValueError("start_at/end_at 无法解析为 ISO 8601 时间") from None
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("start_at 必须带时区（统一 UTC）")
    if end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("end_at 必须带时区（统一 UTC）")
    if not start < end:
        raise ValueError("start_at 必须早于 end_at")
    if end - start > MAX_WINDOW:
        raise ValueError("查询窗口不能超过 24 小时，请缩小范围或分窗查询")
    return start, end


def _parse_limit(args: dict) -> int:
    limit = args.get("limit")
    if limit is None:
        return DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        raise ValueError("limit 必须是整数")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit 必须在 1–{MAX_LIMIT} 之间")
    return limit


def _parse_kind(args: dict) -> str | None:
    kind = args.get("kind")
    if kind is None:
        return None
    if not isinstance(kind, str):
        raise ValueError(f"kind 必须是 {'/'.join(KINDS)} 之一")
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {'/'.join(KINDS)} 之一")
    return kind


def run_dwell_query(db: Session, args: dict) -> dict:
    """执行 query_ship_dwell：校验参数 → 复用 dwell 服务 → 组装智能体结果。"""
    if not isinstance(args, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    kind = _parse_kind(args)
    start, end = _parse_window_args(args)
    limit = _parse_limit(args)

    from_raw = start.isoformat() if start else None
    to_raw = end.isoformat() if end else None
    result = dwell_service.get_dwell(db, kind, from_raw, to_raw)

    if result["status"] == "not_built":
        return {
            "status": "not_built",
            "message": result["message"],
            "kind": kind,
            "window": [start, end] if start else None,
            "dwells": [],
            "returned_count": 0,
            "matched_count": 0,
            "truncated": False,
            "built_at": None,
            "params": None,
            "stale": None,
            "limitations": list(LIMITATIONS),
        }

    features = result["features"]
    matched_count = result["feature_count"]  # 服务层 5000 条上限内实际匹配数
    truncated = bool(result["truncated"])
    if matched_count > limit:
        truncated = True
    kept = features[:limit]

    dwells = []
    for feature in kept:
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or [None, None]
        properties = feature["properties"]
        dwells.append(
            {
                "ship_id": properties["ship_id"],
                "ship_name": properties["ship_name"],
                "mmsi": properties["mmsi"],
                "ship_type": properties["ship_type"],
                "dwell_no": properties["dwell_no"],
                "kind": properties["kind"],
                "enter_at": properties["enter_at"],
                "leave_at": properties["leave_at"],
                "duration_min": properties["duration_min"],
                "displacement_radius_m": properties["displacement_radius_m"],
                "max_speed_kn": properties["max_speed_kn"],
                "point_count": properties["point_count"],
                "center": {"lng": coordinates[0], "lat": coordinates[1]},
                "is_simulated": properties["is_simulated"],
            }
        )

    return {
        "status": result["status"],
        "kind": kind,
        "window": [start, end] if start else None,
        "dwells": dwells,
        "returned_count": len(dwells),
        "matched_count": matched_count,
        "truncated": truncated,
        "params": result["params"],
        "built_at": result["built_at"],
        "stale": result["stale"],
        "is_simulated": result["is_simulated"],
        "limitations": list(LIMITATIONS),
    }
