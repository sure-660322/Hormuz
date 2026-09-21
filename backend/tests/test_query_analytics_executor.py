"""SQL-04 executor tests.

The PostgreSQL checks are skipped during the ordinary offline suite.  Run the
tracked PowerShell verifier to provision a one-use PostgreSQL 17 database and
set the required SQL04_TEST_* environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

import psycopg
import pytest

from backend.app.services.agent.query_analytics_executor import (
    CatalogMismatchError,
    ExecutorConfig,
    ExecutorConfigurationError,
    QueryAnalyticsExecutor,
    QueryExecutionError,
)


def test_feature_flag_defaults_closed() -> None:
    config = ExecutorConfig.from_env({})
    assert config.enabled is False
    with pytest.raises(ExecutorConfigurationError) as caught:
        QueryAnalyticsExecutor(config)
    assert caught.value.code == "AGENT_QUERY_UNAVAILABLE"


def test_enabled_config_requires_dedicated_role_and_loopback() -> None:
    base = {
        "AGENT_QUERY_ENABLED": "true",
        "AGENT_DB_USER": "application_admin",
        "AGENT_DB_PASSWORD": "not-logged",
        "AGENT_DB_HOST": "127.0.0.1",
        "AGENT_DB_PORT": "5432",
        "AGENT_DB_NAME": "fixture",
    }
    with pytest.raises(ExecutorConfigurationError):
        ExecutorConfig.from_env(base)
    base["AGENT_DB_USER"] = "agent_reader_login"
    base["AGENT_QUERY_BIND_HOST"] = "0.0.0.0"
    with pytest.raises(ExecutorConfigurationError):
        ExecutorConfig.from_env(base)


class _ExplodingEngine:
    def connect(self):  # pragma: no cover - the assertion is that this is never reached
        raise AssertionError("policy refusal must not contact PostgreSQL")


def test_policy_refusal_happens_before_any_database_call() -> None:
    config = ExecutorConfig(
        enabled=True, db_user="agent_reader_login", db_password="placeholder",
        db_host="127.0.0.1", db_port=5432, db_name="fixture",
    )
    executor = QueryAnalyticsExecutor(config, engine=_ExplodingEngine())
    with pytest.raises(QueryExecutionError) as caught:
        executor.execute(
            sql="DELETE FROM public.news", params=[], purpose="write",
            request_id="req_offline", call_id="call_offline",
        )
    assert caught.value.status == "refused"
    assert caught.value.code == "AGENT_QUERY_REFUSED"


def test_process_concurrency_limit_rejects_without_queue_or_database_call() -> None:
    config = ExecutorConfig(
        enabled=True, db_user="agent_reader_login", db_password="placeholder",
        db_host="127.0.0.1", db_port=5432, db_name="fixture",
    )
    occupied = threading.BoundedSemaphore(1)
    assert occupied.acquire(blocking=False)
    executor = QueryAnalyticsExecutor(
        config, engine=_ExplodingEngine(), process_slots=occupied,
    )
    try:
        with pytest.raises(QueryExecutionError) as caught:
            executor.execute(
                sql="SELECT ship_id FROM agent_data.v_ships", params=[], purpose="busy",
                request_id="req_busy", call_id="call_busy",
            )
        assert caught.value.code == "AGENT_QUERY_BUSY"
        assert caught.value.query_executed is False
    finally:
        occupied.release()


INTEGRATION = os.getenv("SQL04_TEST_INTEGRATION") == "1"
requires_postgres = pytest.mark.skipif(not INTEGRATION, reason="use scripts/verify_query_analytics_executor.ps1")


@pytest.fixture()
def executor() -> QueryAnalyticsExecutor:
    if not INTEGRATION:
        pytest.skip("SQL-04 integration environment is not provisioned")
    instance = QueryAnalyticsExecutor.from_env()
    yield instance
    instance.dispose()


def _execute(executor: QueryAnalyticsExecutor, sql: str, params=None, *, call="call_01"):
    return executor.execute(
        sql=sql, params=params or [], purpose="SQL-04 isolated verification",
        request_id="req_sql04", call_id=call,
    )


@requires_postgres
def test_integration_normal_zero_aggregate_join_and_typed_binding(executor) -> None:
    normal = _execute(
        executor,
        "SELECT news_id, reported_date FROM agent_data.v_news "
        "WHERE reported_date = :p_date ORDER BY news_id LIMIT 3",
        [{"name": "p_date", "type": "date", "value": "2026-09-20"}],
    )
    assert normal.status == "ok"
    assert normal.returned_row_count == 3
    assert normal.rows[0][1] == "2026-09-20"
    assert normal.source["catalog_version"] == "1.0"
    assert normal.source["views"] == ["agent_data.v_news"]

    empty = _execute(
        executor,
        "SELECT news_id FROM agent_data.v_news WHERE news_id = :p_id",
        [{"name": "p_id", "type": "text", "value": "absent"}],
        call="call_zero",
    )
    assert empty.status == "ok"
    assert empty.returned_row_count == 0
    assert empty.truncated is False

    aggregate = _execute(
        executor,
        "SELECT event_id, COUNT(*) AS event_count FROM agent_data.v_news "
        "GROUP BY event_id ORDER BY event_id",
        call="call_aggregate",
    )
    assert aggregate.rows == (("evt_fixture", 601),)

    joined = _execute(
        executor,
        "SELECT v_news.news_id, v_events.event_type FROM agent_data.v_news "
        "JOIN agent_data.v_events ON v_news.event_id = v_events.event_id "
        "ORDER BY v_news.news_id LIMIT 2",
        call="call_join",
    )
    assert joined.returned_row_count == 2
    assert joined.source["views"] == ["agent_data.v_news", "agent_data.v_events"]


@requires_postgres
def test_integration_row_and_byte_limits_stream_and_mark_truncated(executor) -> None:
    by_rows = _execute(
        executor,
        "SELECT news_id FROM agent_data.v_news ORDER BY news_id",
        call="call_rows",
    )
    assert by_rows.returned_row_count == 500
    assert by_rows.truncated is True

    by_bytes = _execute(
        executor,
        "SELECT news_id, title FROM agent_data.v_news ORDER BY news_id",
        call="call_bytes",
    )
    assert 0 < by_bytes.returned_row_count < 500
    assert by_bytes.truncated is True
    encoded = sum(len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode()) for row in by_bytes.rows)
    assert encoded <= 256 * 1024


@requires_postgres
def test_integration_catalog_hash_drift_fails_closed(tmp_path, executor) -> None:
    original = json.loads(Path(executor.catalog_path).read_text(encoding="utf-8"))
    original["views"][0]["definition_sha256"] = "0" * 64
    drifted = tmp_path / "catalog.json"
    drifted.write_text(json.dumps(original), encoding="utf-8")
    drift_executor = QueryAnalyticsExecutor(executor.config, catalog_path=drifted)
    try:
        with pytest.raises(CatalogMismatchError) as caught:
            _execute(drift_executor, "SELECT ship_id FROM agent_data.v_ships", call="call_drift")
        assert "view_hash:agent_data.v_ships" in caught.value.mismatches
        assert caught.value.http_status == 503
    finally:
        drift_executor.dispose()


@requires_postgres
def test_integration_lock_timeout_and_cancel_leave_no_active_query(executor) -> None:
    admin_dsn = os.environ["SQL04_TEST_ADMIN_DSN"]
    with psycopg.connect(admin_dsn) as admin:
        admin.execute("LOCK TABLE public.news IN ACCESS EXCLUSIVE MODE")
        with pytest.raises(QueryExecutionError) as timeout:
            _execute(executor, "SELECT news_id FROM agent_data.v_news", call="call_timeout")
        assert timeout.value.status == "timeout"
        assert timeout.value.code == "AGENT_QUERY_TIMEOUT"

    cancel_event = threading.Event()
    with psycopg.connect(admin_dsn) as admin:
        admin.execute("LOCK TABLE public.news IN ACCESS EXCLUSIVE MODE")
        timer = threading.Timer(0.15, cancel_event.set)
        timer.start()
        try:
            with pytest.raises(QueryExecutionError) as cancelled:
                executor.execute(
                    sql="SELECT news_id FROM agent_data.v_news", params=[], purpose="cancel test",
                    request_id="req_cancel", call_id="call_cancel", cancel_event=cancel_event,
                )
            assert cancelled.value.code == "AGENT_QUERY_TIMEOUT"
        finally:
            timer.cancel()

    with psycopg.connect(admin_dsn) as admin:
        active = admin.execute(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE usename = 'agent_reader_login' AND state = 'active' "
            "AND query LIKE 'SELECT news_id FROM agent_data.v_news%'"
        ).fetchone()[0]
    assert active == 0


@requires_postgres
def test_integration_permission_failure_maps_without_database_text(executor) -> None:
    admin_dsn = os.environ["SQL04_TEST_ADMIN_DSN"]

    class SkipAttestationExecutor(QueryAnalyticsExecutor):
        def _verify_catalog(self, connection, catalog):
            return ("test_only",)

    bypass = SkipAttestationExecutor(executor.config)
    try:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("REVOKE SELECT ON agent_data.v_news FROM agent_reader")
        with pytest.raises(QueryExecutionError) as caught:
            _execute(bypass, "SELECT news_id FROM agent_data.v_news", call="call_permission")
        assert caught.value.status == "permission_failed"
        assert caught.value.code == "AGENT_QUERY_UNAVAILABLE"
        assert "permission denied" not in caught.value.public_message.lower()
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute("GRANT SELECT ON agent_data.v_news TO agent_reader")
        bypass.dispose()


@requires_postgres
def test_integration_global_concurrency_rejects_without_waiting(executor) -> None:
    admin_dsn = os.environ["SQL04_TEST_ADMIN_DSN"]
    holders = [psycopg.connect(admin_dsn) for _ in range(4)]
    try:
        for slot, holder in enumerate(holders):
            assert holder.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)", (20_801, slot)
            ).fetchone()[0]
        with pytest.raises(QueryExecutionError) as caught:
            _execute(executor, "SELECT ship_id FROM agent_data.v_ships", call="call_busy")
        assert caught.value.code == "AGENT_QUERY_BUSY"
        assert caught.value.status == "refused"
    finally:
        for holder in holders:
            holder.rollback()
            holder.close()


@requires_postgres
def test_integration_audit_contains_hashes_not_sql_params_or_credentials(executor) -> None:
    records: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    capture = Capture()
    executor.audit_logger.addHandler(capture)
    executor.audit_logger.setLevel(logging.INFO)
    secret_value = "audit-secret-value"
    try:
        result = _execute(
            executor,
            "SELECT news_id FROM agent_data.v_news WHERE news_id = :p_id",
            [{"name": "p_id", "type": "text", "value": secret_value}],
            call="call_audit",
        )
        assert result.returned_row_count == 0
    finally:
        executor.audit_logger.removeHandler(capture)
    joined = "\n".join(records)
    assert secret_value not in joined
    assert "SELECT news_id" not in joined
    assert executor.config.db_password not in joined
    parsed = [json.loads(item) for item in records]
    assert any(item["event"] == "catalog_verified" for item in parsed)
    finished = next(item for item in parsed if item["event"] == "query_finished")
    assert finished["status"] == "ok"
    assert len(finished["sql_sha256"]) == 64
    assert len(finished["params_sha256"]) == 64
