"""Protocol development smoke tests, not #50 independent-client business acceptance."""
import asyncio
import json
import os
from pathlib import Path
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import pytest
from starlette.testclient import TestClient

from backend.mcp_server.adapter import Adapter
from backend.mcp_server.server import create_http_app

TOKEN_A, TOKEN_B = "a" * 40, "b" * 40
HEADERS = {"Authorization": f"Bearer {TOKEN_A}", "Accept": "application/json, text/event-stream",
           "MCP-Protocol-Version": "2026-07-28"}


def rpc(method, params=None, request_id=1):
    params = params or {}
    return {"jsonrpc": "2.0", "id": request_id, "method": method,
            "params": params | {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {}}}}


def post(session, headers, body):
    headers = headers | {"MCP-Method": body["method"]}
    if body["method"] == "tools/call":
        headers["MCP-Name"] = body["params"]["name"]
    return session.post("/mcp", headers=headers, json=body)


@pytest.fixture
def client():
    instance = Adapter(sql_enabled=True, executor_factory=lambda: None)
    app = create_http_app(instance, {"client-a": TOKEN_A, "client-b": TOKEN_B})
    with TestClient(app, base_url="http://127.0.0.1:8036", client=("127.0.0.1", 50100)) as session:
        yield session, instance


def test_http_modern_discovery_schema_and_check(client):
    session, _ = client
    response = post(session, HEADERS, rpc("tools/list"))
    assert response.status_code == 200, response.text
    tools = response.json()["result"]["tools"]
    assert len(tools) == 10
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    assert next(t for t in tools if t["name"] == "get_ship_track")["inputSchema"]["required"] == ["start_at", "end_at", "ship_id"]
    result = post(session, HEADERS, rpc("tools/call", {
        "name": "check_sql", "arguments": {"sql": "SELECT ship_id FROM agent_data.v_ships"}}))
    assert result.status_code == 200, result.text
    assert result.json()["result"]["structuredContent"]["validation_token"]


def test_http_trusted_identity_is_present_and_foreign_token_rejected(client):
    session, _ = client
    args = {"sql": "SELECT ship_id FROM agent_data.v_ships"}
    result = post(session, HEADERS, rpc("tools/call", {"name": "check_sql", "arguments": args})).json()
    token = result["result"]["structuredContent"]["validation_token"]
    foreign = HEADERS | {"Authorization": f"Bearer {TOKEN_B}"}
    result = post(session, foreign, rpc("tools/call", {
        "name": "execute_sql", "arguments": args | {"validation_token": token}})).json()
    assert result["result"]["structuredContent"]["code"] == "INVALID_SQL_TOKEN"


def test_http_legacy_initialize_and_list(client):
    session, _ = client
    headers = HEADERS | {"MCP-Protocol-Version": "2025-11-25"}
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "dev-test", "version": "1"}}}
    response = session.post("/mcp", headers=headers, json=initialize)
    assert response.status_code == 200, response.text
    assert response.json()["result"]["protocolVersion"] == "2025-11-25"
    response = session.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert response.status_code == 200, response.text
    assert len(response.json()["result"]["tools"]) == 10


@pytest.mark.parametrize("headers,status", [
    ({"Accept": "application/json, text/event-stream"}, 401),
    (HEADERS | {"Authorization": "Bearer wrong"}, 401),
    (HEADERS | {"Host": "attacker.example:8036"}, 421),
    (HEADERS | {"Origin": "https://attacker.example"}, 403),
])
def test_http_auth_host_origin(client, headers, status):
    response = client[0].post("/mcp", headers=headers, json=rpc("tools/list"))
    assert response.status_code == status, response.text


def test_remote_client_rejected():
    instance = Adapter()
    with TestClient(create_http_app(instance, {"a": TOKEN_A}), base_url="http://localhost:8036",
                    client=("192.0.2.1", 1000)) as session:
        assert session.post("/mcp", headers=HEADERS, json=rpc("tools/list")).status_code == 403


def test_http_oversize_request_rejected(client):
    response = client[0].post("/mcp", headers=HEADERS, json=rpc("tools/call", {
        "name": "search_ships", "arguments": {"keyword": "x" * (129 * 1024)}}))
    assert response.status_code == 413


@pytest.mark.parametrize("payload,code", [
    ({"status": "ok", "fixes": ["x" * (2 * 1024 * 1024)]}, "RESULT_TOO_LARGE"),
    ({"status": "ok", "speed": float("nan")}, "INVALID_RESULT"),
])
def test_invalid_or_oversized_output_is_refused_whole(client, payload, code):
    session, instance = client
    instance.dispatch = lambda *a: payload
    result = post(session, HEADERS, rpc("tools/call", {"name": "search_ships", "arguments": {"keyword": "x"}})).json()
    assert result["result"]["isError"]
    assert result["result"]["structuredContent"]["code"] == code
    assert "fixes" not in result["result"]["structuredContent"]


def test_client_truncation_keeps_summary_and_uncertainty_visible(client):
    session, instance = client
    payload = {"status": "partial", "area": {"version": "1.0.0", "basis": "x" * 10000},
               "algorithm": {"version": "1.0.1", "params": {"description": "y" * 10000}},
               "summary": {"ships_observed": 477},
               "quality": {"limitations": ["Coverage is incomplete"]}}
    instance.dispatch = lambda *a: payload
    result = post(session, HEADERS, rpc("tools/call", {
        "name": "query_area_ship_activity", "arguments": {
            "start_at": "2026-02-26T00:00:00Z", "end_at": "2026-02-27T00:00:00Z"}})).json()["result"]
    text_prefix = result["content"][0]["text"][:2000]
    assert '"ships_observed": 477' in text_prefix
    assert "Coverage is incomplete" in text_prefix
    assert '"algorithm": "1.0.1"' in text_prefix
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    assert result["structuredContent"]["area"] == payload["area"]


def test_stdio_subprocess_discovery_and_offline_sql():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DB_", "MCP_", "AGENT_DB_"))}
    env.update({"MCP_SQL_ENABLED": "true", "AGENT_QUERY_ENABLED": "true",
                "AGENT_QUERY_BIND_HOST": "127.0.0.1"})
    for prefix in ("MCP_DB", "AGENT_DB"):
        env.update({f"{prefix}_USER": "agent_reader_login", f"{prefix}_PASSWORD": "placeholder-not-a-secret",
                    f"{prefix}_HOST": "127.0.0.1", f"{prefix}_PORT": "1", f"{prefix}_NAME": "nonexistent_test"})
    params = StdioServerParameters(command=sys.executable, args=["-m", "backend.mcp_server", "--transport", "stdio"],
                                 env=env, cwd=str(Path(__file__).resolve().parents[2]))
    async def run():
        async with stdio_client(params) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                result = await session.list_tools()
                assert len(result.tools) == 10
                check = await session.call_tool("check_sql", {"sql": "SELECT ship_id FROM agent_data.v_ships"})
                assert not check.is_error
                assert check.structured_content["validation_token"]
                denied = await session.call_tool("check_sql", {"sql": "DELETE FROM ships"})
                assert denied.is_error
    asyncio.run(run())
