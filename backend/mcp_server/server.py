"""Official SDK protocol plumbing, shared by stdio and local HTTP."""
from contextlib import asynccontextmanager
import hashlib
import hmac
import ipaddress
import json
import secrets

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.responses import JSONResponse

from backend.mcp_server.adapter import ADAPTER_VERSION, Adapter, failure
from backend.mcp_server.schemas import TOOLS, output_schema

MAX_RESULT_BYTES = 2 * 1024 * 1024


def create_server(adapter: Adapter, *, http=False):
    stdio_scope = "stdio:" + secrets.token_hex(32)

    @asynccontextmanager
    async def lifespan(server):
        try:
            yield {}
        finally:
            adapter.close()

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[types.Tool(
            name=name, description=TOOLS[name][1], inputSchema=TOOLS[name][0].model_json_schema(),
            annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                idempotentHint=name not in {"check_sql", "execute_sql"}, openWorldHint=False),
            outputSchema=output_schema(name),
        ) for name in adapter.names()])

    async def call_tool(ctx, params):
        scope = stdio_scope
        if http:
            request = ctx.request
            scope = request.scope.get("state", {}).get("mcp_principal") if request is not None else None
        if not scope:
            result = failure("UNAUTHENTICATED", "Client identity is required", "refused")
        else:
            result = await adapter.call(params.name, params.arguments or {}, scope)
        # Some clients truncate tool text before passing it to their model. Put
        # facts and uncertainty before verbose area/algorithm metadata and rows;
        # preserve every field and value in both protocol representations.
        versions = {}
        for field in ("area", "algorithm"):
            metadata = result.get(field)
            if isinstance(metadata, dict) and "version" in metadata:
                versions[field] = metadata["version"]
        if versions:
            result = {**result, "versions": versions}
        leading = ("request_id", "tool_name", "adapter_version", "status", "code", "message",
                   "versions", "summary", "statistics", "quality", "data_quality", "warnings", "limitations")
        result = {key: result[key] for key in leading if key in result} | result
        try:
            serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            result = failure("INVALID_RESULT", "Tool produced an invalid JSON result")
            serialized = json.dumps(result)
        if len(serialized.encode()) > MAX_RESULT_BYTES:
            result = {k: result[k] for k in ("request_id", "tool_name", "adapter_version") if k in result} | failure(
                "RESULT_TOO_LARGE", "Result exceeds transport budget; narrow the query, no data was truncated", "refused")
            serialized = json.dumps(result)
        return types.CallToolResult(content=[types.TextContent(type="text", text=serialized)],
            structuredContent=result, isError=result.get("status") not in
            {"ok", "partial", "no_data", "no_match", "not_found"})

    return Server("hormuz-readonly", version=ADAPTER_VERSION, lifespan=lifespan,
                  instructions="Historical AIS only. Preserve uncertainty and coverage. No UI map control, writes or causal inference.",
                  on_list_tools=list_tools, on_call_tool=call_tool,
                  get_tool_input_schema=lambda name: TOOLS[name][0].model_json_schema() if name in adapter.names() else None)


class LocalAuth:
    """Static per-client local bearer credentials; not a public OAuth deployment."""
    def __init__(self, app, tokens):
        if not isinstance(tokens, dict) or not tokens or len(tokens) > 64:
            raise ValueError("Configure 1..64 local HTTP client tokens")
        values = list(tokens.values())
        if any(not isinstance(v, str) or len(v) < 32 or len(v) > 256 for v in values):
            raise ValueError("Each client token must have 32..256 characters")
        if len(set(values)) != len(values):
            raise ValueError("Each HTTP client requires a distinct token")
        self.app = app
        self.tokens = [(hashlib.sha256(v.encode()).digest(), hashlib.sha256(v.encode()).hexdigest()) for v in values]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        try:
            local = client is not None and ipaddress.ip_address(client[0]).is_loopback
        except ValueError:
            local = False
        if not local:
            await JSONResponse({"error": "local_clients_only"}, status_code=403)(scope, receive, send)
            return
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"")
        token = authorization[7:] if authorization.startswith(b"Bearer ") else b""
        digest = hashlib.sha256(token).digest()
        principal = next((p for expected, p in self.tokens if hmac.compare_digest(expected, digest)), None)
        if principal is None:
            await JSONResponse({"error": "unauthorized"}, status_code=401,
                               headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
            return
        scope.setdefault("state", {})["mcp_principal"] = "http:" + principal
        await self.app(scope, receive, send)


def create_http_app(adapter, tokens):
    server = create_server(adapter, http=True)
    app = server.streamable_http_app(stateless_http=True, json_response=True,
        max_request_body_size=128 * 1024,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]))
    return LocalAuth(app, tokens)
