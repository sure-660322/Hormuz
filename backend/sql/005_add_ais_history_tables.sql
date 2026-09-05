BEGIN;

CREATE TABLE IF NOT EXISTS ais_datasets (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT,
    source_version TEXT,
    source_sha256 CHAR(64) NOT NULL UNIQUE,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    record_count BIGINT NOT NULL DEFAULT 0,
    vessel_count BIGINT NOT NULL DEFAULT 0,
    start_at TIMESTAMPTZ,
    end_at TIMESTAMPTZ,
    coverage_note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ais_vessels (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES ais_datasets(id) ON DELETE CASCADE,
    mmsi TEXT NOT NULL,
    name TEXT,
    ship_type DOUBLE PRECISION,
    flag TEXT,
    destination TEXT,
    draught DOUBLE PRECISION,
    length DOUBLE PRECISION,
    width DOUBLE PRECISION,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    UNIQUE (dataset_id, mmsi)
);

CREATE TABLE IF NOT EXISTS ais_positions (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NOT NULL REFERENCES ais_datasets(id) ON DELETE CASCADE,
    vessel_id BIGINT NOT NULL REFERENCES ais_vessels(id) ON DELETE CASCADE,
    source_row_number BIGINT NOT NULL,
    mmsi TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    speed DOUBLE PRECISION,
    course DOUBLE PRECISION,
    heading DOUBLE PRECISION,
    ship_name TEXT,
    ship_type DOUBLE PRECISION,
    destination TEXT,
    draught DOUBLE PRECISION,
    length DOUBLE PRECISION,
    width DOUBLE PRECISION,
    flag TEXT,
    received_at TIMESTAMPTZ,
    location geography(Point, 4326)
        GENERATED ALWAYS AS (
            ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        ) STORED,
    UNIQUE (dataset_id, source_row_number)
);

CREATE INDEX IF NOT EXISTS ix_ais_vessels_dataset_mmsi
    ON ais_vessels (dataset_id, mmsi);

CREATE INDEX IF NOT EXISTS ix_ais_positions_dataset_time
    ON ais_positions (dataset_id, recorded_at, id);

CREATE INDEX IF NOT EXISTS ix_ais_positions_vessel_time
    ON ais_positions (vessel_id, recorded_at, id);

CREATE INDEX IF NOT EXISTS ix_ais_positions_location_gist
    ON ais_positions USING GIST (location);

COMMIT;
