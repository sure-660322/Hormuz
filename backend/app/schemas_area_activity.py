"""区域船舶活动与进出分析的 REST 响应模型（issue #41 第一阶段）。

契约见 docs/area_activity.md §4；字段与 services/area_activity 的输出一一对应，
前端类型（frontend/src/api.ts 等）在本阶段尚未同步，属后续任务。
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AreaBoundsModel(BaseModel):
    south: float
    west: float
    north: float
    east: float


class AreaModel(BaseModel):
    area_id: str
    name: str
    version: str | None = None
    is_default: bool
    basis: str
    bounds: AreaBoundsModel
    span_deg: dict[str, float]
    containment: str


class AlgorithmModel(BaseModel):
    name: str
    version: str
    params: dict[str, Any]


class FixModel(BaseModel):
    id: int | None = None
    recorded_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None


class EventModel(BaseModel):
    observed: bool
    observed_at: datetime | None = None
    bracket_seconds: float | None = None
    inside_fix: FixModel | None = None
    outside_fix: FixModel | None = None
    outside_evidence_in_context: bool = True
    near_boundary: bool = False
    wide_bracket: bool = False
    same_second_conflict: bool = False
    in_window: bool = False


class SegmentModel(BaseModel):
    segment_no: int
    start_at: datetime
    end_at: datetime
    start_fix_id: int | None = None
    end_fix_id: int | None = None
    seconds: float
    in_window_seconds: float
    fix_count: int


class VisitModel(BaseModel):
    visit_key: str
    ship_id: int
    ship_name: str | None = None
    mmsi: str | None = None
    ship_type: str | None = None
    entry: EventModel
    exit: EventModel
    prior_state: str
    first_inside_at: datetime
    last_inside_at: datetime
    fix_count: int
    segment_count: int
    segments: list[SegmentModel]
    observed_seconds: float
    window_seconds: float
    unobserved_gap_seconds: float
    started_before_window: bool
    touches_window: bool
    status: str
    flags: list[str]


class DailyModel(BaseModel):
    date: str
    ships_observed: int
    observed_entry_count: int
    observed_exit_count: int
    observed_ship_seconds: float
    observed_ship_hours: float
    visits_touching_day: int
    complete_visit_count: int
    truncated_visit_count: int
    interrupted_visit_count: int
    uncertain_visit_count: int


class SnapshotShipModel(BaseModel):
    ship_id: int
    name: str | None = None
    mmsi: str | None = None
    ship_type: str | None = None
    flag: str | None = None
    fix_id: int | None = None
    latitude: float
    longitude: float
    speed: float | None = None
    recorded_at: datetime
    age_seconds: float
    fresh: bool
    inside: bool


class CoverageModel(BaseModel):
    source: str
    batch_ids: list[int]
    batch_days: list[str]
    scope_start: datetime | None = None
    scope_end: datetime | None = None
    scoped_fix_count: int | None = None
    region_fix_count: int | None = None
    window_region_fix_count: int | None = None
    first_fix_at: datetime | None = None
    last_fix_at: datetime | None = None
    note: str


class MetricModel(BaseModel):
    key: str
    label: str
    unit: str
    a: float
    b: float
    delta: float
    change_rate: float | None = None


class DefaultAreaResponse(BaseModel):
    area: AreaModel
    algorithm: AlgorithmModel
    limitations: list[str]


class SnapshotResponse(BaseModel):
    status: str
    area: AreaModel
    query: dict[str, Any]
    algorithm: AlgorithmModel
    coverage: CoverageModel
    summary: dict[str, Any]
    ships: list[SnapshotShipModel]
    limits: dict[str, Any]
    limitations: list[str]


class ActivityResponse(BaseModel):
    status: str
    area: AreaModel
    query: dict[str, Any]
    algorithm: AlgorithmModel
    coverage: CoverageModel
    summary: dict[str, Any]
    daily: list[DailyModel]
    visits: list[VisitModel]
    limits: dict[str, Any]
    limitations: list[str]


class CompareResponse(BaseModel):
    status: str
    area: AreaModel
    algorithm: AlgorithmModel
    windows: dict[str, Any]
    comparability: dict[str, Any]
    metrics: list[MetricModel]
    a: dict[str, Any]
    b: dict[str, Any]
    limitations: list[str]


class AreaResolveRequest(BaseModel):
    """手动圈选/智能体请求的矩形解析（结构校验由模型完成，业务校验在 service）。"""

    west: float
    south: float
    east: float
    north: float
    area_id: str | None = None


class AreaResolveResponse(BaseModel):
    status: str
    area: AreaModel
    message: str
    limitations: list[str]


class ShipTypeOptionModel(BaseModel):
    value: str
    label: str
    raw_values: list[str]
    count: int
    count_scope: str


class ShipTypesResponse(BaseModel):
    status: str
    source: str
    total_ships: int
    ship_types: list[ShipTypeOptionModel]
    reserved: list[ShipTypeOptionModel]
    count: int
    limitations: list[str]

