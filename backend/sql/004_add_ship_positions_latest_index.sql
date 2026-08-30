CREATE INDEX IF NOT EXISTS idx_ship_positions_ship_recorded_at
ON ship_positions (ship_id, recorded_at DESC, id DESC);