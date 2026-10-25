"""Additional cases keep the existing API and reject unsupported news claims."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.services.trajectory_cases import CASES
from backend.case_ais import audit_csv
from backend.tests.test_arctic_case import ROW, source


def test_bad_speed_is_audited_without_editing_source(tmp_path):
    row = ROW.copy()
    row[11] = "102.29"
    valid = ROW.copy()
    valid[17], valid[18] = "2026-03-27 00:01:34", "1774540894"
    path = source(tmp_path, [row, ROW, valid])
    before = path.read_bytes()
    with pytest.raises(ValueError):
        audit_csv(path)
    audit = audit_csv(path, quarantine_invalid_navigation=True)
    assert audit["raw_rows"] == 3 and audit["accepted_rows"] == 1
    assert audit["quarantined_rows"] == [2, 3]
    assert audit["rejected_rows"][0]["source_row"] == 2
    assert path.read_bytes() == before


@pytest.mark.parametrize("case_id", CASES)
def test_case_parser_requires_matching_identity(tmp_path, case_id):
    vessel = CASES[case_id]
    row = ROW.copy()
    row[0], row[2], row[3] = vessel["name"], vessel["imo"], vessel["mmsi"]
    kwargs = {k: vessel[k] for k in ("name", "imo", "mmsi")}
    assert audit_csv(source(tmp_path, [row]), **kwargs)["accepted_rows"] == 1
    row[3] = "123456789"
    with pytest.raises(ValueError):
        audit_csv(source(tmp_path, [row]), **kwargs)


@pytest.mark.parametrize("case_id", CASES)
@pytest.mark.parametrize("ready", [False, True])
def test_case_contract_and_empty_state(case_id, ready):
    from backend.app.database import get_db
    from backend.app.main import app

    class DB:
        def execute(self, sql, params):
            assert params["mmsi"] == CASES[case_id]["mmsi"]
            assert params["imo"] == CASES[case_id]["imo"]
            assert params["prefix"] == f"case/{case_id}/%"
            return self

        def mappings(self):
            return self

        def all(self):
            return [dict(id=123, start_at=datetime(2026, 6, 16, 16, tzinfo=timezone.utc),
                         end_at=datetime(2026, 6, 19, 15, tzinfo=timezone.utc), position_count=20)] if ready else []

    app.dependency_overrides[get_db] = lambda: DB()
    try:
        response = TestClient(app).get(f"/cases/{case_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] == ready and data["id"] == case_id
        assert data["display_title"] == CASES[case_id]["name"]
        assert not any(s["articles"] for s in data["stages"])
        assert all(e["kind"] == "identity" for e in data["evidence"])
        if ready:
            assert data["date_label"] == "2026.06.17 — 06.19"
            assert data["stages"][0]["start_at"] == data["start_at"]
            assert data["stages"][0]["end_at"] == data["end_at"]
        else:
            assert data["stages"] == [] and data["position_count"] == 0
            assert data["ship_id"] is None and data["start_at"] is None
    finally:
        app.dependency_overrides.clear()
