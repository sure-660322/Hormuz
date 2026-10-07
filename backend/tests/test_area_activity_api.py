"""区域活动 HTTP 契约测试：成功、有效零结果、参数错误、超时映射与响应模型。"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from backend.app.database import get_db
from backend.app.main import app as main_app
from backend.app.services.area_activity import params, service

UTC = timezone.utc
START = datetime(2026, 2, 25, 0, 0, tzinfo=UTC)
END = datetime(2026, 2, 26, 0, 0, tzinfo=UTC)
BASE = "/api/area-activity"


class _FakeSession:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


def _stats(**overrides) -> dict:
    payload = {
        "scoped_fix_count": 10, "region_fix_count": 4, "window_region_fix_count": 2,
        "first_fix_at": START, "last_fix_at": END,
    }
    payload.update(overrides)
    return payload


def _visit_row(ship_id: int = 1, base: datetime = START) -> dict:
    return {
        "ship_id": ship_id, "ship_name": f"SHIP {ship_id}", "mmsi": f"10000000{ship_id}",
        "ship_type": "油轮", "fix_id": 100 + ship_id, "recorded_at": base,
        "latitude": 26.5, "longitude": 56.5, "speed": 8.0,
        "seg_no": 0, "ship_fix_seq": 1, "is_seg_start": True, "is_seg_end": True,
        "start_break_kind": None,
        "prev_inside": False, "prev_at": base - timedelta(minutes=10),
        "prev_fix_id": 50 + ship_id, "prev_lat": 25.0, "prev_lon": 55.0,
        "between_first_fix_id": None, "between_first_at": None,
        "between_last_fix_id": None, "between_last_at": None,
        "next_inside": False, "next_at": base + timedelta(minutes=5),
        "next_fix_id": 200 + ship_id, "next_lat": 25.0, "next_lon": 55.0,
        **_stats(),
    }


@pytest.fixture
def stub(monkeypatch):
    state = {"rows": [], "stats": _stats(), "coverage": [], "snapshot_rows": []}
    monkeypatch.setattr(service.repository, "apply_session_settings", lambda *a, **k: None)
    monkeypatch.setattr(service.repository, "fetch_activity_boundaries", lambda *a, **k: state["rows"])
    monkeypatch.setattr(service.repository, "fetch_scope_stats", lambda *a, **k: state["stats"])
    monkeypatch.setattr(service.repository, "fetch_batch_coverage", lambda *a, **k: state["coverage"])
    monkeypatch.setattr(service.repository, "fetch_latest_fixes", lambda *a, **k: state["snapshot_rows"])
    return state


@pytest.fixture
def client():
    session = _FakeSession()
    main_app.dependency_overrides[get_db] = lambda: session
    yield TestClient(main_app), session
    main_app.dependency_overrides.pop(get_db, None)


def test_default_area_contract(client):
    http, _ = client
    response = http.get(f"{BASE}/default-area")
    assert response.status_code == 200
    body = response.json()
    assert body["area"]["area_id"] == params.DEFAULT_AREA_ID
    assert body["area"]["version"] == params.DEFAULT_AREA_VERSION
    assert body["area"]["bounds"] == {"south": 25.8, "west": 55.8, "north": 27.1, "east": 57.1}
    assert body["area"]["is_default"] is True
    assert "半开" in body["area"]["containment"]
    assert body["algorithm"]["version"] == params.ALGORITHM_VERSION
    assert body["limitations"]


def test_activity_success_contract(client, stub):
    stub["rows"] = [_visit_row(1), _visit_row(2, START + timedelta(hours=1))]
    http, _ = client
    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["query"]["window"]["days"] == 1
    assert body["summary"]["ships_observed"] == 2
    assert body["summary"]["observed_entry_count"] == 2
    assert len(body["daily"]) == 1 and body["daily"][0]["date"] == "2026-02-25"
    assert len(body["visits"]) == 2
    assert body["visits"][0]["visit_key"].startswith("s")
    assert body["visits"][0]["status"] == "complete"
    assert body["limits"]["detail_truncated"] is False
    assert body["coverage"]["scoped_fix_count"] == 10


def test_activity_valid_zero_result_contract(client, stub):
    stub["stats"] = _stats(region_fix_count=0, window_region_fix_count=0)
    http, _ = client
    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["summary"]["ships_observed"] == 0
    assert body["visits"] == []
    assert body["daily"][0]["ships_observed"] == 0


def test_activity_no_data_contract(client, stub):
    stub["stats"] = _stats(scoped_fix_count=0, region_fix_count=0, window_region_fix_count=0,
                           first_fix_at=None, last_fix_at=None)
    http, _ = client
    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(),
    })
    assert response.status_code == 200
    assert response.json()["status"] == "no_data"


def test_activity_rejects_naive_time_and_bad_rectangle(client, stub):
    http, _ = client
    response = http.get(f"{BASE}/activity", params={
        "start": START.replace(tzinfo=None).isoformat(), "end": END.isoformat(),
    })
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"

    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(),
        "west": 57.5, "south": 25.8, "east": 55.8, "north": 27.1,
    })
    assert response.status_code == 422
    assert "west < east" in response.json()["detail"]["message"]

    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(), "west": 55.8,
    })
    assert response.status_code == 422
    assert "同时给出" in response.json()["detail"]["message"]


def test_missing_required_query_uses_validation_handler(client):
    http, _ = client
    response = http.get(f"{BASE}/activity", params={"end": END.isoformat()})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_REQUEST"
    assert "request_id" in detail


def test_statement_timeout_maps_to_503(client, monkeypatch):
    def boom(*args, **kwargs):
        raise OperationalError(
            "SELECT 1", {}, Exception("canceling statement due to statement timeout")
        )

    monkeypatch.setattr(service, "query_activity", boom)
    http, session = client
    response = http.get(f"{BASE}/activity", params={
        "start": START.isoformat(), "end": END.isoformat(),
    })
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "QUERY_TIMEOUT"
    assert session.rolled_back is True


def test_snapshot_contract(client, stub):
    stub["snapshot_rows"] = [{
        "ship_id": 7, "name": "TEST", "mmsi": "123456789", "ship_type": "货船", "flag": "CN",
        "fix_id": 77, "latitude": 26.4, "longitude": 56.4, "speed": 9.0,
        "recorded_at": START - timedelta(minutes=30), "source_batch_id": 1,
    }]
    http, _ = client
    response = http.get(f"{BASE}/snapshot", params={"at": START.isoformat()})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["area"]["is_default"] is True
    assert body["summary"]["in_area_count"] == 1
    assert body["ships"][0]["ship_id"] == 7
    assert body["ships"][0]["age_seconds"] == 1800.0


def test_compare_contract(client, stub):
    # A 窗命中第 1 条报位所在访问，B 窗命中第 2 条：两期各 1 艘
    stub["rows"] = [_visit_row(1, START), _visit_row(2, START + timedelta(days=1))]
    http, _ = client
    response = http.get(f"{BASE}/compare", params={
        "start_a": START.isoformat(), "end_a": END.isoformat(),
        "start_b": (START + timedelta(days=1)).isoformat(),
        "end_b": (START + timedelta(days=2)).isoformat(),
    })
    assert response.status_code == 200
    body = response.json()
    assert body["comparability"]["equal_length"] is True
    metrics = {item["key"]: item for item in body["metrics"]}
    assert metrics["ships_observed"]["a"] == 1
    assert metrics["ships_observed"]["b"] == 1
    assert metrics["ships_observed"]["delta"] == 0
    assert metrics["ships_observed"]["change_rate"] == 0.0
    assert body["windows"]["a"]["days"] == 1 and body["windows"]["b"]["days"] == 1
    assert body["comparability"]["warnings"] == []


def test_resolve_area_accepts_custom_rectangle(client):
    """圈选矩形：结构校验通过后回显 area_id=custom 与四个边界（与查询同一套规则）。"""
    http, _ = client
    response = http.post(f"{BASE}/resolve-area", json={
        "west": 56.0, "south": 26.0, "east": 56.9, "north": 26.8,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["area"]["area_id"] == "custom"
    assert body["area"]["is_default"] is False
    assert body["area"]["bounds"] == {"south": 26.0, "west": 56.0, "north": 26.8, "east": 56.9}
    assert body["area"]["span_deg"] == {"lat": 0.8, "lon": 0.9}
    assert "半开" in body["message"]
    assert body["limitations"]


def test_resolve_area_rejects_invalid_rectangles(client):
    """无效、跨 180° 与超跨度矩形在这里就拒绝，不留给后续查询。"""
    http, _ = client
    for payload, expected in (
        ({"west": 57.5, "south": 25.8, "east": 55.8, "north": 27.1}, "west < east"),
        ({"west": 170.0, "south": 20.0, "east": -170.0, "north": 24.0}, "west < east"),
        ({"west": 50.0, "south": 20.0, "east": 61.0, "north": 24.0}, "跨度"),
        ({"west": 55.8, "south": 27.1, "east": 57.1, "north": 25.8}, "south < north"),
    ):
        response = http.post(f"{BASE}/resolve-area", json=payload)
        assert response.status_code == 422, payload
        detail = response.json()["detail"]
        assert detail["code"] == "INVALID_REQUEST"
        assert expected in detail["message"]
        assert detail["request_id"]


def test_resolve_area_missing_field_uses_validation_handler(client):
    http, _ = client
    response = http.post(f"{BASE}/resolve-area", json={"west": 56.0, "south": 26.0})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_REQUEST"
    assert "request_id" in detail


def test_ship_types_catalog_contract(client, monkeypatch):
    """船型目录来自 ships 真实分布：空值/未知映射到保留值，计数之和等于总数。"""
    rows = [("货船", 5), ("未知", 2), ("", 2), ("__missing__", 1), ("油轮", 1)]

    class _Result:
        def fetchall(self):
            return rows

    class _Session:
        def execute(self, *args, **kwargs):
            return _Result()

    http, _ = client
    main_app.dependency_overrides[get_db] = lambda: _Session()
    try:
        response = http.get(f"{BASE}/ship-types")
    finally:
        main_app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["source"] == params.SOURCE
    assert body["total_ships"] == 11
    assert body["count"] == 4
    values = {item["value"]: item for item in body["ship_types"]}
    assert values["__missing__"]["count"] == 3
    assert sorted(values["__missing__"]["raw_values"]) == ["", "__missing__"]
    assert values["__unknown__"]["raw_values"] == ["未知"]
    assert values["__unknown__"]["label"] == "未知"
    assert sum(item["count"] for item in body["ship_types"]) == body["total_ships"]
    assert {item["value"] for item in body["reserved"]} == {"__missing__", "__unknown__"}
    assert body["limitations"]


def test_ship_types_catalog_empty_table_is_valid_zero(client):
    class _Result:
        def fetchall(self):
            return []

    class _Session:
        def execute(self, *args, **kwargs):
            return _Result()

    http, _ = client
    main_app.dependency_overrides[get_db] = lambda: _Session()
    try:
        response = http.get(f"{BASE}/ship-types")
    finally:
        main_app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_data"
    assert body["ship_types"] == [] and body["total_ships"] == 0

