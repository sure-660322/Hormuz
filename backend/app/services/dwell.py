"""Service layer for P3 /api/dwell: filters, GeoJSON assembly, freshness.

Dwell rows are precomputed by backend/build_ship_dwell.py; this layer only
reads the derived table and assembles the response (plan section 5).
"""
import json

from sqlalchemy.orm import Session

from backend.app.repositories import dwell as dwell_repo
from backend.app.services.tracks import parse_window

MAX_FEATURES = 5000


def get_dwell(db: Session, kind: str | None, from_raw: str | None, to_raw: str | None) -> dict:
    if kind is not None and kind not in dwell_repo.KINDS:
        raise ValueError(f"kind 必须是 {'/'.join(dwell_repo.KINDS)}")
    start, end = parse_window(from_raw, to_raw)

    manifest = dwell_repo.fetch_manifest(db)
    if manifest is None:
        return {"status": "not_built",
                "message": "停留派生层尚未重建，请先运行 backend/build_ship_dwell.py"}

    rows = dwell_repo.fetch_dwells(db, kind, start, end, MAX_FEATURES + 1)
    truncated = len(rows) > MAX_FEATURES
    rows = rows[:MAX_FEATURES]

    features = [
        {
            "type": "Feature",
            "geometry": json.loads(row["geometry"]),
            "properties": {
                "ship_id": row["ship_id"],
                "ship_name": row["ship_name"],
                "mmsi": row["mmsi"],
                "ship_type": row["ship_type"],
                "dwell_no": row["dwell_no"],
                "kind": row["kind"],
                "enter_at": row["enter_at"],
                "leave_at": row["leave_at"],
                "duration_min": float(row["duration_min"]),
                "displacement_radius_m": float(row["displacement_radius_m"]),
                "max_speed_kn": float(row["max_speed_kn"]),
                "point_count": row["point_count"],
                "is_simulated": row["data_source"] == "simulation",
            },
        }
        for row in rows
    ]

    params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
    source_max = dwell_repo.fetch_source_max_time(db)
    stale = source_max is not None and manifest["built_at"] < source_max
    sources = {row["data_source"] for row in rows}
    is_simulated = sources == {"simulation"} if sources else None

    return {
        "status": "ok" if features else "no_data",
        "type": "FeatureCollection",
        "features": features,
        "feature_count": len(features),
        "truncated": truncated,
        "kind": kind,
        "window": [start, end] if start else None,
        "params": params,
        "built_at": manifest["built_at"],
        "stale": stale,
        "is_simulated": is_simulated,
        "note": "教学模拟数据的停留识别结果，不代表真实锚地/漂航认定",
    }
