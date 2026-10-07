"""矩形边界：半开包含规则、校验、默认分析区域与边界距离。

内外判定只有一处实现（AreaBounds.contains），SQL 侧用同一规则写死，两者必须一致；
`location && ST_MakeEnvelope(...)` 只用于候选粗筛，粗筛超集不会改变半开判定的结果。
"""
from dataclasses import dataclass
from math import cos, radians

from backend.app.services.area_activity import params

EARTH_RADIUS_KM = 6371.0
KM_PER_DEG_LAT = 111.32


@dataclass(frozen=True)
class AreaBounds:
    """轴对齐分析矩形（半开：西/南含，东/北不含）。"""

    south: float
    west: float
    north: float
    east: float

    def contains(self, latitude: float, longitude: float) -> bool:
        """半开包含规则；与 SQL 中 `west <= lon < east AND south <= lat < north` 一致。"""
        return (
            self.west <= longitude < self.east
            and self.south <= latitude < self.north
        )

    @property
    def lat_span(self) -> float:
        return self.north - self.south

    @property
    def lon_span(self) -> float:
        return self.east - self.west

    def validate(self) -> None:
        """校验范围、顺序与跨度；非法即抛 ValueError（路由映射 422）。"""
        for name, value in (
            ("south", self.south), ("west", self.west),
            ("north", self.north), ("east", self.east),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"{name} 必须是数值")
            if value != value or value in (float("inf"), float("-inf")):
                raise ValueError(f"{name} 必须是有限数值")
        if not -90.0 <= self.south <= 90.0 or not -90.0 <= self.north <= 90.0:
            raise ValueError("纬度必须位于 [-90, 90]")
        if not -180.0 <= self.west <= 180.0 or not -180.0 <= self.east <= 180.0:
            raise ValueError("经度必须位于 [-180, 180]")
        if self.south >= self.north:
            raise ValueError("必须满足 south < north")
        if self.west >= self.east:
            raise ValueError(
                "必须满足 west < east；本接口不支持跨 180° 或跨零度经线的矩形"
            )
        if self.lat_span > params.MAX_RECT_SPAN_DEG or self.lon_span > params.MAX_RECT_SPAN_DEG:
            raise ValueError(
                f"矩形单边跨度不能超过 {params.MAX_RECT_SPAN_DEG:g}°，"
                f"当前纬度 {self.lat_span:g}°、经度 {self.lon_span:g}°"
            )

    def expanded(self, margin_deg: float) -> "AreaBounds":
        """外扩观测上下文；纬度截断到 ±90，仅供读取范围使用。"""
        return AreaBounds(
            south=max(-90.0, self.south - margin_deg),
            west=max(-180.0, self.west - margin_deg),
            north=min(90.0, self.north + margin_deg),
            east=min(180.0, self.east + margin_deg),
        )

    def distance_to_boundary_m(self, latitude: float, longitude: float) -> float:
        """点到矩形最近边的近似距离（米）；用于边界近邻标记，不参与计数。"""
        lat_margin = min(latitude - self.south, self.north - latitude) * KM_PER_DEG_LAT
        lon_scale = max(cos(radians(latitude)), 1e-6) * KM_PER_DEG_LAT
        lon_margin = min(longitude - self.west, self.east - longitude) * lon_scale
        return max(0.0, min(lat_margin, lon_margin) * 1000.0)

    def as_dict(self) -> dict:
        return {
            "south": self.south, "west": self.west,
            "north": self.north, "east": self.east,
        }


def default_bounds() -> AreaBounds:
    return AreaBounds(
        south=params.DEFAULT_SOUTH, west=params.DEFAULT_WEST,
        north=params.DEFAULT_NORTH, east=params.DEFAULT_EAST,
    )


def describe_area(bounds: AreaBounds, *, is_default: bool) -> dict:
    """结果中回显的区域信息：版本、边界、依据与包含规则。"""
    return {
        "area_id": params.DEFAULT_AREA_ID if is_default else "custom",
        "name": params.DEFAULT_AREA_NAME if is_default else "自定义分析矩形",
        "version": params.DEFAULT_AREA_VERSION if is_default else None,
        "is_default": is_default,
        "basis": params.DEFAULT_AREA_BASIS if is_default else "调用方显式提供的矩形（未做权威性核验）",
        "bounds": bounds.as_dict(),
        "span_deg": {"lat": round(bounds.lat_span, 6), "lon": round(bounds.lon_span, 6)},
        "containment": "west <= longitude < east 且 south <= latitude < north（半开矩形）",
    }


def resolve_bounds(
    south: float | None, west: float | None, north: float | None, east: float | None
) -> tuple[AreaBounds, bool]:
    """四个边界要么全给（自定义区域），要么全不给（默认区域）。"""
    values = (south, west, north, east)
    provided = [value is not None for value in values]
    if any(provided) and not all(provided):
        raise ValueError("west/south/east/north 必须同时给出或同时省略")
    if not any(provided):
        bounds = default_bounds()
        bounds.validate()
        return bounds, True
    bounds = AreaBounds(south=south, west=west, north=north, east=east)
    bounds.validate()
    return bounds, False


def split_ship_types(values: list[str] | None) -> tuple[list[str] | None, bool]:
    """拆分船型筛选：返回（精确匹配标签列表 | None, 是否显式全部）。"""
    if not values:
        return None, False
    cleaned = [value for value in values if value and value.strip()]
    if not cleaned:
        return None, False
    if any(value == params.SHIP_TYPE_ALL for value in cleaned):
        return None, True
    return cleaned, False
