"""Development checks with fake services/executor: never connect to a real DB."""
import asyncio
from contextlib import contextmanager
import json
import threading

import pytest

from backend.mcp_server.adapter import Adapter, ApprovalStore, Cancellation

QUERY = {"sql": "SELECT ship_id FROM agent_data.v_ships WHERE ship_id = :n LIMIT 3",
         "params": [{"name": "n", "type": "int", "value": 3}], "purpose": "development"}


class Executor:
    def __init__(self):
        self.calls = []
        self.disposed = False

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        class Result:
            def to_dict(self):
                return {"status": "ok", "query_id": "fake_query", "rows": [], "returned_row_count": 0}
        return Result()

    def dispose(self):
        self.disposed = True


@pytest.fixture
def adapter():
    executor = Executor()
    instance = Adapter(sql_enabled=True, executor_factory=lambda: executor)
    instance.test_executor = executor
    yield instance
    instance.close()


def call(adapter, name, args=None, scope="client-a"):
    return asyncio.run(adapter.call(name, args or {}, scope))


def approval(adapter):
    result = call(adapter, "check_sql", QUERY)
    assert result["status"] == "ok", result
    return result["validation_token"]


def test_exact_single_use_token_and_reader_revalidation(adapter):
    token = approval(adapter)
    result = call(adapter, "execute_sql", QUERY | {"validation_token": token})
    assert result["status"] == "ok"
    assert len(adapter.test_executor.calls) == 1
    assert adapter.test_executor.calls[0]["sql"] == QUERY["sql"]
    assert isinstance(adapter.test_executor.calls[0]["cancel_event"], threading.Event)
    assert adapter.test_executor.disposed
    assert call(adapter, "execute_sql", QUERY | {"validation_token": token})["code"] == "INVALID_SQL_TOKEN"


def test_foreign_client_cannot_execute_or_revoke(adapter):
    token = approval(adapter)
    args = QUERY | {"validation_token": token}
    assert call(adapter, "execute_sql", args, "client-b")["code"] == "INVALID_SQL_TOKEN"
    assert call(adapter, "execute_sql", args)["status"] == "ok"


@pytest.mark.parametrize("change", [{"purpose": "other"}, {"params": [{"name": "n", "type": "int", "value": 4}]},
                                      {"sql": "SELECT ship_id FROM agent_data.v_ships LIMIT :other"}])
def test_modified_args_consume_and_reject_token(adapter, change):
    token = approval(adapter)
    assert call(adapter, "execute_sql", QUERY | change | {"validation_token": token})["code"] == "INVALID_SQL_TOKEN"
    assert not adapter.test_executor.calls


def test_expiry_capacity_and_catalog_drift():
    now = [0]
    store = ApprovalStore(ttl=2, capacity=1, clock=lambda: now[0])
    token = store.issue("a", QUERY, {"v": 1})
    assert store.issue("a", QUERY, {}) is None
    assert not store.consume(token, "a", QUERY, {"v": 2})
    token = store.issue("a", QUERY, {})
    now[0] = 3
    assert not store.consume(token, "a", QUERY, {})


def test_atomic_token_consumption():
    from concurrent.futures import ThreadPoolExecutor
    store = ApprovalStore()
    token = store.issue("a", QUERY, {})
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: store.consume(token, "a", QUERY, {}), range(8)))
    assert results.count(True) == 1


@pytest.mark.parametrize("sql", ["DELETE FROM ships", "SELECT * FROM public.ship_positions", "SELECT pg_sleep(:n)"])
def test_policy_denial_has_no_token_or_execution(adapter, sql):
    result = call(adapter, "check_sql", QUERY | {"sql": sql})
    assert result["status"] != "ok"
    assert "validation_token" not in result
    assert not adapter.test_executor.calls


def test_disabled_sql_is_not_discoverable():
    instance = Adapter()
    try:
        assert len(instance.names()) == 7
        assert call(instance, "check_sql", QUERY)["code"] == "TOOL_UNAVAILABLE"
    finally:
        instance.close()


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
    second = call(adapter, "query_area_ship_snapshot", {"at": args["at"]})
    assert not seen[0]["is_default"] and seen[1]["is_default"]
    assert first["area_context"]["area_id"] == "custom"
    assert second["area_context"]["area_id"] == "hormuz_core_v1"
    assert second["quality"] == {"coverage": "unknown"}


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


def test_sql_timeout_consumes_approval_and_keeps_public_state(adapter):
    from backend.app.services.agent.query_analytics_executor import QueryExecutionError
    token = approval(adapter)
    def timeout(**kwargs):
        raise QueryExecutionError(status="timeout", code="AGENT_QUERY_TIMEOUT", public_message="Query timed out",
                                  http_status=200, query_id="fake_timeout", query_executed=True)
    adapter.test_executor.execute = timeout
    result = call(adapter, "execute_sql", QUERY | {"validation_token": token})
    assert result["status"] == "timeout" and result["query_executed"]
    assert result["query_id"] == "fake_timeout" and not result["retryable"]
    assert call(adapter, "execute_sql", QUERY | {"validation_token": token})["code"] == "INVALID_SQL_TOKEN"


def test_sql_startup_rejects_different_database_without_connecting(monkeypatch):
    import backend.mcp_server.__main__ as cli
    monkeypatch.setattr(cli, "business_engine_from_env", lambda: type("Engine", (), {"dispose": lambda self: None})())
    values = {"MCP_SQL_ENABLED": "true", "AGENT_QUERY_ENABLED": "true", "AGENT_DB_USER": "agent_reader_login",
              "AGENT_DB_PASSWORD": "placeholder", "AGENT_DB_HOST": "127.0.0.1", "AGENT_DB_PORT": "5432",
              "AGENT_DB_NAME": "test_a", "MCP_DB_HOST": "127.0.0.1", "MCP_DB_PORT": "5432", "MCP_DB_NAME": "test_b"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="same database"):
        cli.configured_adapter()
