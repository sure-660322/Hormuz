"""Local-only HTTP fixture for SQL-06 browser acceptance.

This server contains no credentials and never connects to a database. Backend,
policy, PostgreSQL, and real-model behavior are verified separately by
verify_query_analytics_sql06.ps1; this fixture isolates the Vue rendering and
interaction contract.
"""

from __future__ import annotations

import json
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


START = "2026-09-20T00:00:00Z"
END = "2026-09-20T00:10:00Z"


def _context():
    return {
        "schema_version": "4",
        "batch": "SQL-06 browser fixed fixture",
        "ship_data_source": "simulation",
        "closure_at": START,
        "end_at": END,
        "closure_source": "SQL-06 fixed fixture",
        "passage_rule": "SQL-06 browser fixture; backend rules are verified separately",
    }


def _agent_response(question: str):
    base = {
        "schema_version": "4",
        "request_id": "req_sql06_browser",
        "context": _context(),
        "ships": [],
        "evidence": [],
        "query_summary": None,
        "limitations": ["浏览器固定 fixture，不代表共享数据库快照"],
        "clarification": None,
    }
    if "删除" in question:
        return {
            **base,
            "status": "refused",
            "answer": "该请求涉及写库操作，智能体只允许只读查询，因此已拒绝。",
            "tools_used": [],
            "results": {},
        }
    if question.strip() == "查一下":
        clarification = "请说明要查询的对象、指标或时间范围。"
        return {
            **base,
            "status": "needs_clarification",
            "answer": clarification,
            "clarification": clarification,
            "tools_used": [],
            "results": {},
        }
    return {
        **base,
        "status": "ok",
        "answer": "固定 fixture 中 shipping 类事件为 1 条。",
        "tools_used": ["query_analytics"],
        "results": {
            "call_001": {
                "call_id": "call_001",
                "tool_name": "query_analytics",
                "query_id": "aq_sql06_browser",
                "status": "ok",
                "columns": ["event_type", "event_count"],
                "rows": [["shipping", 1]],
                "returned_row_count": 1,
                "truncated": False,
                "source": {
                    "catalog_version": "1.0",
                    "views": ["agent_data.v_events"],
                    "data_scope": {"agent_data.v_events": "browser fixture"},
                },
                "limitations": ["事件分类是报道聚合标签"],
            }
        },
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self):
        self._send({})

    def do_GET(self):
        path = urlparse(self.path).path
        payloads = {
            "/health": {"status": "ok"},
            "/events": [],
            "/simulation/meta": {
                "start_at": START, "end_at": END, "frame_interval_seconds": 600,
                "frame_count": 2, "ship_count": 1, "position_count": 1,
                "event_count": 0, "is_simulated": True,
            },
            "/ships/map": [{
                "id": 1, "mmsi": "900000001", "name": "SIM SQL06",
                "ship_type": "cargo", "flag": "TEST", "imo": None, "callsign": None,
                "latitude": 26.5, "longitude": 56.5, "speed": 12.0, "course": 90.0,
                "heading": 90.0, "recorded_at": START,
            }],
            "/ships/playback": [{
                "id": 1, "ship_id": 1, "latitude": 26.5, "longitude": 56.5,
                "speed": 12.0, "course": 90.0, "heading": 90.0, "recorded_at": START,
            }],
            "/api/encounters": {
                "status": "ok", "encounters": [], "count": 0, "truncated": False,
                "params": None, "built_at": None, "stale": None, "limitations": [],
            },
            "/api/data-health": {
                "status": "ok", "batch": "SQL-06 browser fixed fixture",
                "source": {"by_data_source": [], "totals": {"ships": 1, "events": 0, "news": 0, "positions": 1}},
                "derived": [], "note": "browser fixture",
            },
        }
        if path in payloads:
            self._send(payloads[path])
        else:
            self._send({"detail": "not found"}, 404)

    def do_POST(self):
        if urlparse(self.path).path != "/agent/analyze":
            self._send({"detail": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self._send(_agent_response(str(body.get("question", ""))))

    def log_message(self, format, *args):
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
