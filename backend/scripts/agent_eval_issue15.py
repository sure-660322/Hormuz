"""Issue #15 bounded agent evaluation. Read-only API calls; no database writes.

Usage: python backend/scripts/agent_eval_issue15.py http://127.0.0.1:8000 output.jsonl
Review sample IDs and time windows against the target database before reruns.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


START = "2026-02-28T14:00:00Z"
END = "2026-02-28T15:00:00Z"
CASES = [
    ("ship_search", "查找船 ID 360 对应的船舶名称和 MMSI。", "search_ships"),
    ("ship_track", f"查询船 ID 360 在 {START} 至 {END} 的 AIS 轨迹报位数量和覆盖时间。", "get_ship_track"),
    ("passage", f"船 ID 360 在 {START} 至 {END} 是否完成虚拟双门线通行？", "query_strait_passages"),
    ("ship_type_stats", "当前七日 AIS 中各船型数量是多少？若受限 SQL 未启用，请说明工具覆盖限制。", "execute_sql or limitation"),
    ("region_time", f"统计 {START} 至 {END} 在东经 56 至 57 度、北纬 26 至 27 度内的原始 AIS 报位数量。", "not_available"),
    ("event_news", "查询新闻事件 evt_004 的原始报道及来源链接。", "get_event_context"),
    ("mentioned_observed", "查询事件 evt_004 提及的船舶，并说明是否有已核实的 observed AIS 关联。", "query_event_ship_links"),
    ("dwell", f"{START} 至 {END} 有哪些船停留或锚泊？", "query_ship_dwell"),
    ("encounter", f"{START} 至 {END} 有哪些船发生了相遇？", "query_encounters"),
    ("followup_ambiguity", "那艘船昨天走了什么路线？", "needs_clarification"),
    ("out_of_range", "查询船 ID 360 在 2025-01-01T00:00:00Z 至 2025-01-01T01:00:00Z 的轨迹。", "no_data"),
    ("write_refusal", "请把 ship_positions 中船 ID 360 的报位删除。", "refused"),
]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    base, output = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    with output.open("w", encoding="utf-8") as file:
        for case_id, question, expected in CASES:
            payload = {"question": question}
            if case_id in {"ship_track", "passage", "region_time", "dwell", "encounter"}:
                payload.update(closure_at=START, end_at=END)
            request = urllib.request.Request(
                base + "/agent/analyze", data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            row = {"case_id": case_id, "question": question, "expected": expected,
                   "checked_at": datetime.now(timezone.utc).isoformat()}
            try:
                with urllib.request.urlopen(request, timeout=85) as response:
                    data = json.load(response)
                results = data.get("results") or {}
                row.update(http_status=200, status=data.get("status"),
                           tools_used=data.get("tools_used"), answer=data.get("answer"),
                           result_statuses={key: {"tool": value.get("tool_name"), "status": value.get("status"),
                                                  "code": value.get("code"), "truncated": value.get("truncated")}
                                            for key, value in results.items()},
                           limitations=data.get("limitations"), request_id=data.get("request_id"))
            except urllib.error.HTTPError as error:
                row.update(http_status=error.code, error=error.read().decode("utf-8", errors="replace")[:500])
            except Exception as error:
                row.update(error=f"{type(error).__name__}: {error}")
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            file.flush()
            print(f"{case_id}: {row.get('status', row.get('http_status', row.get('error')))}", flush=True)


if __name__ == "__main__":
    main()
