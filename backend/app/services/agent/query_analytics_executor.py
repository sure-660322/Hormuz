"""SQL-04 isolated read-only executor for validated analytics queries.

This module deliberately has no dependency on the application's main database
engine and is not registered as an Agent tool.  SQL-05 may call it only after
the feature flag and local-only deployment boundary are wired into the runner.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError as PoolTimeoutError

from .query_analytics_policy import (
    CATALOG_PATH,
    BoundParameter,
    QueryInputError,
    QueryPolicyError,
    QueryRefusedError,
    QuerySyntaxError,
    ValidatedQuery,
    load_catalog,
    validate_query,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
AUDIT_LOGGER_NAME = "backend.agent.query_analytics.audit"
EXPECTED_LOGIN_ROLE = "agent_reader_login"
EXPECTED_READER_ROLE = "agent_reader"
MAX_RETURNED_ROWS = 500
MAX_RETURNED_BYTES = 256 * 1024
FETCH_BATCH_SIZE = 64
STATEMENT_TIMEOUT_MS = 5_000
LOCK_TIMEOUT_MS = 1_000
IDLE_TRANSACTION_TIMEOUT_MS = 5_000
PROCESS_CONCURRENCY = 2
GLOBAL_CONCURRENCY = 4
_GLOBAL_LOCK_NAMESPACE = 20_801
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PROCESS_SLOTS = threading.BoundedSemaphore(PROCESS_CONCURRENCY)


@dataclass(frozen=True)
class ExecutorConfig:
    enabled: bool
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    bind_host: str = "127.0.0.1"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ExecutorConfig":
        if environ is None:
            load_dotenv(PROJECT_ROOT / ".env")
            environ = os.environ
        raw_enabled = environ.get("AGENT_QUERY_ENABLED", "false").strip().lower()
        if raw_enabled not in {"true", "false"}:
            raise ExecutorConfigurationError("AGENT_QUERY_ENABLED 必须为 true 或 false")
        enabled = raw_enabled == "true"
        bind_host = environ.get("AGENT_QUERY_BIND_HOST", "127.0.0.1").strip()
        if not enabled:
            return cls(enabled=False, bind_host=bind_host)

        names = (
            "AGENT_DB_USER", "AGENT_DB_PASSWORD", "AGENT_DB_HOST",
            "AGENT_DB_PORT", "AGENT_DB_NAME",
        )
        missing = [name for name in names if not environ.get(name)]
        if missing:
            raise ExecutorConfigurationError("query_analytics 独立连接配置不完整")
        if environ["AGENT_DB_USER"] != EXPECTED_LOGIN_ROLE:
            raise ExecutorConfigurationError("query_analytics 必须使用专用只读登录角色")
        if not _is_loopback(bind_host):
            raise ExecutorConfigurationError("query_analytics 仅允许绑定本机回环地址")
        try:
            port = int(environ["AGENT_DB_PORT"])
        except ValueError as exc:
            raise ExecutorConfigurationError("AGENT_DB_PORT 必须是有效端口") from exc
        if not 1 <= port <= 65_535:
            raise ExecutorConfigurationError("AGENT_DB_PORT 必须是有效端口")
        return cls(
            enabled=True,
            db_user=environ["AGENT_DB_USER"],
            db_password=environ["AGENT_DB_PASSWORD"],
            db_host=environ["AGENT_DB_HOST"],
            db_port=port,
            db_name=environ["AGENT_DB_NAME"],
            bind_host=bind_host,
        )


@dataclass(frozen=True)
class QueryAnalyticsResult:
    query_id: str
    status: str
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    returned_row_count: int
    truncated: bool
    source: dict[str, Any]
    limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["columns"] = list(self.columns)
        value["rows"] = [list(row) for row in self.rows]
        value["limitations"] = list(self.limitations)
        return value


class QueryExecutionError(RuntimeError):
    """Stable SQL-04 failure; never expose the wrapped database exception."""

    def __init__(
        self,
        *,
        status: str,
        code: str,
        public_message: str,
        http_status: int,
        query_id: str | None = None,
        retryable: bool = False,
        query_executed: bool = False,
    ):
        super().__init__(public_message)
        self.status = status
        self.code = code
        self.public_message = public_message
        self.http_status = http_status
        self.query_id = query_id
        self.retryable = retryable
        self.query_executed = query_executed


class ExecutorConfigurationError(QueryExecutionError):
    def __init__(self, message: str = "query_analytics 当前不可用", *, query_id: str | None = None):
        super().__init__(
            status="source_unavailable", code="AGENT_QUERY_UNAVAILABLE",
            public_message=message, http_status=503, query_id=query_id,
        )


class CatalogMismatchError(ExecutorConfigurationError):
    def __init__(self, mismatches: tuple[str, ...], *, query_id: str | None = None):
        super().__init__("query_analytics 数据目录校验失败", query_id=query_id)
        self.mismatches = mismatches


def _is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _new_query_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"aq_{stamp}_{uuid.uuid4().hex[:12]}"


def _sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sqlstate(exc: BaseException) -> str | None:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        state = getattr(current, "sqlstate", None)
        if state:
            return str(state)
        current = getattr(current, "orig", None) or getattr(current, "__cause__", None)
    return None


def _json_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise ExecutorConfigurationError("query_analytics 返回了不受支持的数据类型")


def _bound_value(param: BoundParameter) -> Any:
    value = param.value
    if value is None:
        return None
    if param.type == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if param.type == "timestamptz" and isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    if param.type == "numeric" and not isinstance(value, Decimal):
        return Decimal(str(value))
    return value


class QueryAnalyticsExecutor:
    """Validate, attest and execute one query through a dedicated reader pool."""

    def __init__(
        self,
        config: ExecutorConfig,
        *,
        engine: Engine | None = None,
        catalog_path: Path = CATALOG_PATH,
        audit_logger: logging.Logger | None = None,
        process_slots: threading.BoundedSemaphore = _PROCESS_SLOTS,
    ):
        if not config.enabled:
            raise ExecutorConfigurationError("query_analytics 功能开关未开启")
        if config.db_user != EXPECTED_LOGIN_ROLE:
            raise ExecutorConfigurationError("query_analytics 必须使用专用只读登录角色")
        if not _is_loopback(config.bind_host):
            raise ExecutorConfigurationError("query_analytics 仅允许绑定本机回环地址")
        self.config = config
        self.catalog_path = catalog_path
        self.audit_logger = audit_logger or logging.getLogger(AUDIT_LOGGER_NAME)
        self._process_slots = process_slots
        self.engine = engine or self._build_engine(config)

    @staticmethod
    def _build_engine(config: ExecutorConfig) -> Engine:
        if not all((config.db_password, config.db_host, config.db_port, config.db_name)):
            raise ExecutorConfigurationError("query_analytics 独立连接配置不完整")
        url = URL.create(
            "postgresql+psycopg", username=config.db_user, password=config.db_password,
            host=config.db_host, port=config.db_port, database=config.db_name,
        )
        return create_engine(
            url,
            pool_size=PROCESS_CONCURRENCY,
            max_overflow=0,
            pool_timeout=0,
            pool_pre_ping=True,
            pool_use_lifo=True,
            pool_reset_on_return="rollback",
            connect_args={
                "connect_timeout": 3,
                "application_name": "hormuz_query_analytics",
            },
        )

    @classmethod
    def from_env(cls) -> "QueryAnalyticsExecutor":
        return cls(ExecutorConfig.from_env())

    def dispose(self) -> None:
        self.engine.dispose()

    def execute(
        self,
        *,
        sql: str,
        params: list[dict[str, Any]] | None,
        purpose: str,
        request_id: str,
        call_id: str,
        cancel_event: threading.Event | None = None,
    ) -> QueryAnalyticsResult:
        query_id = _new_query_id()
        started = time.perf_counter()
        base_audit = {
            "event": "query_finished", "request_id": request_id, "call_id": call_id,
            "query_id": query_id, "sql_sha256": _sha256_json(sql),
            "params_sha256": _sha256_json(params or []),
            "purpose_sha256": _sha256_json(purpose),
        }
        try:
            self._validate_audit_ids(request_id, call_id)
            catalog = load_catalog(self.catalog_path)
            validated = validate_query(sql, params, purpose, catalog=catalog)
            base_audit["normalized_sql_sha256"] = _sha256_json(validated.normalized_sql)
        except QueryPolicyError as exc:
            mapped = self._map_policy_error(exc, query_id)
            self._audit(base_audit, started, status=mapped.status, error_code=mapped.code, query_executed=False)
            raise mapped from None
        except QueryExecutionError as exc:
            exc.query_id = query_id
            self._audit(base_audit, started, status=exc.status, error_code=exc.code, query_executed=False)
            raise

        if not self._process_slots.acquire(blocking=False):
            error = QueryExecutionError(
                status="refused", code="AGENT_QUERY_BUSY",
                public_message="query_analytics 并发已满，请稍后重试",
                http_status=200, query_id=query_id,
            )
            self._audit(base_audit, started, status=error.status, error_code=error.code, query_executed=False)
            raise error
        try:
            result = self._execute_validated(
                validated, catalog, query_id=query_id, cancel_event=cancel_event,
            )
            self._audit(
                base_audit, started, status="ok", error_code=None, query_executed=True,
                returned_row_count=result.returned_row_count, truncated=result.truncated,
                returned_bytes=sum(len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) for row in result.rows),
                catalog_version=validated.catalog_version, views=list(validated.referenced_views),
            )
            return result
        except QueryExecutionError as exc:
            if exc.query_id is None:
                exc.query_id = query_id
            extra: dict[str, Any] = {}
            if isinstance(exc, CatalogMismatchError):
                extra["catalog_mismatches"] = list(exc.mismatches)
            self._audit(
                base_audit, started, status=exc.status, error_code=exc.code,
                query_executed=exc.query_executed, **extra,
            )
            raise
        finally:
            self._process_slots.release()

    @staticmethod
    def _validate_audit_ids(request_id: str, call_id: str) -> None:
        if not isinstance(request_id, str) or not _SAFE_ID.fullmatch(request_id):
            raise QueryInputError("request_id 格式无效")
        if not isinstance(call_id, str) or not _SAFE_ID.fullmatch(call_id):
            raise QueryInputError("call_id 格式无效")

    @staticmethod
    def _map_policy_error(exc: QueryPolicyError, query_id: str) -> QueryExecutionError:
        if isinstance(exc, QuerySyntaxError):
            return QueryExecutionError(
                status="syntax_error", code="AGENT_QUERY_SYNTAX",
                public_message="SQL 语法无法解析", http_status=200,
                query_id=query_id, retryable=True,
            )
        if isinstance(exc, (QueryRefusedError, QueryInputError)):
            return QueryExecutionError(
                status="refused", code="AGENT_QUERY_REFUSED",
                public_message="查询未通过只读安全策略", http_status=200,
                query_id=query_id,
            )
        return ExecutorConfigurationError(query_id=query_id)

    def _execute_validated(
        self,
        validated: ValidatedQuery,
        catalog: dict[str, Any],
        *,
        query_id: str,
        cancel_event: threading.Event | None,
    ) -> QueryAnalyticsResult:
        try:
            with self.engine.connect() as connection:
                transaction = connection.begin()
                try:
                    self._set_transaction_guards(connection)
                    if not self._acquire_global_slot(connection):
                        raise QueryExecutionError(
                            status="refused", code="AGENT_QUERY_BUSY",
                            public_message="query_analytics 全局并发已满，请稍后重试",
                            http_status=200, query_id=query_id,
                        )
                    checks = self._verify_catalog(connection, catalog)
                    self._emit_catalog_audit(query_id, validated.catalog_version, checks)
                    result = self._stream_query(
                        connection, validated, catalog, query_id=query_id,
                        cancel_event=cancel_event,
                    )
                    transaction.commit()
                    return result
                except BaseException:
                    if transaction.is_active:
                        transaction.rollback()
                    raise
        except QueryExecutionError:
            raise
        except PoolTimeoutError as exc:
            raise QueryExecutionError(
                status="refused", code="AGENT_QUERY_BUSY",
                public_message="query_analytics 并发已满，请稍后重试",
                http_status=200, query_id=query_id,
            ) from exc
        except (DBAPIError, OperationalError) as exc:
            raise self._map_database_error(exc, query_id) from None
        except Exception as exc:
            raise ExecutorConfigurationError(query_id=query_id) from exc

    @staticmethod
    def _set_transaction_guards(connection: Connection) -> None:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog")
        connection.exec_driver_sql(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms'")
        connection.exec_driver_sql(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'")
        connection.exec_driver_sql(
            f"SET LOCAL idle_in_transaction_session_timeout = '{IDLE_TRANSACTION_TIMEOUT_MS}ms'"
        )

    @staticmethod
    def _acquire_global_slot(connection: Connection) -> bool:
        for slot in range(GLOBAL_CONCURRENCY):
            acquired = connection.exec_driver_sql(
                "SELECT pg_catalog.pg_try_advisory_xact_lock(%(namespace)s, %(slot)s)",
                {"namespace": _GLOBAL_LOCK_NAMESPACE, "slot": slot},
            ).scalar_one()
            if acquired:
                return True
        return False

    def _verify_catalog(self, connection: Connection, catalog: dict[str, Any]) -> tuple[str, ...]:
        mismatches: list[str] = []
        checks: list[str] = []

        major = connection.exec_driver_sql(
            "SELECT current_setting('server_version_num')::integer / 10000"
        ).scalar_one()
        if major != catalog.get("postgres_major"):
            mismatches.append("postgres_major")
        checks.append("postgres_major")

        role = connection.exec_driver_sql(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin,
                   rolinherit, rolreplication, rolbypassrls, rolconnlimit
            FROM pg_roles WHERE rolname = current_user
            """
        ).mappings().one_or_none()
        expected_role = {
            "rolname": EXPECTED_LOGIN_ROLE, "rolsuper": False, "rolcreatedb": False,
            "rolcreaterole": False, "rolcanlogin": True, "rolinherit": True,
            "rolreplication": False, "rolbypassrls": False, "rolconnlimit": 4,
        }
        if role is None or any(role[key] != value for key, value in expected_role.items()):
            mismatches.append("login_role")
        checks.append("login_role")

        memberships = tuple(connection.exec_driver_sql(
            """
            SELECT member.rolname, granted.rolname
            FROM pg_auth_members AS membership
            JOIN pg_roles AS granted ON granted.oid = membership.roleid
            JOIN pg_roles AS member ON member.oid = membership.member
            WHERE member.rolname IN (current_user, 'agent_reader')
            ORDER BY member.rolname, granted.rolname
            """
        ).all())
        if memberships != ((EXPECTED_LOGIN_ROLE, EXPECTED_READER_ROLE),):
            mismatches.append("role_memberships")
        checks.append("role_memberships")

        boundary_roles = tuple(connection.exec_driver_sql(
            """
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin,
                   rolinherit, rolreplication, rolbypassrls
            FROM pg_roles WHERE rolname IN ('agent_reader', 'agent_view_owner')
            ORDER BY rolname
            """
        ).all())
        expected_boundary_roles = (
            ("agent_reader", False, False, False, False, False, False, False),
            ("agent_view_owner", False, False, False, False, False, False, False),
        )
        if boundary_roles != expected_boundary_roles:
            mismatches.append("boundary_roles")
        checks.append("boundary_roles")

        schemas = tuple(row[0] for row in connection.exec_driver_sql(
            """
            SELECT nspname FROM pg_namespace
            WHERE nspname NOT LIKE 'pg_%%' AND nspname <> 'information_schema'
              AND has_schema_privilege(current_user, oid, 'USAGE')
            ORDER BY nspname
            """
        ).all())
        privileges = connection.exec_driver_sql(
            """
            SELECT has_schema_privilege(current_user, 'agent_data', 'USAGE'),
                   has_schema_privilege(current_user, 'agent_data', 'CREATE'),
                   has_database_privilege(current_user, current_database(), 'TEMP'),
                   has_database_privilege(current_user, current_database(), 'CREATE')
            """
        ).one()
        if schemas != ("agent_data",) or tuple(privileges) != (True, False, False, False):
            mismatches.append("schema_privileges")
        checks.append("schema_privileges")

        expected_names = tuple(sorted(view["name"] for view in catalog["views"]))
        actual_names = tuple(row[0] for row in connection.exec_driver_sql(
            """
            SELECT n.nspname || '.' || c.relname
            FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'agent_data' AND c.relkind IN ('r','p','v','m','f')
            ORDER BY 1
            """
        ).all())
        if actual_names != expected_names:
            mismatches.append("relation_inventory")
        checks.append("relation_inventory")

        function_count = connection.exec_driver_sql(
            """
            SELECT count(*) FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
            WHERE n.nspname = 'agent_data'
            """
        ).scalar_one()
        if function_count != 0:
            mismatches.append("function_inventory")
        checks.append("function_inventory")

        for view in catalog["views"]:
            name = view["name"]
            meta = connection.exec_driver_sql(
                """
                SELECT pg_get_userbyid(c.relowner),
                       has_table_privilege(current_user, c.oid, 'SELECT')
                FROM pg_class AS c WHERE c.oid = %(view_name)s::regclass
                """,
                {"view_name": name},
            ).one_or_none()
            if meta is None or meta[0] != view["owner"] or meta[1] is not True:
                mismatches.append(f"view_access:{name}")
            definition = connection.exec_driver_sql(
                "SELECT pg_get_viewdef(%(view_name)s::regclass, false)",
                {"view_name": name},
            ).scalar_one()
            actual_hash = hashlib.sha256(definition.encode("utf-8")).hexdigest()
            if actual_hash != view["definition_sha256"]:
                mismatches.append(f"view_hash:{name}")
            actual_columns = tuple(connection.exec_driver_sql(
                """
                SELECT a.attname, format_type(a.atttypid, a.atttypmod),
                       (i.is_nullable = 'YES')
                FROM pg_attribute AS a
                JOIN pg_class AS c ON c.oid = a.attrelid
                JOIN pg_namespace AS n ON n.oid = c.relnamespace
                JOIN information_schema.columns AS i
                  ON i.table_schema = n.nspname AND i.table_name = c.relname
                 AND i.column_name = a.attname
                WHERE n.nspname = split_part(%(view_name)s, '.', 1)
                  AND c.relname = split_part(%(view_name)s, '.', 2)
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY a.attnum
                """,
                {"view_name": name},
            ).all())
            expected_columns = tuple(
                (item["name"], item["postgres_type"], bool(item["nullable"]))
                for item in view["columns"]
            )
            if actual_columns != expected_columns:
                mismatches.append(f"view_columns:{name}")
            checks.extend((f"view_access:{name}", f"view_hash:{name}", f"view_columns:{name}"))

        source_access = tuple(connection.exec_driver_sql(
            """
            SELECT c.relname, has_table_privilege(current_user, c.oid, 'SELECT')
            FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = ANY(%(names)s::text[])
            ORDER BY c.relname
            """,
            {"names": ["ships", "ship_positions", "events", "news"]},
        ).all())
        if len(source_access) != 4 or any(has_access for _, has_access in source_access):
            mismatches.append("source_table_privileges")
        checks.append("source_table_privileges")

        if mismatches:
            raise CatalogMismatchError(tuple(mismatches))
        return tuple(checks)

    def _stream_query(
        self,
        connection: Connection,
        validated: ValidatedQuery,
        catalog: dict[str, Any],
        *,
        query_id: str,
        cancel_event: threading.Event | None,
    ) -> QueryAnalyticsResult:
        params = {item.name: _bound_value(item) for item in validated.params}
        done = threading.Event()
        monitor: threading.Thread | None = None
        if cancel_event is not None:
            driver = connection.connection.driver_connection

            def cancel_when_requested() -> None:
                while not done.is_set():
                    if cancel_event.wait(0.05):
                        if not done.is_set():
                            try:
                                driver.cancel()
                            except Exception:
                                pass
                        return

            monitor = threading.Thread(target=cancel_when_requested, daemon=True)
            monitor.start()
        try:
            streaming = connection.execution_options(stream_results=True, yield_per=FETCH_BATCH_SIZE)
            result = streaming.exec_driver_sql(validated.normalized_sql, params)
            columns = tuple(result.keys())
            rows: list[tuple[Any, ...]] = []
            byte_count = 0
            truncated = False
            while True:
                batch = result.fetchmany(FETCH_BATCH_SIZE)
                if not batch:
                    break
                for raw_row in batch:
                    row = tuple(_json_scalar(value) for value in raw_row)
                    encoded_size = len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    if len(rows) >= MAX_RETURNED_ROWS or byte_count + encoded_size > MAX_RETURNED_BYTES:
                        truncated = True
                        break
                    rows.append(row)
                    byte_count += encoded_size
                if truncated:
                    break
            result.close()
        except DBAPIError as exc:
            mapped = self._map_database_error(exc, query_id)
            mapped.query_executed = True
            raise mapped from None
        finally:
            done.set()
            if monitor is not None:
                monitor.join(timeout=0.2)

        view_catalog = {item["name"]: item for item in catalog["views"]}
        limitations: list[str] = []
        for view_name in validated.referenced_views:
            limitations.extend(view_catalog[view_name].get("limitations", []))
        return QueryAnalyticsResult(
            query_id=query_id,
            status="ok",
            columns=columns,
            rows=tuple(rows),
            returned_row_count=len(rows),
            truncated=truncated,
            source={
                "catalog_version": validated.catalog_version,
                "views": list(validated.referenced_views),
                "data_scope": {
                    name: view_catalog[name]["data_scope"] for name in validated.referenced_views
                },
            },
            limitations=tuple(dict.fromkeys(limitations)),
        )

    @staticmethod
    def _map_database_error(exc: BaseException, query_id: str) -> QueryExecutionError:
        state = _sqlstate(exc)
        if state in {"57014", "55P03"}:
            return QueryExecutionError(
                status="timeout", code="AGENT_QUERY_TIMEOUT",
                public_message="query_analytics 查询超时", http_status=504,
                query_id=query_id,
            )
        if state == "53300":
            return QueryExecutionError(
                status="refused", code="AGENT_QUERY_BUSY",
                public_message="query_analytics 全局并发已满，请稍后重试",
                http_status=200, query_id=query_id,
            )
        if state in {"42501", "25006"}:
            return QueryExecutionError(
                status="permission_failed", code="AGENT_QUERY_UNAVAILABLE",
                public_message="query_analytics 只读权限配置异常", http_status=503,
                query_id=query_id,
            )
        return ExecutorConfigurationError(query_id=query_id)

    def _emit_catalog_audit(self, query_id: str, version: str, checks: tuple[str, ...]) -> None:
        self.audit_logger.info(json.dumps({
            "event": "catalog_verified", "query_id": query_id,
            "catalog_version": version, "verified_at": datetime.now(timezone.utc).isoformat(),
            "check_count": len(checks), "status": "ok",
        }, ensure_ascii=False, separators=(",", ":")))

    def _audit(self, base: dict[str, Any], started: float, **fields: Any) -> None:
        record = dict(base)
        record.update(fields)
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        self.audit_logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
