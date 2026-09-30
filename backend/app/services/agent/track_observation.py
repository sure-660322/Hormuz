"""Bounded model view; complete evidence stays in request state for map actions."""
import json
import math

MAX_OBSERVATION_BYTES = 8192
MAX_TEXT_CHARS = 80


def _scalar(value):
    if isinstance(value, str):
        return value[:MAX_TEXT_CHARS]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and value.bit_length() <= 64:
        return value
    return None


def track_observation(envelope: dict) -> str:
    """Expose only identity, coverage and two endpoints, never the fixes array."""
    keys = ("call_id", "tool_name", "status", "code", "message", "schema_version",
            "ship_id", "ship_name", "start_at", "end_at", "fix_count",
            "coverage_start", "coverage_end", "truncated")
    summary = {key: _scalar(envelope[key]) for key in keys if key in envelope}
    summary["source"] = "nnu_ais"
    summary["observation_kind"] = "track_summary"
    summary["limitations"] = [
        "仅含首末报位摘要，不是完整轨迹；不能据此推断逐点路径、精确通行或停留。",
        "历史 AIS 来源授权与覆盖尚未核实；缺报不能证明船舶不存在。",
    ] + [str(item)[:MAX_TEXT_CHARS] for item in envelope.get("limitations", [])[:8]]
    summary["limitations_omitted"] = max(0, len(envelope.get("limitations", [])) - 8)
    fixes = envelope.get("fixes") or []
    for key, fix in (("first_fix", fixes[0]), ("latest_fix", fixes[-1])) if fixes else ():
        summary[key] = {field: _scalar(fix[field]) for field in (
            "recorded_at", "longitude", "latitude", "speed", "course", "nav_status"
        ) if field in fix}
    encoded = json.dumps(summary, ensure_ascii=False, allow_nan=False)
    # The selected fields are bounded; keep a hard guard if fields are added later.
    if len(encoded.encode("utf-8")) > MAX_OBSERVATION_BYTES:
        raise ValueError("轨迹模型摘要超过大小上限")
    return encoded
