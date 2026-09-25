-- Real AIS import fields. Apply to an existing database only after a backup and
-- after validating this migration in a separate test database.
ALTER TABLE ships ALTER COLUMN mmsi TYPE varchar(10);
ALTER TABLE ships ALTER COLUMN name DROP NOT NULL;
ALTER TABLE ships ALTER COLUMN ship_type DROP NOT NULL;
ALTER TABLE ships ADD COLUMN IF NOT EXISTS ship_type_cn_raw varchar(100);
ALTER TABLE ships ADD COLUMN IF NOT EXISTS dwt_t double precision;

ALTER TABLE ship_positions ADD COLUMN IF NOT EXISTS eta_text varchar(32);

CREATE TABLE IF NOT EXISTS ais_import_batches (
    id bigserial PRIMARY KEY,
    source_file text NOT NULL,
    source_sha256 char(64) NOT NULL UNIQUE,
    source_day date NOT NULL,
    data_source varchar(50) NOT NULL,
    file_size_bytes bigint NOT NULL,
    expected_rows bigint NOT NULL,
    inserted_rows bigint NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE ship_positions
    ADD COLUMN IF NOT EXISTS source_batch_id bigint REFERENCES ais_import_batches(id);
ALTER TABLE ship_positions ADD COLUMN IF NOT EXISTS source_row integer;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ship_positions_source_batch_id_fkey') THEN
        ALTER TABLE ship_positions ADD CONSTRAINT ship_positions_source_batch_id_fkey
            FOREIGN KEY (source_batch_id) REFERENCES ais_import_batches(id);
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS idx_ship_positions_source_row
    ON ship_positions (source_batch_id, source_row);
