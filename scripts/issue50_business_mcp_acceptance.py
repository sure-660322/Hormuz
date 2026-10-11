"""Independent SDK stdio client; credentials resolved only by the MCP child.

Runtime JSON contains only python/workspace/database metadata. Does not change
DSH profiles, database objects, or source data. Evidence excludes secrets.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

EXPECTED = ["search_ships", "get_ship_track", "query_strait_passage_statistics",
            "compare_strait_passage_statistics", "query_area_ship_snapshot",
            "query_area_ship_activity", "compare_area_ship_activity"]
WINDOW = {"start_at": "2026-02-26T00:00:00Z", "end_at": "2026-02-27T00:00:00Z"}
PERIODS = {"start_a": WINDOW["start_at"], "end_a": WINDOW["end_at"],
           "start_b": "2026-02-27T00:00:00Z", "end_b": "2026-02-28T00:00:00Z"}
SAMPLES = [
    ("search_ships", {"keyword": "ATHE NOVA", "limit": 10}),
    ("get_ship_track", {"ship_id": 628, **WINDOW}),
    ("query_strait_passage_statistics", {**WINDOW, "direction": "all"}),
    ("compare_strait_passage_statistics", {**PERIODS, "direction": "all"}),
    ("query_area_ship_snapshot", {"at": "2026-02-26T12:00:00Z"}),
    ("query_area_ship_activity", WINDOW),
    ("compare_area_ship_activity", PERIODS),
    ("search_ships", {"keyword": "HORMUZ_NO_SUCH_SHIP_50_20261011"}),
    ("search_ships", {"keyword": "ATHE NOVA", "limit": True}),
]


async def collect(runtime, root):
    db = runtime["database"]
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("DB_", "MCP_", "AGENT_DB_", "AGENT_QUERY_"))}
    for key, field in [("USER", "user"), ("PASSWORD_CREDENTIAL", "credential"),
                       ("HOST", "host"), ("PORT", "port"), ("NAME", "name")]:
        env[f"MCP_DB_{key}"] = db[field]
    evidence = {"date": "2026-10-11", "client": f"Python MCP SDK {importlib.metadata.version('mcp')}",
                "transport": "stdio", "database": {k: db[k] for k in ("host", "port", "name")},
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in (root / "backend/mcp_server").glob("*.py")}, "runs": []}
    for flag in ("false", "true"):
        env.update(MCP_SQL_ENABLED=flag, AGENT_QUERY_ENABLED="true",
                   AGENT_DB_PASSWORD_CREDENTIAL="unused-sql-sentinel-not-read")
        params = StdioServerParameters(command=runtime["python"],
            args=["-m", "backend.mcp_server", "--transport", "stdio"], env=env, cwd=str(root))
        run = {"legacy_sql_flag": flag, "records": []}
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                init = await session.initialize()
                run["server_version"] = init.server_info.version
                run["tools"] = [t.name for t in (await session.list_tools()).tools]
                assert run["tools"] == EXPECTED
                for name in ("get_database_schema", "check_sql", "execute_sql"):
                    response = await session.call_tool(name, {"sql": "DELETE FROM ships"})
                    result = response.structured_content
                    assert response.is_error and result["code"] == "TOOL_UNAVAILABLE"
                    run["records"].append({"tool": name, "input": {"sql": "DELETE FROM ships"}, "result": result})
                if flag == "true":
                    for name, args in SAMPLES:
                        response = await session.call_tool(name, args)
                        result = response.structured_content
                        # Keep summaries, windows, versions and quality; omit large position/visit detail lists.
                        fields = ("request_id", "status", "code", "adapter_version", "summary", "statistics",
                                  "quality", "coverage", "data_quality", "limitations", "versions", "window",
                                  "determination_version", "metrics", "a", "b", "matches", "matched_count",
                                  "returned_count", "fix_count", "truncated", "source")
                        compact = {k: result[k] for k in fields if k in result}
                        for side in ("a", "b"):
                            if isinstance(compact.get(side), dict):
                                compact[side] = {k: v for k, v in compact[side].items()
                                                 if k not in ("visits", "ships", "fixes", "daily")}
                        run["records"].append({"tool": name, "input": args, "result": compact})
                        if args.get("limit") is True:
                            assert result["code"] == "INVALID_TOOL_ARGS"
                        elif args.get("keyword", "").startswith("HORMUZ_NO_SUCH"):
                            assert result["status"] == "no_match" and result["matched_count"] == 0
                        else:
                            assert result["status"] in {"ok", "partial", "no_data", "not_found"}
        evidence["runs"].append(run)
    records = evidence["runs"][1]["records"]
    by_tool = {r["tool"]: r["result"] for r in records[:10]}
    ship = by_tool["search_ships"]["matches"][0]
    assert str(ship["mmsi"]) == "334931000" and str(ship["imo"]) == "9188116"
    passage = by_tool["query_strait_passage_statistics"]["window"]
    assert passage["passage_count"] == 132 and passage["unique_ship_count"] == 131
    assert by_tool["query_area_ship_snapshot"]["summary"]["in_area_count"] == 199
    area = by_tool["query_area_ship_activity"]["summary"]
    assert area["ships_observed"] == 477 and area["observed_ship_hours"] == 4719.027
    evidence["baseline_comparison"] = {
        "reference": "docs/dsh_mcp_acceptance.json (2026-10-10 historical business baseline)",
        "result": "PASS: identity, passage counts, snapshot count and activity summary",
        "scope": "Same test database and parameters; baseline not recomputed this batch. Comparisons and empty track are new protocol observations."}
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = json.loads(args.runtime.read_text(encoding="utf-8-sig"))
    root = Path(__file__).resolve().parents[1]
    result = asyncio.run(collect(runtime, root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("Independent protocol evidence saved; inspect statuses before claiming acceptance.")


if __name__ == "__main__":
    main()
