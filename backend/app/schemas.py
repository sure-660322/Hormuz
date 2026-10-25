#schemas.py 定义FastAPI允许向前端返回什么json
#models.py定义数据如何存入PostgreSQL
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict

#BaseModel:Pydantic的数据验证和转换基类
#ShipResponse：一艘船返回给前端时的json格式
#from_attributes=True：允许 Pydantic 从 SQLAlchemy 对象的属性中读取数据，例如读取 ship.name
class ShipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:int
    mmsi:str
    name:str | None
    ship_type:str | None
    ship_type_cn_raw:str | None
    flag:str | None
    imo:str | None
    callsign:str | None

class ShipPositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ship_id: int
    latitude: float
    longitude: float
    speed: float
    course: float
    heading: float | None
    recorded_at: datetime

class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    title_zh: str
    summary_zh: str
    event_type: str
    event_datetime: datetime | None
    event_time_text: str | None
    event_location_text: str | None
    event_region: str | None
    event_lat: float | None
    event_lng: float | None
    geo_method: str | None
    geo_note: str | None
    coverage_count: int
    perspectives: list[str]
    mentioned_vessels: list[str]
    publish_date_min: date | None
    publish_date_max: date | None


class EventNewsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    story_id: str
    title_zh: str
    summary_zh: str
    title: str
    canonical_url: str
    media_name: str
    perspective: str
    publish_date: date


class NearbyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:int
    title:str
    description:str
    event_type:str
    latitude:float
    longitude:float
    occurred_at:datetime
    source_name:str | None
    source_url: str | None
    distance_km:float

class ShipMapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mmsi: str
    name: str | None
    ship_type: str | None
    ship_type_cn_raw: str | None
    flag: str | None
    imo: str | None
    callsign: str | None
    latitude: float
    longitude: float
    speed: float
    course: float
    heading: float | None
    recorded_at: datetime


class ShipSnapshotFrameResponse(BaseModel):
    at: datetime
    ships: list[ShipMapResponse]


class ShipSnapshotWindowResponse(BaseModel):
    frames: list[ShipSnapshotFrameResponse]
    max_age_seconds: int


class SimulationMetaResponse(BaseModel):
    start_at: datetime | None
    end_at: datetime | None
    frame_interval_seconds: int
    frame_count: int
    ship_count: int
    position_count: int
    event_count: int
    is_simulated: bool
    has_events: bool = True
    has_derived: bool = True


class CaseArticleResponse(BaseModel):
    image_url: str | None = None
    image_source_url: str | None = None
    image_kind: str | None = None
    title: str
    media: str
    publish_date: date
    url: str
    # issue #56：1–2 句摘要，证据列表默认展示；不复制报道全文。
    summary: str = ""


class CaseNewsArticleResponse(BaseModel):
    story_id: str
    title: str
    media: str
    publish_date: date
    url: str
    summary: str


class CaseNewsEntryResponse(BaseModel):
    case_id: str
    event_id: str
    title_zh: str
    summary_zh: str
    vessel_name: str
    mmsi: str
    imo: str
    available: bool
    event_day: date
    articles: list[CaseNewsArticleResponse]


class CaseStageResponse(BaseModel):
    id: str
    title: str
    date: date
    start_at: datetime
    end_at: datetime
    summary: str
    articles: list[CaseArticleResponse]


class CaseEvidenceResponse(BaseModel):
    # issue #56：展示元数据。kind 为 ais_observation / report / boundary / identity；
    # stage_ids 为空表示适用于整个案例（案例级证据），否则列出适用阶段 id。
    id: str
    kind: str
    stage_ids: list[str] = []
    summary: str = ""
    title: str
    observation: str
    boundary: str
    at: datetime | None = None
    url: str | None = None


class MaritimeCaseResponse(BaseModel):
    id: str
    title: str
    mmsi: str
    imo: str
    data_source: str
    supplier: str
    ready: bool
    ship_id: int | None
    start_at: datetime | None
    end_at: datetime | None
    position_count: int
    stages: list[CaseStageResponse]
    limitations: list[str]
    display_title: str = "中海北冰洋"
    vessel_label: str = "集装箱船 · CSCL ARCTIC OCEAN"
    date_label: str = "2026.03.27 — 03.31"
    overview_summary: str = "沿五日历史航迹，查看首次尝试、两次尝试之间的航行过程与再次通过。阶段用于组织浏览，报道与 AIS 观测分别提供证据。"
    unavailable_reason: str = "轨迹尚未导入，可先阅读报道。"
    evidence: list[CaseEvidenceResponse] = []
