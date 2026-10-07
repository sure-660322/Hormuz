"""Issue #41 opt-in real PostgreSQL timeout verification (20 seconds, read-only).

Run from repository root using the configured backend environment.
Only this process patches fetch_latest_fixes to run pg_sleep(21); the live API is untouched.
The real service sets its 20s timeout and the real router must map PostgreSQL cancellation to 503.
No source table, global database setting, or credential is changed or printed.
"""
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import SessionLocal, get_db
from backend.app.services.area_activity import repository, params


def main():
    seen = {}
    def read_only_db():
        with SessionLocal() as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            yield db
            db.rollback()
    def slow_query(db, **kwargs):
        seen["read_only"] = db.execute(text("SHOW transaction_read_only")).scalar()
        seen["timeout"] = db.execute(text("SHOW statement_timeout")).scalar()
        db.execute(text("SELECT pg_sleep(:seconds)"), {"seconds": 21})
        return []
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = read_only_db
    try:
        started = time.monotonic()
        with patch.object(repository, "fetch_latest_fixes", slow_query):
            with TestClient(app) as client:
                response = client.get("/api/area-activity/snapshot", params={"at": "2026-02-28T12:00:00Z"})
        seen.update(http_status=response.status_code,
                    error_code=response.json().get("detail", {}).get("code"),
                    elapsed_seconds=round(time.monotonic() - started, 3),
                    configured_timeout_ms=params.STATEMENT_TIMEOUT_MS)
        seen["passed"] = (seen["read_only"] == "on" and seen["http_status"] == 503
                          and seen["error_code"] == "QUERY_TIMEOUT"
                          and seen["elapsed_seconds"] >= 20)
        output = Path("output/acceptance/statement_timeout_current.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(seen, indent=2), encoding="utf-8")
        print(json.dumps(seen))
        return 0 if seen["passed"] else 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


if __name__ == "__main__":
    raise SystemExit(main())
