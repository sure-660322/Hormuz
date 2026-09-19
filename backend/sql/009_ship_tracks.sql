-- P0 generalized derived track layer (docs/mobility_capability_plan.md).
-- Source tables (ships / ship_positions / events / news) are never modified by this file;
-- only indexes are added and new derived tables are created.
-- MobilityDB 1.3 must already be installed. Track coordinates use UTM 40N (metres, EPSG:32640);
-- the SRID is recorded in track_build_manifest.params at build time.

-- 2.1 source-table indexes. The (ship_id, recorded_at) btree already exists as
-- idx_ship_positions_ship_recorded_at (008, DESC); BRIN suits append-only time series
-- and stays cheap at real-AIS scale.
CREATE INDEX IF NOT EXISTS idx_ship_positions_recorded_at_brin
ON ship_positions USING brin(recorded_at);
CREATE INDEX IF NOT EXISTS idx_ship_positions_data_source
ON ship_positions(data_source);

-- 2.2 generalized derived tracks; replaces mobility_demo_segments once accepted.
CREATE TABLE IF NOT EXISTS ship_tracks (
    ship_id bigint NOT NULL REFERENCES ships(id),
    segment_no integer NOT NULL,
    track tgeompoint NOT NULL,
    speed tfloat NOT NULL,
    point_count integer NOT NULL CHECK (point_count >= 2),
    t_start timestamptz NOT NULL,
    t_end timestamptz NOT NULL,
    data_source varchar(50) NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ship_id, segment_no)
);
CREATE INDEX IF NOT EXISTS ship_tracks_track_gist
ON ship_tracks USING gist(track);
CREATE INDEX IF NOT EXISTS ship_tracks_data_source
ON ship_tracks(data_source);

-- Rebuild manifest: one row per rebuild, written by backend/build_ship_tracks.py.
CREATE TABLE IF NOT EXISTS track_build_manifest (
    id bigserial PRIMARY KEY,
    table_name text NOT NULL,
    row_count bigint NOT NULL,
    sha256 text NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    params jsonb NOT NULL
);

COMMENT ON TABLE ship_tracks IS
'Generalized derived tracks (P0): per ship, linear tgeompoint in EPSG:32640 with step-interpolated tfloat speed; segments break on gap > gap_minutes (manifest) or data_source change. Rebuild explicitly via backend/build_ship_tracks.py after source changes.';
