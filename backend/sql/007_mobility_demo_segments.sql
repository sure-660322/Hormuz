-- Derived pilot only; ships, ship_positions, events and news are never modified.
-- MobilityDB 1.3 must already be installed. Coordinates use UTM 40N (metres).
CREATE TABLE IF NOT EXISTS mobility_demo_segments (
    ship_id bigint NOT NULL REFERENCES ships(id),
    segment_no integer NOT NULL,
    track tgeompoint NOT NULL,
    point_count integer NOT NULL CHECK (point_count >= 2),
    built_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ship_id, segment_no)
);
CREATE INDEX IF NOT EXISTS mobility_demo_segments_track_gist
ON mobility_demo_segments USING gist(track);
COMMENT ON TABLE mobility_demo_segments IS
'Teaching simulation pilot: 10 selected ships, linear interpolation in EPSG:32640; gaps >90 minutes excluded. Rebuild explicitly after source changes.';
