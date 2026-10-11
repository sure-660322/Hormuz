"""No LangChain/model invocation: calls existing read-only business services."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
import logging
import os
import threading
import time
import uuid

from pydantic import ValidationError
from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.mcp_server.schemas import TOOLS
from backend.app.services.agent.serialization import to_jsonable

LOGGER = logging.getLogger("hormuz.mcp.audit")
ADAPTER_VERSION = "0.2.0"


def failure(code, message, status="error"):
    return {"status": status, "code": code, "message": message}


@dataclass
class Cancellation:
    event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    connection: object = None

    def cancel(self):
        self.event.set()
        with self.lock:
            if self.connection is not None:
                try:
                    self.connection.cancel()
                except Exception:
                    pass  # Do not expose driver/connection details.


def business_engine_from_env():
    names = [f"MCP_DB_{key}" for key in ("USER", "PASSWORD", "HOST", "PORT", "NAME")]
    if any(not os.environ.get(key) for key in names):
        raise ValueError("MCP business database configuration is incomplete")
    # Legacy ORM imports require DB_* at import time. Supply placeholders only:
    # the ORM engine is never used here; actual queries use the MCP-specific engine.
    for key, value in {"USER": "unused", "PASSWORD": "unused", "HOST": "127.0.0.1",
                       "PORT": "5432", "NAME": "unused"}.items():
        os.environ.setdefault(f"DB_{key}", value)
    port = int(os.environ["MCP_DB_PORT"])
    if not 1 <= port <= 65535:
        raise ValueError("Invalid MCP database port")
    return create_engine(URL.create("postgresql+psycopg", username=os.environ["MCP_DB_USER"],
                         password=os.environ["MCP_DB_PASSWORD"], host=os.environ["MCP_DB_HOST"],
                         port=port, database=os.environ["MCP_DB_NAME"]),
                         pool_size=4, max_overflow=0, pool_timeout=2,
                         connect_args={"connect_timeout": 3})


class Adapter:
    def __init__(self, *, session_factory=None,
                 max_workers=4, timeout=30, rate_limit=60):
        self.session_factory = session_factory
        self.timeout, self.rate_limit = timeout, rate_limit
        self.pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="mcp-query")
        self.slots = threading.BoundedSemaphore(max_workers)
        self.rate_lock = threading.Lock()
        self.rates = {}
        self.engine = None

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.engine is not None:
            self.engine.dispose()

    def names(self):
        return list(TOOLS)

    def _allow(self, scope):
        with self.rate_lock:
            now = time.monotonic()
            self.rates = {k: v for k, v in self.rates.items() if now - v[0] < 60}
            start, count = self.rates.get(scope, (now, 0))
            if count >= self.rate_limit or (scope not in self.rates and len(self.rates) >= 256):
                return False
            self.rates[scope] = (start, count + 1)
            return True

    async def call(self, name, arguments, scope):
        request_id = f"req_{uuid.uuid4().hex}"
        if not self._allow(scope):
            result = failure("RATE_LIMITED", "Local client call budget exhausted", "refused")
        elif name not in self.names():
            result = failure("TOOL_UNAVAILABLE", "Tool is not enabled", "refused")
        else:
            try:
                args = TOOLS[name][0].model_validate(arguments).model_dump()
            except ValidationError:
                result = failure("INVALID_TOOL_ARGS", "Arguments do not match the advertised schema")
            else:
                result = await self._run(name, args, scope, request_id)
        result = {"request_id": request_id, "tool_name": name, "adapter_version": ADAPTER_VERSION,
                  **to_jsonable(result)}
        # IDs/status only: no SQL, arguments, credentials, data rows or exception text.
        LOGGER.info("request=%s tool=%s status=%s code=%s", request_id,
                    name if name in TOOLS else "unknown", result.get("status"), result.get("code", ""))
        return result

    async def _run(self, name, args, scope, request_id):
        if not self.slots.acquire(blocking=False):
            return failure("MCP_BUSY", "Local query concurrency exhausted", "refused")
        cancel = Cancellation()

        def worker():
            try:
                if cancel.event.is_set():
                    return failure("CANCELLED", "Query cancelled", "cancelled")
                return self.dispatch(name, args, scope, request_id, cancel)
            except ValueError:
                return failure("INVALID_TOOL_ARGS", "Invalid bounds, time window or configured limits")
            except SQLAlchemyError as exc:
                state = getattr(getattr(exc, "orig", None), "sqlstate", None)
                if state == "57014":
                    return failure("QUERY_TIMEOUT", "Database query cancelled or timed out", "timeout")
                return failure("DATABASE_UNAVAILABLE", "Configured database is unavailable")
            except Exception:
                return failure("TOOL_ERROR", "Tool failed; connection and internal details withheld")
            finally:
                self.slots.release()  # Retain slot until the worker really exits.

        try:
            future = self.pool.submit(worker)
        except Exception:
            self.slots.release()
            return failure("MCP_UNAVAILABLE", "MCP worker is unavailable")
        try:
            return await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), self.timeout)
        except TimeoutError:
            cancel.cancel()
            return failure("QUERY_TIMEOUT", "Query exceeded local time budget", "timeout")
        except asyncio.CancelledError:
            cancel.cancel()
            raise

    @contextmanager
    def session(self, cancel):
        if self.session_factory is not None:
            with self.session_factory() as db:
                yield db
            return
        if self.engine is None:
            # Serialized first engine initialization, no lazy shared ORM Session.
            with self.rate_lock:
                if self.engine is None:
                    self.engine = business_engine_from_env()
        with Session(self.engine) as db:
            with db.begin():
                db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SELECT set_config('statement_timeout', :v, true)"), {"v": "5000"})
                db.execute(text("SELECT set_config('lock_timeout', :v, true)"), {"v": "1000"})
                with cancel.lock:
                    connection = db.connection()
                    cancel.connection = connection.connection.driver_connection

                def before_query(conn, cursor, statement, parameters, context, executemany):
                    if cancel.event.is_set():
                        raise ValueError("Query cancelled")

                event.listen(connection, "before_cursor_execute", before_query)
                try:
                    if cancel.event.is_set():
                        raise ValueError("Cancelled before query")
                    yield db
                finally:
                    event.remove(connection, "before_cursor_execute", before_query)
                    with cancel.lock:
                        cancel.connection = None
                # No source writes; transaction ends before the Session is returned.

    def dispatch(self, name, args, scope, request_id, cancel):
        if name not in TOOLS:
            return failure("TOOL_UNAVAILABLE", "Tool is not enabled", "refused")
        if "bounds" in args:
            from backend.app.services.area_activity.context import resolve_area_context
            resolve_area_context(args["bounds"]).bounds.validate()
        with self.session(cancel) as db:
            return self.business(name, args, db)

    @staticmethod
    def business(name, args, db):
        from backend.app.services.agent.results import parse_time_arg
        from backend.app.services.agent.ship_search import search_ships
        from backend.app.services.agent.ship_tracks import get_ship_track
        from backend.app.services.agent.strait_statistics import (
            query_strait_passage_statistics, compare_strait_passage_statistics)
        from backend.app.services.area_activity import service as area_service
        from backend.app.services.area_activity.context import resolve_area_context

        def timestamp(key):
            return parse_time_arg(args[key])

        if name == "search_ships":
            return to_jsonable(search_ships(db, **args))
        if name == "get_ship_track":
            return to_jsonable(get_ship_track(db, args["ship_id"], timestamp("start_at"), timestamp("end_at")))
        if name == "query_strait_passage_statistics":
            return to_jsonable(query_strait_passage_statistics(db, timestamp("start_at"), timestamp("end_at"),
                               args["ship_types"], args["direction"]))
        if name == "compare_strait_passage_statistics":
            return to_jsonable(compare_strait_passage_statistics(db, timestamp("start_a"), timestamp("end_a"),
                               timestamp("start_b"), timestamp("end_b"), args["ship_types"], args["direction"]))
        ctx = resolve_area_context(args["bounds"])
        common = dict(bounds=ctx.bounds, is_default=ctx.is_default, ship_type_values=args["ship_types"])
        if name == "query_area_ship_snapshot":
            result = area_service.query_snapshot(db, at=timestamp("at"), **common,
                       freshness_seconds=args["freshness_seconds"], limit=50)
        elif name == "query_area_ship_activity":
            result = area_service.query_activity(db, start=timestamp("start_at"), end=timestamp("end_at"),
                       **common, batch_ids=args["batch_ids"], visit_limit=30)
        else:
            result = area_service.compare_activity(db, start_a=timestamp("start_a"), end_a=timestamp("end_a"),
                       start_b=timestamp("start_b"), end_b=timestamp("end_b"), **common,
                       batch_ids=args["batch_ids"], visit_limit=30)
        return {**to_jsonable(result), "area_context": ctx.payload()}
