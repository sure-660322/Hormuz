-- Keep existing records; supplier fields stay NULL until data is supplied.
BEGIN;
ALTER TABLE ships ALTER COLUMN flag DROP NOT NULL;
ALTER TABLE ships
    ADD COLUMN IF NOT EXISTS length_m double precision,
    ADD COLUMN IF NOT EXISTS width_m double precision;

ALTER TABLE ship_positions
    ADD COLUMN IF NOT EXISTS unix_time bigint,
    ADD COLUMN IF NOT EXISTS nav_status varchar(50),
    ADD COLUMN IF NOT EXISTS rot double precision,
    ADD COLUMN IF NOT EXISTS draught_m double precision,
    ADD COLUMN IF NOT EXISTS destination varchar(255),
    ADD COLUMN IF NOT EXISTS ais_type varchar(50),
    ADD COLUMN IF NOT EXISTS data_source varchar(50) NOT NULL DEFAULT 'unknown';

-- This project's existing baseline is teaching simulation data.
UPDATE ship_positions SET data_source = 'simulation' WHERE data_source = 'unknown';
COMMENT ON COLUMN ships.ship_type IS 'Chinese ship type';
COMMENT ON COLUMN ship_positions.nav_status IS 'Chinese navigation status supplied with the position';
COMMENT ON COLUMN ship_positions.unix_time IS 'Supplier Unix timestamp in seconds; derive recorded_at on import';
COMMENT ON COLUMN ship_positions.rot IS 'Supplier ROT value; confirm encoding and units before interpretation';
COMMENT ON COLUMN ship_positions.data_source IS 'Data provider: simulation, shipxy, or unknown';
COMMIT;
