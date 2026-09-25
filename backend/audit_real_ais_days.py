"""Stream supplier CSVs and emit bounded, reproducible per-file quality summaries."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from backend.import_real_ais_pilot import EXPECTED_HEADER


def audit(path: Path) -> dict:
    day = date.fromisoformat(path.stem)
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 * 1024 * 1024):
            digest.update(block)
    counts = Counter()
    nulls = Counter()
    first = last = None
    with path.open("r", encoding="gb18030", errors="strict", newline="") as source:
        reader = csv.reader(source, strict=True)
        header = next(reader)
        if header != EXPECTED_HEADER:
            raise ValueError(f"{path.name}: header mismatch: {header!r}")
        for row in reader:
            counts["rows"] += 1
            if len(row) != len(header):
                counts["wrong_columns"] += 1
                continue
            for column, value in zip(header, row):
                if value == "":
                    nulls[column] += 1
            mmsi = row[3]
            if not (mmsi.isascii() and mmsi.isdigit() and len(mmsi) in (9, 10)):
                counts["bad_mmsi"] += 1
            if len(mmsi) == 10:
                counts["ten_digit_mmsi"] += 1
            try:
                lon, lat = float(row[21]), float(row[22])
                if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                    counts["bad_coordinates"] += 1
            except ValueError:
                counts["bad_coordinates"] += 1
            try:
                stamp = int(row[20])
                observed = datetime.fromtimestamp(stamp, timezone.utc)
                local_day = (observed + timedelta(hours=8)).date()
                if local_day != day:
                    counts["outside_day"] += 1
                received = datetime.strptime(row[19], "%Y-%m-%d %H:%M:%S")
                if abs((received - (observed + timedelta(hours=8)).replace(tzinfo=None)).total_seconds()) > 1:
                    counts["time_mismatch"] += 1
                first = stamp if first is None else min(first, stamp)
                last = stamp if last is None else max(last, stamp)
            except (ValueError, OverflowError):
                counts["bad_time"] += 1
    return {"file": str(path), "bytes": size, "sha256": digest.hexdigest(),
            "header_columns": len(header), "encoding": "gb18030 strict",
            "counts": dict(counts), "nulls": dict(nulls),
            "first_utc": datetime.fromtimestamp(first, timezone.utc).isoformat() if first is not None else None,
            "last_utc": datetime.fromtimestamp(last, timezone.utc).isoformat() if last is not None else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", nargs="+", type=Path)
    args = parser.parse_args()
    for csv_path in args.csv:
        print(json.dumps(audit(csv_path), ensure_ascii=False), flush=True)
