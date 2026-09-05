#schemas.py 定义FastAPI允许向前端返回什么json
#models.py定义数据如何存入PostgreSQL
from datetime import datetime
from pydantic import BaseModel, ConfigDict

#BaseModel:Pydantic的数据验证和转换基类
#ShipResponse：一艘船返回给前端时的json格式
#from_attributes=True：允许 Pydantic 从 SQLAlchemy 对象的属性中读取数据，例如读取 ship.name
class ShipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:int
    mmsi:str
    name:str
    ship_type:str
    flag:str
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

    id:int
    title:str
    description:str
    event_type:str
    latitude:float
    longitude:float
    occurred_at:datetime
    source_name:str | None
    source_url:str | None

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
    name: str
    ship_type: str
    flag: str
    imo: str | None
    callsign: str | None
    latitude: float
    longitude: float
    speed: float
    course: float
    heading: float | None
    recorded_at: datetime


class SimulationMetaResponse(BaseModel):
    start_at: datetime | None
    end_at: datetime | None
    frame_interval_seconds: int
    frame_count: int
    ship_count: int
    position_count: int
    event_count: int
    is_simulated: bool
