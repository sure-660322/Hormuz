"""Parser tests plus explicitly isolated Postgres import/API checks."""
import csv
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.case_ais import audit_csv
from backend.import_case_ais import import_case

HEADER = ["船名", "呼号", "IMO", "MMSI", "船舶类型", "航行状态", "船长", "船宽", "吃水", "船首向", "船迹向", "航速", "Lon", "Lat", "旋转角速度", "目的地", "ETA", "最后更新时间", "时间戳", "Lon_d", "Lat_d", "数据来源"]
ROW = ["CSCL ARCTIC OCEAN", "VROD9", "9695169", "477967700", "集装箱船", "锚泊", "400", "58", "11", "76", "1.5", "1", "54°20.626′E", "25°10.847′N", "0", "MYPKG", "04-06-08-00", "2026-03-27 00:01:33", "1774540893", "54.343762", "25.180788", "岸基"]


def source(tmp_path, rows):
    p = tmp_path / "case.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return p


def test_unquoted_destination_repair(tmp_path):
    row = ROW[:15] + ["CHINESE!AS", "SPAIN"] + ROW[16:]
    audit = audit_csv(source(tmp_path, [row]))
    assert audit["positions"][0]["destination"] == "CHINESE!AS,SPAIN"
    assert audit["repaired_rows"] == [2]
    assert audit["start_at"] == "2026-03-26T16:01:33+00:00"


@pytest.mark.parametrize("index,value", [(3,"123"),(17,"2026-03-27 01:01:33"),(19,"nan"),(20,"91")])
def test_invalid_identity_time_coordinate(tmp_path,index,value):
    row = ROW.copy(); row[index] = value
    with pytest.raises(ValueError): audit_csv(source(tmp_path,[row]))


def test_conflicting_second_quarantines_both(tmp_path):
    conflict = ROW.copy(); conflict[19] = "54.34"
    other = ROW.copy(); other[17] = "2026-03-27 00:01:34"; other[18] = "1774540894"
    audit = audit_csv(source(tmp_path,[ROW,conflict,other]))
    assert audit["quarantined_rows"] == [2,3]
    assert audit["accepted_rows"] == 1


def test_real_export():
    path = os.environ.get("HORMUZ_CASE_CSV")
    if not path: pytest.skip("Local source CSV is intentionally not committed")
    audit = audit_csv(Path(path))
    assert (audit["raw_rows"],audit["accepted_rows"]) == (11642,11640)
    assert len(audit["repaired_rows"]) == 56
    assert audit["quarantined_rows"] == [882,883]
    assert len(audit["gaps"]) == 4


def test_isolated_import_and_routes():
    database = os.environ.get("HORMUZ_CASE_TEST_DB")
    path = os.environ.get("HORMUZ_CASE_CSV")
    if not database or not path: pytest.skip("Requires explicit isolated test database and local CSV")
    assert database == "hormuz_arctic_case_test", "Never run write tests against the application database"
    from backend.app.database import DATABASE_URL, get_db
    from backend.app.main import app
    engine = create_engine(DATABASE_URL.set(database=database))
    with engine.connect() as conn:
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: db
        try:
            client = TestClient(app)
            assert client.get("/health").status_code == 200
            assert client.get("/docs").status_code == 200
            assert client.get("/cases/arctic-ocean").json()["ready"] is False
            audit = audit_csv(Path(path))
            result = import_case(conn,Path(path),audit)
            repeat = import_case(conn,Path(path),audit)
            assert repeat["state"] == "already_imported"
            case = client.get("/cases/arctic-ocean").json()
            assert case["ready"] and case["position_count"] == 11640
            assert len(case["stages"]) == 4
            assert client.get("/simulation/meta").json()["position_count"] == 0
            track = client.get(f"/ships/{result['ship_id']}/track-window",params={"from":"2026-03-28T00:00:00Z","to":"2026-03-29T00:00:00Z","bucket_seconds":120})
            assert track.status_code == 200 and track.json()["gaps"]
            assert client.get(f"/ships/{result['ship_id']}/track-window",params={"from":"2026-03-27T00:00:00Z","to":"2026-03-30T00:00:00Z"}).status_code == 422
            assert client.get(f"/ships/{result['ship_id']}/track-window",params={"from":"2100-01-01T00:00:00Z","to":"2100-01-02T00:00:00Z"}).json()["point_count"] == 0
        finally:
            app.dependency_overrides.clear()
            db.close()
            outer.rollback()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM ais_import_batches")) == 0
    from sqlalchemy.exc import IntegrityError
    bad = dict(audit)
    bad["positions"] = [dict(p) for p in audit["positions"][:2]]
    bad["positions"][1]["source_row"] = bad["positions"][0]["source_row"]
    with pytest.raises(IntegrityError):
        with engine.begin() as conn: import_case(conn,Path(path),bad)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM ais_import_batches")) == 0
        assert conn.scalar(text("SELECT count(*) FROM ship_positions")) == 0
