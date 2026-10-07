"""动态海峡通行统计 API（issue #40）。

手动「通行分析」面板的四个只读端点，与智能体新工具共用
services/agent/strait_statistics.py 的同一统计/比较服务：
路由只校验参数，分窗/去重/汇总/比较全部在服务端完成。

- GET  /api/strait-passages/meta        船型选项与来源批次覆盖元数据
- POST /api/strait-passages/statistics  单时段按日统计 + 全窗汇总
- POST /api/strait-passages/compare     A/B 两期比较（差值/变化率/可比性）
- GET  /api/strait-passages/evidence    证据明细分页（不影响汇总完整性）

时间参数必须带时区（统一 UTC），后端使用半开区间 [start_at, end_at)。
查询只读：不触发导入、迁移或派生重建。
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services.agent.serialization import to_jsonable
from backend.app.services.agent import strait_statistics as stats

router = APIRouter(prefix="/api/strait-passages", tags=["strait-passages"])


def _error(status_code: int, code: str, message: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "request_id": str(uuid.uuid4())},
    )


class StatisticsRequest(BaseModel):
    start_at: str = Field(description="ISO 8601，必须带时区（统一 UTC）")
    end_at: str = Field(description="ISO 8601，必须带时区；区间半开 [start_at, end_at)")
    ship_types: list[str] | None = Field(default=None, description="船型多选；省略=全部；含 __unknown__ 表示含未知/缺失")
    direction: str | None = Field(default=None, description="inbound=入湾 / outbound=出湾 / 省略=全部")


class CompareRequest(BaseModel):
    a_start_at: str
    a_end_at: str
    b_start_at: str
    b_end_at: str
    ship_types: list[str] | None = None
    direction: str | None = None


def _parse_time(raw: str, name: str):
    from backend.app.services.agent.results import parse_time_arg
    try:
        return parse_time_arg(raw)
    except ValueError as exc:
        _error(422, "INVALID_REQUEST", f"{name}：{exc}")


@router.get("/meta")
def passage_meta(db: Session = Depends(get_db)):
    """船型选项（含未知/缺失桶）与按 source_batch_id 的来源覆盖；不硬编码历史数量。"""
    try:
        return to_jsonable(stats.get_strait_passage_meta(db))
    except SQLAlchemyError:
        _error(500, "DATA_QUERY_FAILED", "数据查询失败")


@router.post("/statistics")
def passage_statistics(request: StatisticsRequest, db: Session = Depends(get_db)):
    """单时段按日统计与全窗汇总（手动面板与智能体工具同一服务）。"""
    start_at = _parse_time(request.start_at, "start_at")
    end_at = _parse_time(request.end_at, "end_at")
    try:
        result = stats.query_strait_passage_statistics(
            db, start_at, end_at, ship_types=request.ship_types, direction=request.direction,
        )
    except ValueError as exc:
        _error(422, "INVALID_REQUEST", str(exc))
    except SQLAlchemyError:
        _error(500, "DATA_QUERY_FAILED", "数据查询失败")
    return to_jsonable(result)


@router.post("/compare")
def passage_compare(request: CompareRequest, db: Session = Depends(get_db)):
    """A/B 两期比较：两期指标、差值、(B-A)/A 变化率与覆盖可比性。"""
    a_start = _parse_time(request.a_start_at, "a_start_at")
    a_end = _parse_time(request.a_end_at, "a_end_at")
    b_start = _parse_time(request.b_start_at, "b_start_at")
    b_end = _parse_time(request.b_end_at, "b_end_at")
    try:
        result = stats.compare_strait_passage_statistics(
            db, a_start, a_end, b_start, b_end,
            ship_types=request.ship_types, direction=request.direction,
        )
    except ValueError as exc:
        _error(422, "INVALID_REQUEST", str(exc))
    except SQLAlchemyError:
        _error(500, "DATA_QUERY_FAILED", "数据查询失败")
    return to_jsonable(result)


@router.get("/evidence")
def passage_evidence(
    start_at: str = Query(description="ISO 8601，必须带时区"),
    end_at: str = Query(description="ISO 8601，必须带时区"),
    day: str | None = Query(default=None, description="UTC 日期 YYYY-MM-DD，限定该日明细"),
    ship_types: list[str] | None = Query(default=None),
    direction: str | None = Query(default=None),
    include_uncertain: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=stats.MAX_EVIDENCE_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """通行证据明细分页：船舶标识、方向、两端报位时间/位置与完成观测时间。"""
    start = _parse_time(start_at, "start_at")
    end = _parse_time(end_at, "end_at")
    parsed_day = None
    if day is not None:
        from datetime import date as date_type
        try:
            parsed_day = date_type.fromisoformat(day)
        except ValueError:
            _error(422, "INVALID_REQUEST", "day 必须是 YYYY-MM-DD")
    try:
        result = stats.query_strait_passage_evidence(
            db, start, end, day=parsed_day, ship_types=ship_types,
            direction=direction, include_uncertain=include_uncertain,
            page=page, page_size=page_size,
        )
    except ValueError as exc:
        _error(422, "INVALID_REQUEST", str(exc))
    except SQLAlchemyError:
        _error(500, "DATA_QUERY_FAILED", "数据查询失败")
    return to_jsonable(result)
