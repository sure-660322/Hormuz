ALTER TABLE ship_positions
ADD COLUMN IF NOT EXISTS location geography(Point,4326)
GENERATED ALWAYS AS (
    ST_SetSRID(
        ST_MakePoint(longitude,latitude),
        4326
    )::geography
)STORED;