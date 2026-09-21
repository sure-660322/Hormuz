-- P4 encounter derived layer (docs/mobility_capability_plan.md section 2.2/7.4).
-- Source tables are never modified; this file only creates the derived table + indexes.
-- A row is one ship PAIR: candidate segment pairs from ship_tracks (same data_source,
-- time overlap, conservative spatial prefilter ST_DWithin on the projected
-- trajectories) are refined by dense synchronized sampling of both interpolated
-- tracks: min_distance_m is the minimum distance at instants sample_seconds apart
-- over the segment-pair overlap. Semantics are defined at segment-pair level; the
-- stored row aggregates qualifying segment pairs of the pair:
--   period          envelope [min overlap start, max overlap end] of qualifying pairs
--   overlap_minutes cumulative overlap minutes of qualifying segment pairs
--   closest_point   midpoint of the two ships at the sampled closest instant
-- Thresholds are snapshotted per row in params by backend/build_encounters.py.
-- Teaching-simulation analysis only; proximity is not interaction.
CREATE TABLE IF NOT EXISTS encounters (
    id bigserial PRIMARY KEY,
    ship_a_id bigint NOT NULL REFERENCES ships(id),
    ship_b_id bigint NOT NULL REFERENCES ships(id),
    period tstzspan NOT NULL,
    min_distance_m double precision NOT NULL CHECK (min_distance_m >= 0),
    closest_point geometry(Point, 4326),
    overlap_minutes double precision NOT NULL CHECK (overlap_minutes > 0),
    data_source varchar(50) NOT NULL,
    params jsonb NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ship_a_id < ship_b_id)
);
CREATE INDEX IF NOT EXISTS encounters_ship_a_idx ON encounters(ship_a_id);
CREATE INDEX IF NOT EXISTS encounters_ship_b_idx ON encounters(ship_b_id);
CREATE INDEX IF NOT EXISTS encounters_point_gist ON encounters USING gist(closest_point);

COMMENT ON TABLE encounters IS
'P4 derived encounters (one row per ship pair): min synchronized distance (nearestApproachDistance) over qualifying ship_tracks segment pairs; period is the envelope of qualifying overlaps, overlap_minutes cumulative. Thresholds in params. Teaching simulation, proximity is not interaction. Rebuild via backend/build_encounters.py.';
