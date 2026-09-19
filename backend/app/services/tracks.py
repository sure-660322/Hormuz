"""Service layer for /api/tracks: validation helpers, assembly, freshness.

Frontend receives finished spatio-temporal results; no interpolation or
speed inference happens outside the database (plan section 5).
"""
from datetime import datetime, timedelta
import json

from sqlalchemy.orm import Session

from backend.app.repositories import tracks as tracks_repo

MAX_WINDOW = timedelta(hours=24)
DEFAULT_BUCKET_SECONDS = 300
MAX_POINTS_FULL = 5000
MAX_POINTS_SIMPLIFIED = 5000
LEVELS = ("full", "simplified")


def parse_window(from_raw: str | None, to_raw: str | None) -> tuple[datetime | None, datetime | None]:
    """Both or neither; timezone required; from < to; window <= 24 h."""
    if (from_raw is None) != (to_raw is None):
        raise ValueError("from 与 to 必须同时提供或同时省略")
    if from_raw is None:
        return None, None
    try:
        start = datetime.fromisoformat(from_raw.replace("Z", "+00:00"))
        end = datetime.fromisoformat(to_raw.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("from/to 无法解析为 ISO 8601 时间") from None
    if start.tzinfo is None or start.utcoffset() is None or end.tzinfo is None or end.utcoffset() is None:
        raise ValueError("from/to 必须包含显式时区")
    if not start < end:
        raise ValueError("from 必须早于 to")
    if end - start > MAX_WINDOW:
        raise ValueError("查询窗口不能超过 24 小时，请缩小范围")
    return start, end


def get_ship_tracks(
    db: Session,
    ship_id: int,
    from_raw: str | None,
    to_raw: str | None,
    level: str,
    bucket_seconds: int | None,
) -> dict:
    if level not in LEVELS:
        raise ValueError(f"level 必须是 {'/'.join(LEVELS)}")
    if bucket_seconds is None:
        bucket_seconds = DEFAULT_BUCKET_SECONDS
    if not 30 <= bucket_seconds <= 3600:
        raise ValueError("bucket_seconds 必须在 30–3600 之间")
    start, end = parse_window(from_raw, to_raw)

    ship = tracks_repo.fetch_ship(db, ship_id)
    if ship is None:
        return {"status": "not_found", "ship_id": ship_id}

    manifest = tracks_repo.fetch_manifest(db)
    if manifest is None:
        return {"status": "not_built", "ship_id": ship_id,
                "message": "派生轨迹尚未重建，请先运行 backend/build_ship_tracks.py"}

    if level == "full":
        segments = tracks_repo.fetch_overlapping_segments(db, ship_id, start, end)
        total_points = sum(int(row["point_count"]) for row in segments)
        if total_points > MAX_POINTS_FULL:
            raise ValueError(
                f"窗口内共 {total_points} 个轨迹点，超过 full 上限 {MAX_POINTS_FULL}；"
                "请缩小时间窗或使用 level=simplified"
            )
        assembled = [
            {
                "segment_no": row["segment_no"],
                "t_start": row["t_start"],
                "t_end": row["t_end"],
                "point_count": row["point_count"],
                "data_source": row["data_source"],
                "geometry": json.loads(row["geometry"]),
                "speed": [[float(pair[0]), float(pair[1])] for pair in row["speed"]],
            }
            for row in segments
        ]
    else:
        samples = tracks_repo.fetch_bucket_samples(db, ship_id, start, end, bucket_seconds)
        if len(samples) > MAX_POINTS_SIMPLIFIED:
            raise ValueError(
                f"抽稀后仍有 {len(samples)} 个点，超过上限 {MAX_POINTS_SIMPLIFIED}；"
                "请增大 bucket_seconds 或缩小时间窗"
            )
        assembled = [
            {
                "segment_no": 0,
                "t_start": datetime.fromtimestamp(float(samples[0]["t"]), tz=start.tzinfo) if samples else None,
                "t_end": datetime.fromtimestamp(float(samples[-1]["t"]), tz=start.tzinfo) if samples else None,
                "point_count": len(samples),
                "data_source": tracks_repo.fetch_ship_data_source(db, ship_id),
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[row["lng"], row["lat"]] for row in samples],
                },
                "speed": [[float(row["t"]), float(row["speed"])] for row in samples],
            }
        ] if samples else []

    sources = {row["data_source"] for row in assembled if row.get("data_source")}
    data_source = sources.pop() if len(sources) == 1 else None
    source_max = tracks_repo.fetch_source_max_time(db, data_source)
    stale = source_max is not None and manifest["built_at"] < source_max

    return {
        "status": "ok" if assembled else "no_data",
        "ship": dict(ship),
        "level": level,
        "bucket_seconds": bucket_seconds if level == "simplified" else None,
        "gap_minutes": manifest["params"].get("gap_minutes") if isinstance(manifest["params"], dict) else json.loads(manifest["params"])["gap_minutes"],
        "built_at": manifest["built_at"],
        "stale": stale,
        "is_simulated": data_source == "simulation",
        "segments": assembled,
    }
