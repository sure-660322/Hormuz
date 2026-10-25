"""Navigation values survive bucket sampling and gap endpoints for local case replay."""
from datetime import datetime, timedelta, timezone

from backend.app.routers.ships import get_ship_track_window


def test_sampled_case_reports_keep_navigation_values():
    start = datetime(2026, 3, 27, tzinfo=timezone.utc)
    rows = [
        dict(id=1, latitude=26, longitude=56, speed=8, course=90, heading=95, recorded_at=start),
        dict(id=2, latitude=26.1, longitude=56.1, speed=9, course=100, heading=None, recorded_at=start + timedelta(seconds=30)),
        dict(id=3, latitude=27, longitude=57, speed=12, course=110, heading=115, recorded_at=start + timedelta(hours=2)),
    ]

    class FakeDB:
        def get(self, model, ship_id):
            return object()

        def execute(self, statement, params):
            assert "course, heading" in str(statement)
            assert params["ship_id"] == 2
            return self

        def mappings(self):
            return self

        def all(self):
            return rows

    track = get_ship_track_window(2, start, start + timedelta(hours=3), 120, FakeDB())
    points = [point for segment in track["segments"] for point in segment["points"]]
    assert [point["id"] for point in points] == [1, 2, 3]
    assert [point["course"] for point in points] == [90, 100, 110]
    assert [point["heading"] for point in points] == [95, None, 115]
    assert points[1]["recorded_at"] == rows[1]["recorded_at"]
    assert len(track["gaps"]) == 1
