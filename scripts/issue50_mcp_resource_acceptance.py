"""Local diagnostic MCP child for real cancellation/concurrency verification.

Never installed in DSH or production. Only fixed read-only pg_sleep probes,
using the existing business credential in the backend child. No arbitrary SQL
input, database changes, or shared-process control.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def server(events):
    from sqlalchemy import text
    from backend.mcp_server.__main__ import configured_adapter, stdio
    adapter = configured_adapter()
    original = adapter.dispatch
    lock = threading.Lock()

    def record(value):
        with lock, events.open("a", encoding="utf8") as stream:
            stream.write(json.dumps(value) + "\n")

    def dispatch(name, args, scope, request_id, cancel):
        keyword = args.get("keyword", "")
        if name != "search_ships" or not keyword.startswith("__resource_probe__"):
            return original(name, args, scope, request_id, cancel)
        started = time.monotonic()
        pid = None
        state = None
        try:
            with adapter.session(cancel) as db:
                pid = db.execute(text("SELECT pg_backend_pid()" )).scalar_one()
                record({"event": "started", "request_id": request_id, "probe": keyword})
                db.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": 3})
            return {"status": "ok", "matches": [], "returned_count": 0}
        except Exception as exc:
            state = getattr(getattr(exc, "orig", None), "sqlstate", None)
            raise
        finally:
            # Check only this diagnostic backend PID after its transaction ends.
            with adapter.engine.connect() as connection:
                active = connection.execute(text(
                    "SELECT count(*) FROM pg_stat_activity WHERE pid=:pid "
                    "AND state='active' AND query LIKE :pattern"),
                    {"pid": pid, "pattern": "%pg_sleep%"}).scalar_one()
            record({"event": "finished", "request_id": request_id, "probe": keyword,
                    "cancel_event": cancel.event.is_set(), "sqlstate": state,
                    "active_probe_queries": active, "elapsed_seconds": round(time.monotonic()-started, 3)})

    adapter.dispatch = dispatch
    asyncio.run(stdio(adapter))


async def client(runtime, events):
    root = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DB_", "MCP_", "AGENT_DB_", "AGENT_QUERY_"))}
    for key, field in [("USER", "user"), ("PASSWORD_CREDENTIAL", "credential"),
                       ("HOST", "host"), ("PORT", "port"), ("NAME", "name")]:
        env[f"MCP_DB_{key}"] = runtime["database"][field]
    params = StdioServerParameters(command=runtime["python"], args=[str(Path(__file__).resolve()),
        "--server", "--events", str(events.resolve())], env=env, cwd=str(root))

    def records():
        return [json.loads(line) for line in events.read_text(encoding="utf8").splitlines()] if events.exists() else []

    async def until(predicate):
        for _ in range(150):
            if predicate(records()):
                return
            await asyncio.sleep(.02)
        raise AssertionError("Diagnostic probe did not reach expected lifecycle state")

    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            task = asyncio.create_task(session.call_tool("search_ships", {"keyword": "__resource_probe__cancel"}))
            await until(lambda rs: any(r["event"] == "started" for r in rs))
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await until(lambda rs: any(r["event"] == "finished" for r in rs))
            done = records()[-1]
            assert done["cancel_event"] and done["sqlstate"] == "57014"
            assert done["active_probe_queries"] == 0 and done["elapsed_seconds"] < 2
            tasks = [asyncio.create_task(session.call_tool("search_ships",
                     {"keyword": f"__resource_probe__concurrency{i}"})) for i in range(4)]
            await until(lambda rs: sum(r["event"] == "started" and "concurrency" in r["probe"] for r in rs) == 4)
            busy = await session.call_tool("search_ships", {"keyword": "__resource_probe__excess"})
            assert busy.structured_content["code"] == "MCP_BUSY"
            results = await asyncio.gather(*tasks)
            assert all(r.structured_content["status"] == "ok" for r in results)
    assert all(r["active_probe_queries"] == 0 for r in records() if r["event"] == "finished")
    return {"date": "2026-10-11", "transport": "stdio", "diagnostic_only": True,
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
            "cancel": "PASS: SDK cancellation -> Adapter event -> psycopg 57014; no active probe query",
            "concurrency": "PASS: four real read-only probes; fifth refused MCP_BUSY; slots released",
            "events": records(), "busy": busy.structured_content,
            "scope": "Dedicated diagnostic child with fixed SQL; not a normal business query or sustained load/TCP disconnect test"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.server:
        server(args.events)
        return
    if args.events.exists():
        raise ValueError("Preserve existing diagnostic evidence; choose a new events path")
    runtime = json.loads(args.runtime.read_text(encoding="utf-8-sig"))
    result = asyncio.run(client(runtime, args.events))
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf8")
    print("Real stdio cancellation and bounded concurrency PASS")


if __name__ == "__main__":
    main()
