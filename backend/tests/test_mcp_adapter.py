"""Development checks with fake services/executor: never connect to a real DB."""
import asyncio
from contextlib import contextmanager
import json
import threading

import pytest

from backend.mcp_server.adapter import Adapter, Cancellation

@pytest.fixture
def adapter():
    instance = Adapter()
    yield instance
    instance.close()


def call(adapter, name, args=None, scope="client-a"):
    return asyncio.run(adapter.call(name, args or {}, scope))


@pytest.mark.parametrize("name", ["get_database_schema", "check_sql", "execute_sql"])
def test_sql_denied_before_dispatch_and_session(adapter, name):
    adapter.dispatch = lambda *a: pytest.fail("SQL dispatch forbidden")
    assert call(adapter, name, {"sql": "DELETE FROM ships"})["code"] == "TOOL_UNAVAILABLE"
    assert len(adapter.names()) == 7
    cancel = Cancellation()
    assert adapter.__class__.dispatch(adapter, name, {}, "a", "test", cancel)["code"] == "TOOL_UNAVAILABLE"


@pytest.mark.parametrize("name,args", [
    ("search_ships", {"keyword": "X", "limit": True}),
    ("get_ship_track", {"ship_id": "3", "start_at": "x", "end_at": "y"}),
    ("query_area_ship_snapshot", {"at": "x", "bounds": {"west": 56.0}}),
    ("query_area_ship_activity", {"start_at": "x", "end_at": "y", "map_context": {}}),
])
def test_strict_arguments_before_db(adapter, name, args):
    assert call(adapter, name, args)["code"] == "INVALID_TOOL_ARGS"


def test_rate_limit_scoped_by_trusted_identity():
    instance = Adapter(rate_limit=1)
    try:
        call(instance, "unknown")
        assert call(instance, "unknown")["code"] == "RATE_LIMITED"
        assert call(instance, "unknown", scope="other")["code"] == "TOOL_UNAVAILABLE"
    finally:
        instance.close()


@pytest.mark.parametrize("status", ["ok", "partial", "no_data", "no_match", "not_found", "not_built"])
def test_status_and_quality_are_preserved(adapter, status):
    adapter.dispatch = lambda *a: {"status": status, "count": 0, "limitations": ["partial coverage"]}
    result = call(adapter, "search_ships", {"keyword": "x"})
    assert result["status"] == status
    assert result["limitations"] == ["partial coverage"]


def test_exception_and_audit_redaction(adapter, caplog):
    def fail(*args):
        raise RuntimeError("password=never-print-me")
    adapter.dispatch = fail
    with caplog.at_level("INFO", logger="hormuz.mcp.audit"):
        result = call(adapter, "search_ships", {"keyword": "private-name"})
    assert result["code"] == "TOOL_ERROR"
    assert "never-print-me" not in json.dumps(result) + caplog.text
    assert "private-name" not in caplog.text


def test_timeout_keeps_concurrency_slot_until_worker_exits():
    instance = Adapter(max_workers=1, timeout=0.02)
    release = threading.Event()
    seen = []
    def blocked(name, args, scope, request_id, cancel):
        seen.append(cancel)
        release.wait(2)
        return {"status": "ok"}
    instance.dispatch = blocked
    try:
        assert call(instance, "search_ships", {"keyword": "x"})["status"] == "timeout"
        assert seen[0].event.is_set()
        assert call(instance, "search_ships", {"keyword": "x"})["code"] == "MCP_BUSY"
    finally:
        release.set()
        instance.close()


def test_request_cancellation_sets_worker_event():
    instance = Adapter(max_workers=1)
    release, started = threading.Event(), threading.Event()
    seen = []
    def blocked(name, args, scope, request_id, cancel):
        seen.append(cancel)
        started.set()
        release.wait(2)
        return {"status": "ok"}
    instance.dispatch = blocked
    async def run():
        task = asyncio.create_task(instance.call("search_ships", {"keyword": "x"}, "a"))
        await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert seen[0].event.is_set()
    try:
        asyncio.run(run())
    finally:
        release.set()
        instance.close()


