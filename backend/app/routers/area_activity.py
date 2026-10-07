"""区域船舶活动与进出分析 REST API（issue #41 第一阶段）。

- GET /api/area-activity/default-area — 默认分析区域的版本、边界与依据
- GET /api/area-activity/snapshot     — 历史时刻在场
- GET /api/area-activity/activity     — 时段出现、进出与停留（按日汇总）
- GET /api/area-activity/compare      — 同区同时段筛选的 A/B 比较

路由只做参数校验与错误映射，业务判定全部在 services/area_activity（手动界面与
后续智能体工具共用同一服务）。契约见 docs/area_activity.md §4。
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas_area_activity import (
    ActivityResponse,
    CompareResponse,
    DefaultAreaResponse,
    SnapshotResponse,
)
from backend.app.services.area_activity import boundaries, service

router = APIRouter(prefix="/api/area-activity", tags=["area-activity"])


def _error(status_code: int, code: str, message: str):
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "request_id": str(uuid.uuid4())},
    )


def invalid(message: str):
    _error(422, "INVALID_REQUEST", message)


def _run(db: Session, action):
    """统一错误映射：参数错误 422，语句超时与数据库不可用 503。"""
    try:
        return action()
    except service.AreaActivityError as exc:
        invalid(str(exc))
    except ValueError as exc:
        # 边界校验（AreaBounds.validate / resolve_bounds）也按参数错误处理
        invalid(str(exc))
    except OperationalError as exc:
        message = str(exc).lower()
        try:
            db.rollback()
        except Exception:  # noqa: BLE001 回滚失败不能掩盖原始错误
            pass
        if "statement timeout" in message or "canceling statement" in message:
            _error(503, "QUERY_TIMEOUT", "查询超过服务端时间上限，请缩小矩形或时间范围")
        _error(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用，请稍后重试")
    except SQLAlchemyError:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _error(503, "DATABASE_UNAVAILABLE", "数据库暂时不可用，请稍后重试")


@router.get("/default-area", response_model=DefaultAreaResponse)
def get_default_area():
    return service.default_area_payload()


@router.get("/snapshot", response_model=SnapshotResponse)
def get_area_snapshot(
    at: datetime = Query(..., description="历史时刻，带时区的 ISO 8601"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
    ship_type: list[str] | None = Query(None, description="船型筛选，可重复；__missing__/__unknown__ 为保留值"),
    freshness_seconds: int | None = Query(None, ge=1, le=86_400),
    limit: int | None = Query(None, ge=1, le=5_000),
    db: Session = Depends(get_db),
):
    def action():
        bounds, is_default = boundaries.resolve_bounds(south, west, north, east)
        return service.query_snapshot(
            db, at=at, bounds=bounds, is_default=is_default,
            ship_type_values=ship_type, freshness_seconds=freshness_seconds, limit=limit,
        )

    return _run(db, action)


@router.get("/activity", response_model=ActivityResponse)
def get_area_activity(
    start: datetime = Query(..., description="窗口开始，带时区，含"),
    end: datetime = Query(..., description="窗口结束，带时区，不含"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
    ship_type: list[str] | None = Query(None, description="船型筛选，可重复"),
    batch_ids: list[int] | None = Query(None, description="来源批次白名单，可重复"),
    state_lookback_seconds: int | None = Query(None, ge=0, le=86_400),
    state_lookahead_seconds: int | None = Query(None, ge=0, le=86_400),
    visit_limit: int | None = Query(None, ge=1, le=2_000),
    db: Session = Depends(get_db),
):
    def action():
        bounds, is_default = boundaries.resolve_bounds(south, west, north, east)
        return service.query_activity(
            db, start=start, end=end, bounds=bounds, is_default=is_default,
            ship_type_values=ship_type, batch_ids=batch_ids,
            lookback_seconds=state_lookback_seconds,
            lookahead_seconds=state_lookahead_seconds,
            visit_limit=visit_limit,
        )

    return _run(db, action)


@router.get("/compare", response_model=CompareResponse)
def get_area_activity_compare(
    start_a: datetime = Query(..., description="A 窗口开始，带时区"),
    end_a: datetime = Query(..., description="A 窗口结束，带时区"),
    start_b: datetime = Query(..., description="B 窗口开始，带时区"),
    end_b: datetime = Query(..., description="B 窗口结束，带时区"),
    west: float | None = Query(None, ge=-180, le=180),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    north: float | None = Query(None, ge=-90, le=90),
    ship_type: list[str] | None = Query(None, description="船型筛选，两期共用，可重复"),
    batch_ids: list[int] | None = Query(None, description="来源批次白名单，两期共用"),
    state_lookback_seconds: int | None = Query(None, ge=0, le=86_400),
    state_lookahead_seconds: int | None = Query(None, ge=0, le=86_400),
    visit_limit: int | None = Query(None, ge=1, le=2_000),
    db: Session = Depends(get_db),
):
    def action():
        bounds, is_default = boundaries.resolve_bounds(south, west, north, east)
        return service.compare_activity(
            db, start_a=start_a, end_a=end_a, start_b=start_b, end_b=end_b,
            bounds=bounds, is_default=is_default,
            ship_type_values=ship_type, batch_ids=batch_ids,
            lookback_seconds=state_lookback_seconds,
            lookahead_seconds=state_lookahead_seconds,
            visit_limit=visit_limit,
        )

    return _run(db, action)
