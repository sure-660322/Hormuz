"""Summarise the project's existing regional AIS dataset as a reference check.

Read-only. Produces the files under ``reference/`` that document what could (and could
not) be learned from the historical data already in this repository:

    reference/observed_extent.json   - spatial extent and row counts
    reference/observed_cells.json    - coarse occupancy grid (0.02 deg cells)
    reference/transit_gates.json     - gate names and centroids in the transit file

Why this matters: the historical dataset is a sparse sample of the region. In the Strait
of Hormuz itself it contains almost no observations, so it cannot be used as a water or
land reference for the simulation. That is why the coastline reference
(``reference/ne_10m_land.geojson``) is used instead, and this script records the evidence.

Run:
    python tools/summarise_reference_ais.py
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT.parent
DATA = PROJECT / "data"

CELL_DEG = 0.02
REGION = {"lat_min": 23.5, "lat_max": 30.5, "lon_min": 46.0, "lon_max": 60.0}


def parse_point(text_value: str) -> tuple[float, float] | None:
    """Parse 'SRID=4326;POINT(lon lat)' into (lon, lat)."""
    if not text_value or "POINT(" not in text_value:
        return None
    inner = text_value.split("POINT(")[1].rstrip(")")
    parts = inner.split()
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        return None


def main() -> int:
    out = ROOT / "reference"
    out.mkdir(parents=True, exist_ok=True)

    # ---- transit gates ----
    gates: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    transit_file = DATA / "crossing_data" / "transit_events.csv"
    if transit_file.exists():
        with transit_file.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                point = parse_point(row.get("geom", ""))
                if point:
                    gates[(row["gate_name"], row["direction"])].append(point)

    gate_summary = {}
    for (name, direction), points in sorted(gates.items()):
        gate_summary[f"{name} | {direction}"] = {
            "n": len(points),
            "centroid_lat": round(sum(p[1] for p in points) / len(points), 5),
            "centroid_lon": round(sum(p[0] for p in points) / len(points), 5),
        }
    (out / "transit_gates.json").write_text(
        json.dumps({
            "source": "data/crossing_data/transit_events.csv",
            "note_zh": "现有过境数据只覆盖迪拜/杰贝阿里进出港，不含海峡内的分道通航数据。",
            "gates": gate_summary,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # ---- occupancy grid from positions ----
    cells: set[tuple[int, int]] = set()
    total = 0
    bounds = {"lon_min": float("inf"), "lon_max": float("-inf"),
              "lat_min": float("inf"), "lat_max": float("-inf")}
    positions_file = DATA / "ship_data" / "ais_positions.csv"
    if positions_file.exists():
        with positions_file.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                point = parse_point(row.get("geom", ""))
                if not point:
                    continue
                lon, lat = point
                total += 1
                bounds["lon_min"] = min(bounds["lon_min"], lon)
                bounds["lon_max"] = max(bounds["lon_max"], lon)
                bounds["lat_min"] = min(bounds["lat_min"], lat)
                bounds["lat_max"] = max(bounds["lat_max"], lat)
                if (REGION["lat_min"] <= lat <= REGION["lat_max"]
                        and REGION["lon_min"] <= lon <= REGION["lon_max"]):
                    cells.add((int(math.floor(lon / CELL_DEG)), int(math.floor(lat / CELL_DEG))))

    strait_cells = [
        (cx, cy) for cx, cy in cells
        if 55.5 <= cx * CELL_DEG <= 57.0 and 25.5 <= cy * CELL_DEG <= 27.0
    ]
    (out / "observed_cells.json").write_text(
        json.dumps({
            "source": "data/ship_data/ais_positions.csv",
            "cell_deg": CELL_DEG,
            "region": REGION,
            "count": len(cells),
            "strait_region_cell_count": len(strait_cells),
            "note_zh": (
                "这是历史 AIS 观测到的位置占用网格，只能说明“这些格子曾有船位”，"
                "不能说明“其他格子是陆地”。海峡本身观测极稀疏，因此不作为陆地判定依据。"
            ),
            "cells": [[c[0], c[1]] for c in sorted(cells)],
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "observed_extent.json").write_text(
        json.dumps({
            "source": "data/ship_data/ais_positions.csv",
            "rows_total": total,
            "extent": {k: round(v, 4) for k, v in bounds.items()},
            "gulf_region_cells": len(cells),
            "strait_region_cells": len(strait_cells),
            "cell_deg": CELL_DEG,
            "conclusion_zh": (
                "现有区域 AIS 数据覆盖波斯湾至阿拉伯海，但在霍尔木兹海峡最窄段几乎没有观测，"
                "无法支撑陆地/水域判定，也无法据此重建真实航道。因此本次生成改用 Natural Earth "
                "1:10m 陆地面作为岸线参考，并明确其精度限制。"
            ),
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"过境门：{len(gate_summary)}")
    print(f"位置行数：{total}，区域网格：{len(cells)}，海峡区域网格：{len(strait_cells)}")
    print(f"范围：{ {k: round(v, 4) for k, v in bounds.items()} }")
    print(f"已写出到 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
