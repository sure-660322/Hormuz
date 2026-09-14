"""Read-only export of the news/events rows that the scenario refers to.

Writes reference/news_snapshot.json so that data generation does not depend on a
live database connection at generation time. This script performs SELECT statements
only. It never prints or stores credentials.

If the database is unreachable, the already-committed snapshot file is kept as-is
and the generation step continues; the acceptance report then flags that the news
basis was not re-verified against the live database in this run.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))

REFERENCED_EVENT_IDS = [
    # P0 - pre-incident
    "evt_001", "evt_002", "evt_003", "evt_004", "evt_005",
    # P1 - onset
    "evt_006", "evt_008", "evt_009", "evt_011", "evt_014",
    # P2 - peak
    "evt_007", "evt_015", "evt_016", "evt_017", "evt_020", "evt_021", "evt_024",
    "evt_027", "evt_028", "evt_029", "evt_031", "evt_033", "evt_037", "evt_040",
    "evt_044", "evt_045", "evt_047", "evt_049", "evt_052", "evt_055", "evt_056",
    "evt_058", "evt_065",
    # P3 - reported anchors only
    "evt_039", "evt_059",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="只读导出新闻事件快照")
    parser.add_argument("--out", default=str(ROOT / "reference" / "news_snapshot.json"))
    args = parser.parse_args()

    out_path = Path(args.out)
    snapshot = {
        "exported_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "PostgreSQL aisdb: public.events JOIN public.news",
        "access": "read-only",
        "database_available": False,
        "notes_zh": [
            "news.event_id 是指向 events.id 的数值外键；events.event_id 是业务字符串编号（evt_xxx），两者不可混用。",
            "publish_date 是报道日期，不等于事件发生时间。",
            "event_datetime 可为空，空值表示报道未给出可核实的发生时刻，本快照不回填。",
            "events.event_lat/lng 是区域代表点或地理编码结果，不是核实的精确事发坐标。",
            "mentioned_vessels 只是报道中提到的船名，不代表本批次模拟船与真实船舶存在任何关联。",
        ],
        "events": [],
    }

    try:
        from sqlalchemy import text
        from backend.app.database import SessionLocal

        with SessionLocal() as session:
            rows = session.execute(
                text(
                    """
                    SELECT id, event_id, event_key, title_zh, summary_zh, event_type,
                           event_datetime, event_time_text, event_location_text,
                           event_region, event_lat, event_lng, mentioned_vessels,
                           geo_method, geo_note, coverage_count, perspectives,
                           story_ids, publish_date_min, publish_date_max
                    FROM events
                    WHERE event_id = ANY(:ids)
                    ORDER BY event_id
                    """
                ),
                {"ids": REFERENCED_EVENT_IDS},
            ).mappings().all()

            found = {r["event_id"] for r in rows}
            linked = session.execute(
                text(
                    """
                    SELECT n.event_id AS numeric_fk, e.event_id AS biz_event_id,
                           n.story_id, n.title_zh, n.title, n.publish_date,
                           n.media_name, n.perspective, n.language, n.canonical_url,
                           n.event_type, n.event_datetime, n.event_time_text,
                           n.event_location_text, n.event_region, n.event_lat, n.event_lng,
                           n.mentioned_vessels, n.relevant
                    FROM news n
                    LEFT JOIN events e ON e.id = n.event_id
                    WHERE e.event_id = ANY(:ids)
                    ORDER BY e.event_id, n.publish_date, n.story_id
                    """
                ),
                {"ids": REFERENCED_EVENT_IDS},
            ).mappings().all()

        news_by_event: dict[str, list] = {}
        for r in linked:
            item = dict(r)
            item.pop("numeric_fk", None)
            news_by_event.setdefault(item.pop("biz_event_id"), []).append(item)

        for r in rows:
            item = dict(r)
            item["linked_news"] = news_by_event.get(item["event_id"], [])
            snapshot["events"].append(item)

        snapshot["database_available"] = True
        snapshot["missing_referenced_event_ids"] = sorted(set(REFERENCED_EVENT_IDS) - found)
        snapshot["linked_news_total"] = len(linked)
    except Exception as exc:  # noqa: BLE001
        snapshot["error"] = f"{type(exc).__name__}: {exc}"
        if out_path.exists():
            print(f"数据库不可用，保留既有快照：{out_path}")
            print(f"原因：{type(exc).__name__}")
            return 0
        print(f"数据库不可用且没有既有快照：{type(exc).__name__}: {exc}")
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"已写出 {out_path}")
    print(f"事件：{len(snapshot['events'])}，关联报道：{snapshot['linked_news_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
