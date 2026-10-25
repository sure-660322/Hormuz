"""Strict case-export audit; preserves the Arctic default and never changes sources."""
import csv
import hashlib
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CASE_PREFIX = "case/arctic-ocean/"


def audit_csv(path: Path, *, mmsi="477967700", imo="9695169", name=None,
              supplier="船讯网（用户确认）", quarantine_invalid_navigation=False) -> dict:
    points, repairs, conflicts = [], [], []
    rejected, raw_rows = [], 0
    invalid_epochs = set()
    seen = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream)
        header = next(rows)
        expected = ["船名", "呼号", "IMO", "MMSI", "船舶类型", "航行状态", "船长", "船宽", "吃水", "船首向", "船迹向", "航速", "Lon", "Lat", "旋转角速度", "目的地", "ETA", "最后更新时间", "时间戳", "Lon_d", "Lat_d", "数据来源"]
        if [s.strip() for s in header] != expected:
            raise ValueError("CSV header does not match the ShipXY case format")
        for number, row in enumerate(rows, 2):
            raw_rows += 1
            if len(row) > 22:
                # Only destination may contain unquoted commas; validate all tail fields below.
                row = row[:15] + [",".join(row[15:-6])] + row[-6:]
                repairs.append(number)
            if len(row) != 22 or row[2:4] != [imo, mmsi] or (name and row[0] != name):
                raise ValueError(f"Invalid width or vessel identity at line {number}")
            epoch = int(row[18])
            recorded = datetime.fromtimestamp(epoch, timezone.utc)
            local = datetime.fromisoformat(row[17])
            if (local - recorded.replace(tzinfo=None)).total_seconds() != 28800:
                raise ValueError(f"Inconsistent time fields at line {number}")
            lon, lat, speed, course = map(float, (row[19], row[20], row[11], row[10]))
            if not all(math.isfinite(v) for v in (lon, lat, speed, course)) or not (-180 <= lon <= 180 and -90 <= lat <= 90 and 0 <= speed <= 102.2 and 0 <= course <= 360):
                if quarantine_invalid_navigation:
                    conflicts.append(number)
                    invalid_epochs.add(epoch)
                    rejected.append(dict(source_row=number, reason="Invalid coordinate or navigation value"))
                    continue
                raise ValueError(f"Invalid coordinate or navigation value at line {number}")
            heading, rot, draught = (float(row[9]) if row[9] else None), float(row[14]), float(row[8])
            if (heading is not None and (not math.isfinite(heading) or not (0 <= heading <= 359 or heading == 511))) or not math.isfinite(rot) or not math.isfinite(draught) or draught < 0:
                raise ValueError(f"Invalid heading, ROT or draught at line {number}")
            p = dict(source_row=number, unix_time=epoch, recorded_at=recorded.isoformat(),
                     longitude=lon, latitude=lat, speed=speed, course=course,
                     heading=heading if heading is not None and heading < 360 else None,
                     nav_status=row[5], rot=rot, draught_m=draught,
                     destination=row[15], eta_text=row[16], ais_type=row[21])
            if epoch in seen:
                # Quarantine every member of a conflicting second, not an arbitrary winner.
                conflicts.append(number)
                conflicts.append(seen[epoch]["source_row"])
            else:
                seen[epoch] = p
            points.append(p)
    quarantine = set(conflicts)
    quarantine.update(p["source_row"] for p in points if p["unix_time"] in invalid_epochs)
    accepted = sorted((p for p in points if p["source_row"] not in quarantine), key=lambda p: p["unix_time"])
    if not accepted:
        raise ValueError("No accepted positions")
    gaps = [dict(from_at=a["recorded_at"], to_at=b["recorded_at"], seconds=b["unix_time"]-a["unix_time"])
            for a, b in zip(accepted, accepted[1:]) if b["unix_time"]-a["unix_time"] > 5400]
    return dict(source_file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                supplier=supplier, data_source="nnu_ais", raw_rows=raw_rows,
                accepted_rows=len(accepted), repaired_rows=repairs, quarantined_rows=sorted(quarantine),
                rejected_rows=rejected,
                start_at=accepted[0]["recorded_at"], end_at=accepted[-1]["recorded_at"], gaps=gaps,
                daily_utc=dict(Counter(p["recorded_at"][:10] for p in accepted)), positions=accepted)
