-- P3 dwell (anchor/wait) derived layer (docs/mobility_capability_plan.md section 2.2/7.3).
-- Source tables are never modified; this file only creates the derived table + indexes.
-- Rows are identified set-based in the database from ship_positions (speed-class runs,
-- gap break, then duration / displacement-radius filters); thresholds are snapshotted
-- into track_build_manifest.params by backend/build_ship_dwell.py.
-- kind semantics:
--   at_anchor   low-speed run (speed < anchor_speed_kn), displacement radius small
--   drift       low-speed run, displacement radius large (moving while slow)
--   slow_transit mid-speed run (anchor_speed_kn <= speed < transit_speed_kn), long duration
-- All values are teaching-simulation observations, not real AIS anchoring ground truth.
CREATE TABLE IF NOT EXISTS ship_dwell (
    id bigserial PRIMARY KEY,
    ship_id bigint NOT NULL REFERENCES ships(id),
    dwell_no integer NOT NULL,
    kind varchar(16) NOT NULL CHECK (kind IN ('at_anchor', 'drift', 'slow_transit')),
    enter_at timestamptz NOT NULL,
    leave_at timestamptz NOT NULL,
    duration_min double precision NOT NULL CHECK (duration_min > 0),
    geom geometry(Point, 4326) NOT NULL,
    displacement_radius_m double precision NOT NULL,
    max_speed_kn double precision NOT NULL,
    point_count integer NOT NULL CHECK (point_count >= 2),
    data_source varchar(50) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (ship_id, dwell_no)
);
CREATE INDEX IF NOT EXISTS ship_dwell_geom_gist ON ship_dwell USING gist(geom);
CREATE INDEX IF NOT EXISTS ship_dwell_ship_idx ON ship_dwell(ship_id);
CREATE INDEX IF NOT EXISTS ship_dwell_kind_idx ON ship_dwell(kind);

COMMENT ON TABLE ship_dwell IS
'P3 derived dwell intervals: speed-class runs from ship_positions (gap break at manifest gap_minutes), filtered by duration and displacement-radius thresholds (snapshot in track_build_manifest). Teaching simulation, not real AIS ground truth. Rebuild via backend/build_ship_dwell.py.';
