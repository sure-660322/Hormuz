from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.agent.strait_passages import query_strait_passages

START = datetime(2026, 2, 28, 15, tzinfo=timezone.utc)


class _Mapped:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def one(self):
        return self.rows[0]

    def all(self):
        return self.rows


class _ReadOnlySession:
    def __init__(self, transitions=(), *, position_count=2, window_count=1):
        self.transitions = transitions
        self.position_count = position_count
        self.window_count = window_count
        self.calls = []

    def execute(self, query, params):
        sql = str(query)
        self.calls.append((sql, params))
        assert sql.lstrip().lower().startswith(("select", "with"))
        if "count(*) AS position_count" in sql:
            return _Mapped([{
                "position_count": self.position_count,
                "window_position_count": self.window_count,
                "coverage_start": START - timedelta(hours=2) if self.position_count else None,
                "coverage_end": START + timedelta(hours=1) if self.position_count else None,
            }])
        return _Mapped(self.transitions)


def _transition(ship_id, *, hours=2, end_lon=56.8, start_lon=56.1, left_corridor=False):
    return {
        "ship_id": ship_id, "name": f"ship {ship_id}",
        "side": "east", "previous_side": "west",
        "recorded_at": START + timedelta(minutes=30),
        "longitude": end_lon, "latitude": 26.5,
        "previous_at": START + timedelta(minutes=30) - timedelta(hours=hours),
        "previous_lon": start_lon, "previous_lat": 26.5,
        "left_corridor": left_corridor,
    }


def test_bounded_virtual_gates_and_uncertain_candidates():
    session = _ReadOnlySession([
        _transition(1), _transition(2, hours=7),
        _transition(3, hours=0), _transition(4, left_corridor=True),
    ])
    result = query_strait_passages(session, START, START + timedelta(hours=1))
    assert result.status == "partial"
    assert result.query_summary.passage_count == 1
    assert result.query_summary.uncertain_candidate_count == 3
    assert {x.uncertain_reason for x in result.uncertain_candidates} == {"long_gap", "jump", "left_corridor"}
    assert result.ships[0].ship_id == 1
    assert all(x.direction == "west_to_east" for x in result.evidence)
    assert len(session.calls) == 2
    for sql, params in session.calls:
        assert params["source"] == "nnu_ais"
        assert params["lookback_at"] == START - timedelta(hours=24)
        assert params["end_at"] == START + timedelta(hours=1)
        assert "p.recorded_at >= :lookback_at" in sql
        assert "p.latitude BETWEEN :lat_min AND :lat_max" in sql
        assert "p.longitude BETWEEN :west_approach AND :east_approach" in sql
    assert "lag(side)" in session.calls[1][0]
    assert session.calls[1][1]["candidate_limit"] == 5001


def test_no_gate_observation_is_not_zero_passages():
    result = query_strait_passages(
        _ReadOnlySession(position_count=0, window_count=0),
        START, START + timedelta(hours=1),
    )
    assert result.status == "no_data"
    assert result.query_summary.position_count == 0


def test_gate_scan_limit_rejects_without_truncating():
    session = _ReadOnlySession(position_count=1_000_001)
    with pytest.raises(ValueError, match="超过上限"):
        query_strait_passages(session, START, START + timedelta(hours=1))
    assert len(session.calls) == 1


def test_window_over_24_hours_rejected():
    with pytest.raises(ValueError, match="24 小时"):
        query_strait_passages(_ReadOnlySession(), START, START + timedelta(hours=25))


def test_ship_id_scopes_both_queries():
    session = _ReadOnlySession([_transition(7)])
    result = query_strait_passages(session, START, START + timedelta(hours=1), ship_id=7)
    assert result.query_summary.matched_ship_count == 1
    assert all(params["ship_id"] == 7 for _, params in session.calls)
    assert all("p.ship_id = :ship_id" in sql for sql, _ in session.calls)


def test_invalid_ship_id_rejected():
    with pytest.raises(ValueError, match="ship_id"):
        query_strait_passages(_ReadOnlySession(), START, START + timedelta(hours=1), ship_id=0)
