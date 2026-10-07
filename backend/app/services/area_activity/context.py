"""区域活动分析的「当前区域」上下文。

手动界面与智能体工具共用同一个区域解析入口：
- 请求未给出矩形 → 使用版本化的默认分析区域（`hormuz_core_v1`）；
- 请求/工具给出四个边界 → 作为自定义矩形（`custom`），仍由 service 做跨度与半开校验；
- 工具显式给出的矩形只作用于该次调用，不改变前端当前区域。

本模块只做结构性解析与回显，不做跨度上限校验——上限由
`AreaBounds.validate()` 与 `services.area_activity.service` 统一执行，保证 REST 与
智能体工具的口径一致（拒绝而不是截断）。
"""
from dataclasses import dataclass
from typing import Any, Iterable

from backend.app.services.area_activity import boundaries, params

BOUND_KEYS: tuple[str, str, str, str] = ("west", "south", "east", "north")

SOURCE_DEFAULT = "default"
SOURCE_CUSTOM = "custom"
SOURCE_REQUEST = "request"


@dataclass(frozen=True)
class AreaContext:
    """一次查询实际生效的分析区域（含版本与来源）。"""

    bounds: boundaries.AreaBounds
    is_default: bool
    area_id: str
    name: str
    version: str | None
    label: str
    source: str

    def describe(self) -> dict:
        """与 REST `area` 字段同构的区域描述（供兼容 old service 调用）。"""
        return boundaries.describe_area(self.bounds, is_default=self.is_default)

    def payload(self) -> dict:
        return area_context_payload(self)


def _number(value: Any, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"区域边界 {key} 必须是数值")
    return float(value)


def _same_bounds(left: boundaries.AreaBounds, right: boundaries.AreaBounds) -> bool:
    return (
        left.south == right.south and left.west == right.west
        and left.north == right.north and left.east == right.east
    )


def _from_bounds(
    bounds: boundaries.AreaBounds,
    *,
    is_default: bool,
    area_id: str | None = None,
    label: str | None = None,
    source: str,
) -> AreaContext:
    if is_default:
        return AreaContext(
            bounds=bounds,
            is_default=True,
            area_id=params.DEFAULT_AREA_ID,
            name=params.DEFAULT_AREA_NAME,
            version=params.DEFAULT_AREA_VERSION,
            label=label or params.DEFAULT_AREA_NAME,
            source=SOURCE_DEFAULT,
        )
    # 调用方显式声明 area_id=默认区域标识且边界与默认区域完全一致时，按默认区域处理：
    # 否则「当前区域=默认区域」的智能体请求会回显 custom，丢掉默认区身份（数字不受影响）。
    if (
        area_id
        and area_id.strip() == params.DEFAULT_AREA_ID
        and _same_bounds(bounds, boundaries.default_bounds())
    ):
        return AreaContext(
            bounds=bounds,
            is_default=True,
            area_id=params.DEFAULT_AREA_ID,
            name=params.DEFAULT_AREA_NAME,
            version=params.DEFAULT_AREA_VERSION,
            label=label or params.DEFAULT_AREA_NAME,
            source=SOURCE_DEFAULT,
        )
    return AreaContext(
        bounds=bounds,
        is_default=False,
        area_id=(area_id or "").strip() or "custom",
        name=(label or "").strip() or "自定义分析矩形",
        version=None,
        label=(label or "").strip() or "自定义分析矩形",
        source=source,
    )


def default_context() -> AreaContext:
    """默认分析区域上下文（版本化，不是官方航道边界）。"""
    bounds = boundaries.default_bounds()
    bounds.validate()
    return _from_bounds(bounds, is_default=True, source=SOURCE_DEFAULT)


def resolve_area_context(
    raw: object | None,
    *,
    payload_keys: tuple[str, ...] = BOUND_KEYS,
    source: str = SOURCE_REQUEST,
) -> AreaContext:
    """把请求中的区域载荷解析成 AreaContext。

    `raw` 为 None 或空 → 默认区域；否则必须是包含四个边界键的映射。
    只校验结构；跨度、跨 180°、south<north 等业务校验在 service 中进行。
    """
    if raw is None:
        return default_context()
    if isinstance(raw, AreaContext):
        return raw
    if not isinstance(raw, dict):
        raise ValueError("区域上下文必须是对象")

    values = {key: raw.get(key) for key in payload_keys if key in BOUND_KEYS}
    present = [values.get(key) is not None for key in BOUND_KEYS]
    if not any(present):
        return default_context()
    if not all(present):
        raise ValueError("区域边界的 west/south/east/north 必须同时给出或同时省略")
    bounds = boundaries.AreaBounds(
        west=_number(values["west"], "west"),
        south=_number(values["south"], "south"),
        north=_number(values["north"], "north"),
        east=_number(values["east"], "east"),
    )
    return _from_bounds(
        bounds,
        is_default=False,
        area_id=raw.get("area_id") if isinstance(raw.get("area_id"), str) else None,
        label=raw.get("label") if isinstance(raw.get("label"), str) else None,
        source=source,
    )


def bounds_from_arguments(
    west: float | None,
    south: float | None,
    east: float | None,
    north: float | None,
    explicit_area_id: str | None,
    current: AreaContext,
) -> AreaContext:
    """智能体工具显式给出矩形时使用；缺省则沿用当前区域上下文。"""
    provided = [value is not None for value in (west, south, east, north)]
    if not any(provided):
        return current
    if not all(provided):
        raise ValueError("工具调用中的 west/south/east/north 必须同时给出或同时省略")
    bounds = boundaries.AreaBounds(
        west=_number(west, "west"),
        south=_number(south, "south"),
        north=_number(north, "north"),
        east=_number(east, "east"),
    )
    return _from_bounds(
        bounds,
        is_default=False,
        area_id=explicit_area_id,
        label=None,
        source=SOURCE_CUSTOM,
    )


def area_context_payload(ctx: AreaContext) -> dict:
    """回显实际生效的区域：区域标识、版本、边界与来源。"""
    bounds = ctx.bounds
    return {
        "area_id": ctx.area_id,
        "name": ctx.name,
        "version": ctx.version,
        "label": ctx.label,
        "source": ctx.source,
        "is_default": ctx.is_default,
        "west": bounds.west,
        "south": bounds.south,
        "east": bounds.east,
        "north": bounds.north,
        "span_deg": {
            "lat": round(bounds.lat_span, 6),
            "lon": round(bounds.lon_span, 6),
        },
        "containment": "west <= longitude < east 且 south <= latitude < north（半开矩形）",
    }


def bounds_payload(ctx: AreaContext) -> dict:
    """只返回四个边界（供前端把结果与当前区域比对）。"""
    return ctx.bounds.as_dict()


def ship_type_values(values: Iterable[str] | None) -> list[str] | None:
    """规范化船型筛选参数：空列表视为全部（None）。"""
    if values is None:
        return None
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return cleaned or None
