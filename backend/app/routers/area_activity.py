"""区域船舶活动与进出分析 REST API（issue #41）。

- GET  /api/area-activity/default-area — 默认分析区域的版本、边界与依据
- GET  /api/area-activity/ship-types   — 船型候选目录（真实取值分布，不硬编码）
- POST /api/area-activity/resolve-area — 解析/校验一个矩形并回显区域标识（圈选与智能体共用）
- GET  /api/area-activity/snapshot     — 历史时刻在场
- GET  /api/area-activity/activity     — 时段出现、进出与停留（按日汇总）
- GET  /api/area-activity/compare      — 同区同时段筛选的 A/B 比较

路由只做参数校验与错误映射，业务判定全部在 services/area_activity（手动界面与
智能体工具共用同一服务）。契约见 docs/area_activity.md §4。
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas_area_activity import (
    ActivityResponse,
    AreaResolveRequest,
    AreaResolveResponse,
    CompareResponse,
    DefaultAreaResponse,
    ShipTypesResponse,
    SnapshotResponse,
)
from backend.app.services.area_activity import boundaries, service, ship_types

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


@router.get("/ship-types", response_model=ShipTypesResponse)
def get_ship_types(db: Session = Depends(get_db)):
    """船型候选：来自 ships 表真实取值分布，前端与智能体共用同一目录。"""

    def action():
        return ship_types.ship_type_catalog(db)

    return _run(db, action)


@router.post("/resolve-area", response_model=AreaResolveResponse)
def post_resolve_area(payload: AreaResolveRequest):
    """把手动圈选/智能体给出的矩形解析成带版本的区域标识。

    与 snapshot/activity/compare 使用同一套半开边界与跨度校验：非法、超限或跨 180°
    的矩形在这里就以 422 拒绝，避免前端拿着一个后端不接受的区域去查询。
    """

    def action():
        bounds, is_default = boundaries.resolve_bounds(
            payload.south, payload.west, payload.north, payload.east
        )
        described = boundaries.describe_area(bounds, is_default=is_default)
        area = {
            key: described[key]
            for key in (
                "area_id", "name", "version", "is_default",
                "basis", "bounds", "span_deg", "containment",
            )
        }
        if not is_default and payload.area_id and payload.area_id.strip():
            area["area_id"] = payload.area_id.strip()
        message = (
            "使用默认分析区域；如需自选区域请显式给出 west/south/east/north"
            if is_default
            else "已接受自选矩形：西/南含、东/北不含（半开），跨度上限 "
                 f"{service.params.MAX_RECT_SPAN_DEG:g}°"
        )
        return {
            "status": "ok",
            "area": area,
            "message": message,
            "limitations": list(service.STANDING_LIMITATIONS),
        }

    return _run(None, action)


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
