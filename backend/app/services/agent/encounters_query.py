"""AG-04 query_encounters 的服务适配：参数校验 + 复用 P4 encounters 读取服务 + 边界说明。

只读取 encounters 派生层现有结果：
- analyze_encounters（POST /api/encounters/analyze）是写操作，本适配层绝不调用；
- max_distance_nm 查询层只能缩小、不能扩大构建覆盖：
  省略时取构建阈值（manifest params.distance_nm，即不额外过滤）；
  请求阈值 > 构建阈值时抛 ValueError（能力不支持，不得返回 0 结果）；
- 窗口省略时返回全部已构建船对，而不是套用通行工具的默认封锁窗口。
"""
from datetime import datetime, timedelta
import json

from sqlalchemy.orm import Session

from backend.app.repositories import encounters as enc_repo
from backend.app.services import encounters as encounters_service

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_WINDOW = timedelta(hours=24)

LIMITATIONS = [
    "相遇判定的距离/时长/采样阈值由构建参数快照决定（见 params），"
    "查询层 max_distance_nm 只能缩小不能扩大覆盖",
    "min_distance_m / min_distance_nm 为离散采样（采样间隔见 params.sample_seconds 秒）"
    "近似的最小距离，不是连续时间精确值",
    "窗口筛选的是与窗口重叠的预计算船对（period 与窗口求交），"
    "最小距离不一定发生在所查子窗口之内",
    "时空接近不等于实际交互；结果为教学模拟数据，不指向真实船舶行为",
    "stale 仅为时间启发式（built_at 早于最新源报位），stale=false 不证明历史数据未被修改",
    "未提供时间窗时返回全部已构建船对",
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


def _parse_max_distance_nm(args: dict) -> float | None:
    raw = args.get("max_distance_nm")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError("max_distance_nm 必须是数字")
    if raw <= 0:
        raise ValueError("max_distance_nm 必须为正数")
    return float(raw)


def _manifest_params(manifest) -> dict:
    if manifest is None:
        return {}
    params = manifest["params"]
    if not isinstance(params, dict):
        params = json.loads(params)
    return params


def run_encounters_query(db: Session, args: dict) -> dict:
    """执行 query_encounters：校验参数 → 计算生效阈值 → 复用 encounters 读取服务。"""
    if not isinstance(args, dict):
        raise ValueError("工具参数必须是 JSON 对象")
    start, end = _parse_window_args(args)
    limit = _parse_limit(args)
    requested_nm = _parse_max_distance_nm(args)

    # 先读构建阈值：查询层只能缩小不能扩大覆盖；阈值不可知时不做额外限制
    manifest = enc_repo.fetch_manifest(db)
    params = _manifest_params(manifest)
    build_nm = params.get("distance_nm")
    effective_nm = requested_nm
    if requested_nm is not None and build_nm is not None and requested_nm > build_nm:
        raise ValueError(
            f"max_distance_nm={requested_nm} 超过构建阈值 {build_nm} NM："
            "查询层只能缩小不能扩大覆盖，请改用不超过构建阈值的值"
        )
    if effective_nm is None:
        effective_nm = build_nm  # 省略时按构建阈值过滤，即不额外缩小覆盖

    from_raw = start.isoformat() if start else None
    to_raw = end.isoformat() if end else None
    result = encounters_service.list_encounters(db, from_raw, to_raw, effective_nm)

    if result["status"] == "not_built":
        return {
            "status": "not_built",
            "message": result["message"],
            "window": [start, end] if start else None,
            "max_distance_nm_filter": None,
            "encounters": [],
            "returned_count": 0,
            "matched_count": 0,
            "truncated": False,
            "params": None,
            "built_at": None,
            "stale": None,
            "limitations": list(LIMITATIONS),
        }

    encounters = result["encounters"]
    matched_count = result["count"]
    truncated = bool(result["truncated"])
    if matched_count > limit:
        truncated = True
    kept = encounters[:limit]

    return {
        "status": result["status"],
        "window": [start, end] if start else None,
        "max_distance_nm_filter": effective_nm,
        "requested_max_distance_nm": requested_nm,
        "encounters": kept,
        "returned_count": len(kept),
        "matched_count": matched_count,
        "truncated": truncated,
        "params": result["params"],
        "built_at": result["built_at"],
        "stale": result["stale"],
        "limitations": list(LIMITATIONS),
    }
