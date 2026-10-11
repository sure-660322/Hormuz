"""python -m backend.mcp_server --transport stdio|streamable-http"""
import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import suppress

from backend.mcp_server.adapter import Adapter, business_engine_from_env
from backend.mcp_server.server import create_server, create_http_app
from backend.mcp_server.credentials import resolve_passwords


def configured_adapter():
    adapter = Adapter()
    try:
        # External MCP never resolves internal SQL credentials.
        resolve_passwords()
        # Validate explicit target before starting; constructing an engine does not connect.
        adapter.engine = business_engine_from_env()
        return adapter
    except Exception:
        adapter.close()
        raise


async def stdio(adapter):
    from mcp.server.stdio import stdio_server
    server = create_server(adapter)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main():
    parser = argparse.ArgumentParser(description="Hormuz local read-only MCP")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8036)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    logging.getLogger("hormuz.mcp.audit").setLevel(logging.INFO)
    adapter = None
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Invalid local port")
        adapter = configured_adapter()
        if args.transport == "stdio":
            asyncio.run(stdio(adapter))
        else:
            import uvicorn
            tokens = json.loads(os.environ.get("MCP_HTTP_TOKENS", "{}"))
            app = create_http_app(adapter, tokens)
            # No host override or proxy headers: this entry point is local-only.
            uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False, access_log=False)
    except Exception:
        print("MCP startup failed; check explicit business database/HTTP token configuration and local port.", file=sys.stderr)
        return 1
    finally:
        if adapter is not None:
            with suppress(Exception):
                adapter.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
