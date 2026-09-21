"""Service layer for P4 /api/encounters: filters, assembly, freshness, rebuild.

Encounters are precomputed by backend/build_encounters.py (imported here for
the controlled synchronous POST /analyze); the GET path only reads the derived
table (plan section 4: never computed on the request path).
"""
import json

from sqlalchemy.orm import Session

from backend.app.repositories import encounters as enc_repo
from backend.app.services.tracks import parse_window

MAX_ROWS = 2000
DEFAULT_MAX_DISTANCE_NM = 10.0


def list_encounters(db: Session, from_raw: str | None, to_raw: str | None,
                    max_distance_nm: float | None) -> dict:
    if max_distance_nm is not None and max_distance_nm <= 0:
        raise ValueError("max_distance_nm 必须为正数")
    start, end = parse_window(from_raw, to_raw)

    manifest = enc_repo.fetch_manifest(db)
    if manifest is None:
        return {"status": "not_built",
                "message": "相遇派生层尚未重建，请先运行 backend/build_encounters.py 或 POST /api/encounters/analyze"}

    max_m = (max_distance_nm if max_distance_nm is not None else DEFAULT_MAX_DISTANCE_NM) * 1852.0
    rows = enc_repo.fetch_encounters(db, start, end, max_m, MAX_ROWS + 1)
    truncated = len(rows) > MAX_ROWS
    rows = rows[:MAX_ROWS]

    encounters = [
        {
            "ship_a": {"id": r["ship_a_id"], "name": r["ship_a_name"],
                       "mmsi": r["ship_a_mmsi"], "ship_type": r["ship_a_type"]},
            "ship_b": {"id": r["ship_b_id"], "name": r["ship_b_name"],
                       "mmsi": r["ship_b_mmsi"], "ship_type": r["ship_b_type"]},
            "min_distance_m": float(r["min_distance_m"]),
            "min_distance_nm": round(float(r["min_distance_m"]) / 1852.0, 3),
            "overlap_minutes": float(r["overlap_minutes"]),
            "period_start": r["period_start"],
            "period_end": r["period_end"],
            "closest_point": json.loads(r["closest_point"]) if r["closest_point"] else None,
            "is_simulated": r["data_source"] == "simulation",
        }
        for r in rows
    ]

    params = manifest["params"] if isinstance(manifest["params"], dict) else json.loads(manifest["params"])
    source_max = enc_repo.fetch_source_max_time(db)
    stale = source_max is not None and manifest["built_at"] < source_max

    return {
        "status": "ok" if encounters else "no_data",
        "encounters": encounters,
        "count": len(encounters),
        "truncated": truncated,
        "window": [start, end] if start else None,
        "max_distance_nm_filter": max_distance_nm,
        "params": params,
        "built_at": manifest["built_at"],
        "stale": stale,
        "note": "模拟数据相遇（时空邻近）分析，接近不等于有交互；不指向真实船舶行为",
    }


def analyze_encounters(db: Session, distance_nm: float, overlap_min: int,
                       sample_seconds: int) -> dict:
    """Controlled synchronous rebuild; body params validated by the router."""
    # Imported here so the API process does not pay the import cost on reads.
    from backend.build_encounters import run_build

    result = run_build(distance_nm, overlap_min, sample_seconds, None)
    return {
        "status": "ok",
        "manifest_id": result["manifest_id"],
        "summary": result["summary"],
        "params": {"distance_nm": distance_nm, "overlap_min": overlap_min,
                   "sample_seconds": sample_seconds},
    }
