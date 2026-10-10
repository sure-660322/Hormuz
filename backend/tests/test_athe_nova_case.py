"""API identity gate and no-data contract; no database writes."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.database import get_db
from backend.app.main import app


class FakeDB:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, statement, params):
        assert params["mmsi"] == "334931000" and params["imo"] == "9188116"
        assert params["source"] == "nnu_ais"
        assert "b.source_file = b.source_day::text" in str(statement)
        assert "BETWEEN :start AND :end" in str(statement)
        return self

    def mappings(self):
        return self

    def all(self):
        return self.rows


def row(count=12):
    return dict(id=628, position_count=count,
                start_at=datetime(2026, 2, 25, tzinfo=timezone.utc) if count else None,
                end_at=datetime(2026, 3, 3, tzinfo=timezone.utc) if count else None)


@pytest.mark.parametrize("rows,ready", [([row()], True), ([], False), ([row(0)], False), ([row(), row()], False)])
def test_identity_and_source_gate(rows, ready):
    app.dependency_overrides[get_db] = lambda: FakeDB(rows)
    try:
        response = TestClient(app).get("/cases/athe-nova")
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] is ready
        assert data["id"] == "athe-nova"
        assert len(data["stages"]) == 3
        assert len(data["evidence"]) == 6
        assert not any(e["at"] for e in data["evidence"] if e["title"] == "报道说了什么")
        _assert_evidence_contract(data)
        if not ready:
            assert data["start_at"] is None and data["end_at"] is None
            assert data["unavailable_reason"]
        assert all(a["image_url"] is None for s in data["stages"] for a in s["articles"])
    finally:
        app.dependency_overrides.clear()


def _assert_evidence_contract(data):
    """issue #56 映射清单的机器可核依据：稳定 id、明确类型、范围指向真实阶段。"""
    stage_ids = {s["id"] for s in data["stages"]}
    kinds = {"ais_observation", "report", "boundary", "identity"}
    seen = set()
    for item in data["evidence"]:
        assert item["id"] and item["id"] not in seen
        seen.add(item["id"])
        assert item["kind"] in kinds
        assert set(item["stage_ids"]) <= stage_ids
        assert item["summary"]
        for stage in data["stages"]:
            if stage["id"] in item["stage_ids"] and item["at"]:
                assert stage["start_at"] <= item["at"] <= stage["end_at"], \
                    f'{item["id"]} 的观测时刻不在声明阶段 {stage["id"]} 窗口内'
    identity = next(e for e in data["evidence"] if e["kind"] == "identity")
    assert identity["stage_ids"] == []
    assert all(a["summary"] for s in data["stages"] for a in s["articles"])
