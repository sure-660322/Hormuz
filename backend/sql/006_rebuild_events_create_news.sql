-- Run through backend.migrate_real_news: backup and transaction required.
DROP TABLE IF EXISTS public.news;
DROP TABLE IF EXISTS public.events;

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
