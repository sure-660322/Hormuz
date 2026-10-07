"""测量原 strait_passages 算法耗时基线（只读，issue #40 性能基线）。

用法：在仓库根目录、配置好 DB_* 环境变量后运行
python scripts/measure_strait_baseline.py
"""
import statistics
import time
from datetime import datetime, timedelta, timezone

from backend.app.database import SessionLocal
from backend.app.services.agent.strait_passages import query_strait_passages

# 七日批次的 UTC 覆盖（来自 simulation/meta 实际数据范围，以数据库为准）
CASES = [
    ("1日·全部船型", datetime(2026, 2, 26, tzinfo=timezone.utc), datetime(2026, 2, 27, tzinfo=timezone.utc)),
    ("1日·油轮(事后过滤)", datetime(2026, 2, 26, tzinfo=timezone.utc), datetime(2026, 2, 27, tzinfo=timezone.utc)),
    ("7日逐日·全部船型(7次调用)", None, None),
]

def run_one(db, start, end):
    t0 = time.perf_counter()
    result = query_strait_passages(db, start, end)
    elapsed = time.perf_counter() - t0
    return result, elapsed

def main():
    db = SessionLocal()
    try:
        # 冷/热各测一遍 1 日全船
        for label, start, end in CASES[:2]:
            times = []
            last = None
            for i in range(3 if label.startswith("1日·全部") else 2):
                last, elapsed = run_one(db, start, end)
                times.append(elapsed)
            qs = last.query_summary
            print(f"{label}: min={min(times):.2f}s median={statistics.median(times):.2f}s "
                  f"positions={qs.position_count} ships={qs.matched_ship_count} "
                  f"passages={qs.passage_count} uncertain={qs.uncertain_candidate_count} status={last.status}")
        # 多日：7 次逐日调用（原算法能力上限即 24h 单窗）
        total = 0.0
        counts = {"passages": 0, "uncertain": 0}
        per_day = []
        day = datetime(2026, 2, 25, tzinfo=timezone.utc)
        for i in range(7):
            result, elapsed = run_one(db, day, day + timedelta(days=1))
            total += elapsed
            counts["passages"] += result.query_summary.passage_count
            counts["uncertain"] += result.query_summary.uncertain_candidate_count
            per_day.append(f"{day:%m-%d}:{elapsed:.2f}s/{result.query_summary.passage_count}次")
            day += timedelta(days=1)
        print(f"7日逐日·全部船型: total={total:.2f}s passages={counts['passages']} uncertain={counts['uncertain']}")
        print("  " + " ".join(per_day))
    finally:
        db.close()

if __name__ == "__main__":
    main()
