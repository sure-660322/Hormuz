CREATE INDEX IF NOT EXISTS idx_events_location
ON events
USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_ship_positions_location
ON ship_positions
USING GIST (location);