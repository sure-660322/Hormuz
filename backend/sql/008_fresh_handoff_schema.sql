-- Fresh empty database only. Use backend.handoff import (transaction + empty-table guard).

CREATE TABLE ships (
	id BIGSERIAL NOT NULL, 
	mmsi VARCHAR(9) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	ship_type VARCHAR(50) NOT NULL, 
	flag VARCHAR(50), 
	imo VARCHAR(20), 
	callsign VARCHAR(20), 
	length_m DOUBLE PRECISION, 
	width_m DOUBLE PRECISION, 
	PRIMARY KEY (id), 
	UNIQUE (mmsi)
)

;

CREATE TABLE ship_positions (
	id BIGSERIAL NOT NULL, 
	ship_id BIGINT NOT NULL, 
	latitude DOUBLE PRECISION NOT NULL, 
	longitude DOUBLE PRECISION NOT NULL, 
	speed DOUBLE PRECISION NOT NULL, 
	course DOUBLE PRECISION NOT NULL, 
	heading DOUBLE PRECISION, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	unix_time BIGINT, 
	nav_status VARCHAR(50), 
	rot DOUBLE PRECISION, 
	draught_m DOUBLE PRECISION, 
	destination VARCHAR(255), 
	ais_type VARCHAR(50), 
	data_source VARCHAR(50) DEFAULT 'unknown' NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ship_id) REFERENCES ships (id)
)

;

CREATE TABLE events (
	id BIGSERIAL NOT NULL, 
	event_id VARCHAR(20) NOT NULL, 
	event_key VARCHAR(64) NOT NULL, 
	title_zh TEXT NOT NULL, 
	summary_zh TEXT NOT NULL, 
	event_type VARCHAR(32) NOT NULL, 
	event_datetime TIMESTAMP WITH TIME ZONE, 
	event_time_text TEXT, 
	event_location_text TEXT, 
	event_region VARCHAR(32), 
	event_lat DOUBLE PRECISION, 
	event_lng DOUBLE PRECISION, 
	mentioned_vessels JSONB NOT NULL, 
	image_url TEXT, 
	image_path VARCHAR, 
	event_points JSONB, 
	geo_method VARCHAR(32), 
	geo_note TEXT, 
	coverage_count INTEGER NOT NULL, 
	perspectives JSONB NOT NULL, 
	story_ids JSONB NOT NULL, 
	publish_date_min DATE, 
	publish_date_max DATE, 
	PRIMARY KEY (id), 
	UNIQUE (event_id), 
	UNIQUE (event_key)
)

;

CREATE TABLE news (
	id BIGSERIAL NOT NULL, 
	story_id VARCHAR(64) NOT NULL, 
	source_id BIGINT, 
	title TEXT NOT NULL, 
	url TEXT NOT NULL, 
	canonical_url TEXT NOT NULL, 
	publish_date DATE NOT NULL, 
	language VARCHAR(8) NOT NULL, 
	media_name VARCHAR(64) NOT NULL, 
	perspective VARCHAR(32) NOT NULL, 
	description_en TEXT, 
	enrich_status SMALLINT NOT NULL, 
	title_zh TEXT NOT NULL, 
	summary_zh TEXT NOT NULL, 
	event_type VARCHAR(32) NOT NULL, 
	event_datetime TIMESTAMP WITH TIME ZONE, 
	event_time_text TEXT, 
	event_location_text TEXT, 
	event_region VARCHAR(32), 
	event_lat DOUBLE PRECISION, 
	event_lng DOUBLE PRECISION, 
	mentioned_vessels JSONB NOT NULL, 
	image_url TEXT, 
	image_path VARCHAR, 
	relevant BOOLEAN NOT NULL, 
	event_id BIGINT, 
	PRIMARY KEY (id), 
	UNIQUE (story_id), 
	UNIQUE (canonical_url), 
	FOREIGN KEY(event_id) REFERENCES events (id)
)

;
ALTER TABLE ship_positions
ADD COLUMN IF NOT EXISTS location geography(Point,4326)
GENERATED ALWAYS AS (
    ST_SetSRID(
        ST_MakePoint(longitude,latitude),
        4326
    )::geography
)STORED;
CREATE INDEX idx_ship_positions_location ON ship_positions USING gist(location);
CREATE INDEX idx_ship_positions_ship_recorded_at ON ship_positions(ship_id, recorded_at DESC, id DESC);
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
