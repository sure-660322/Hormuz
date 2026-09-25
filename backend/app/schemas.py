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