def test_custom_area_is_not_remembered(adapter, monkeypatch):
    from backend.app.services.area_activity import service
    seen = []
    def query(db, **kwargs):
        seen.append(kwargs)
        return {"status": "no_data", "quality": {"coverage": "unknown"}}
    monkeypatch.setattr(service, "query_snapshot", query)
    @contextmanager
    def fake_session():
        yield object()
    adapter.session_factory = fake_session
    args = {"at": "2026-02-28T00:00:00Z", "bounds": {"west": 56.1, "south": 26.1, "east": 56.2, "north": 26.2}}
    first = call(adapter, "query_area_ship_snapshot", args)
    second = call(adapter, "query_area_ship_snapshot", {"at": args["at"]}, scope="client-b")
    assert not seen[0]["is_default"] and seen[1]["is_default"]
    assert first["area_context"]["area_id"] == "custom"
    assert second["area_context"]["area_id"] == "hormuz_core_v1"
    assert second["quality"] == {"coverage": "unknown"}


@pytest.mark.parametrize("flag", [None, "true", "invalid"])
def test_startup_ignores_legacy_sql_settings(monkeypatch, flag):
    from backend.mcp_server import __main__ as cli
    if flag is None:
        monkeypatch.delenv("MCP_SQL_ENABLED", raising=False)
    else:
        monkeypatch.setenv("MCP_SQL_ENABLED", flag)
    monkeypatch.setenv("AGENT_DB_PASSWORD_CREDENTIAL", "unavailable-sentinel")
    monkeypatch.setenv("AGENT_QUERY_ENABLED", "true")
    # No DB connection or native credential access in this startup test.
    monkeypatch.setattr(cli, "resolve_passwords", lambda: None)
    monkeypatch.setattr(cli, "business_engine_from_env",
                        lambda: type("Engine", (), {"dispose": lambda self: None})())
    instance = cli.configured_adapter()
    try:
        assert len(instance.names()) == 7
        assert not hasattr(instance, "executor_factory")
    finally:
        instance.close()


def test_readonly_transaction_timeout_and_cancel_guard(adapter, monkeypatch):
    import backend.mcp_server.adapter as module
    commands, handlers = [], []
    class Driver:
        def cancel(self):
            commands.append("driver_cancel")
    class Connection:
        connection = type("Proxy", (), {"driver_connection": Driver()})()
    connection = Connection()
    class Database:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            commands.append("close_or_end")
        def begin(self):
            return self
        def execute(self, statement, parameters=None):
            commands.append((str(statement), parameters))
        def connection(self):
            return connection
    monkeypatch.setattr(module, "Session", lambda engine: Database())
    monkeypatch.setattr(module.event, "listen", lambda conn, name, callback: handlers.append(callback))
    monkeypatch.setattr(module.event, "remove", lambda conn, name, callback: commands.append("removed"))
    adapter.engine = type("Engine", (), {"dispose": lambda self: None})()
    cancel = Cancellation()
    with adapter.session(cancel):
        assert commands[0][0] == "SET TRANSACTION READ ONLY"
        assert commands[1][1] == {"v": "5000"}
        assert commands[2][1] == {"v": "1000"}
        cancel.cancel()
        with pytest.raises(ValueError):
            handlers[0](None, None, None, None, None, False)
    assert "driver_cancel" in commands
    assert "removed" in commands
    assert cancel.connection is None


@pytest.mark.parametrize("args", [
    {"ship_id": 1, "start_at": "2026-02-28T00:00:00", "end_at": "2026-03-01T00:00:00Z"},
    {"ship_id": 1, "start_at": "2026-02-28T00:00:00Z", "end_at": "2026-03-02T00:00:00Z"},
])
def test_time_bounds_rejected_before_database(adapter, args):
    adapter.dispatch = lambda *a: pytest.fail("Invalid time must not touch dispatch/database")
    assert call(adapter, "get_ship_track", args)["code"] == "INVALID_TOOL_ARGS"
