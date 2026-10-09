-- 017: controlled analytical snapshot tables for the restricted SQL agent
-- (catalog v3, issue #48). These are ordinary tables in schema agent_data,
-- owned by agent_view_owner and populated ONLY by the reviewed builder script
-- scripts/build_agent_analysis_snapshots.py (which calls the deterministic
-- business services, so snapshot rows are service output, not a SQL rewrite of
-- the analysis state machines).
--
-- agent_reader keeps SELECT-only. DML is granted to pg_database_owner (the
-- application role) so the builder can refresh snapshots in one transaction;
-- TEMP stays revoked and no function is created in agent_data (the executor
-- attestation requires function_inventory = 0).
--
-- Refresh/invalidation rule: snapshots never auto-refresh. After any source
-- position change (re-import, batch add/remove), re-run the builder script
-- explicitly -- same project rule as the MobilityDB derived layer. A failed
-- build rolls back the whole transaction and leaves the previous snapshot.
--
-- Run only as a reviewed database administration identity, first in an
-- isolated test database. With psql:
--   psql -v ON_ERROR_STOP=1 -d <database> -f 017_agent_analysis_snapshots.sql
-- Requires 016 (roles, schema agent_data, catalog v2 views) to be present.

BEGIN;

-- TimescaleDB's DDL event triggers touch _timescaledb_catalog during
-- CREATE TABLE, which SET LOCAL ROLE agent_view_owner cannot reach; tables
-- are therefore created by the migration identity and ownership is then
-- transferred to agent_view_owner (same end state as 016's views).
GRANT USAGE, CREATE ON SCHEMA agent_data TO pg_database_owner;

-- 3.1 passage evidence (one row per side transition per daily detection window)
CREATE TABLE IF NOT EXISTS agent_data.v_passage_evidence (
    passage_key             text        NOT NULL,
    window_day              date        NOT NULL,
    window_start            timestamptz NOT NULL,
    window_end              timestamptz NOT NULL,
    ship_id                 bigint      NOT NULL,
    ship_name               text,
    ship_type               text,
    direction               text        NOT NULL,
    observed_completion_at  timestamptz NOT NULL,
    start_observed_at       timestamptz NOT NULL,
    start_fix_id            bigint      NOT NULL,
    completion_fix_id       bigint      NOT NULL,
    uncertain               boolean     NOT NULL,
    uncertain_reason        text,
    data_source             text        NOT NULL,
    schema_version          text        NOT NULL,
    built_at                timestamptz NOT NULL,
    PRIMARY KEY (passage_key)
);

-- 3.2 passage daily summary (per UTC day x direction, from the daily windows)
CREATE TABLE IF NOT EXISTS agent_data.v_passage_daily (
    day                       date        NOT NULL,
    direction                 text        NOT NULL,
    confirmed_passage_count   integer     NOT NULL,
    confirmed_unique_ships    integer     NOT NULL,
    uncertain_candidate_count integer     NOT NULL,
    schema_version            text        NOT NULL,
    built_at                  timestamptz NOT NULL,
    PRIMARY KEY (day, direction)
);

-- 3.3 area visit evidence (one row per visit, per registered analysis area)
CREATE TABLE IF NOT EXISTS agent_data.v_area_visit (
    area_id                 text        NOT NULL,
    area_version            text        NOT NULL,
    window_start            timestamptz NOT NULL,
    window_end              timestamptz NOT NULL,
    visit_key               text        NOT NULL,
    ship_id                 bigint      NOT NULL,
    ship_name               text,
    mmsi                    text,
    ship_type               text,
    prior_state             text        NOT NULL,
    status                  text        NOT NULL,
    flags                   text        NOT NULL,
    first_inside_at         timestamptz NOT NULL,
    last_inside_at          timestamptz NOT NULL,
    observed_seconds        numeric     NOT NULL,
    window_seconds          numeric     NOT NULL,
    unobserved_gap_seconds  numeric     NOT NULL,
    entry_observed          boolean     NOT NULL,
    entry_observed_at       timestamptz,
    entry_in_window         boolean     NOT NULL,
    exit_observed           boolean     NOT NULL,
    exit_observed_at        timestamptz,
    exit_in_window          boolean     NOT NULL,
    segment_count           integer     NOT NULL,
    fix_count               integer     NOT NULL,
    started_before_window   boolean     NOT NULL,
    algorithm_version       text        NOT NULL,
    built_at                timestamptz NOT NULL,
    PRIMARY KEY (area_id, visit_key)
);

-- 3.4 area daily summary (per area x UTC day)
CREATE TABLE IF NOT EXISTS agent_data.v_area_daily (
    area_id                 text        NOT NULL,
    area_version            text        NOT NULL,
    day                     date        NOT NULL,
    window_start            timestamptz NOT NULL,
    window_end              timestamptz NOT NULL,
    ships_observed          integer     NOT NULL,
    observed_entry_count    integer     NOT NULL,
    observed_exit_count     integer     NOT NULL,
    observed_ship_hours     numeric     NOT NULL,
    visits_touching_day     integer     NOT NULL,
    complete_visit_count    integer     NOT NULL,
    truncated_visit_count   integer     NOT NULL,
    interrupted_visit_count integer     NOT NULL,
    uncertain_visit_count   integer     NOT NULL,
    algorithm_version       text        NOT NULL,
    built_at                timestamptz NOT NULL,
    PRIMARY KEY (area_id, day)
);

-- 3.5 coverage / quality metadata (per UTC day over the detection corridor)
CREATE TABLE IF NOT EXISTS agent_data.v_data_coverage (
    day             date        NOT NULL,
    data_source     text        NOT NULL,
    position_count  bigint      NOT NULL,
    ship_count      integer     NOT NULL,
    first_fix_at    timestamptz,
    last_fix_at     timestamptz,
    coverage_scope  text        NOT NULL,
    built_at        timestamptz NOT NULL,
    PRIMARY KEY (day, data_source)
);

-- 3.6 snapshot manifest (meta table: attested by the executor, not queryable
-- by the model). One row per snapshot build.
CREATE TABLE IF NOT EXISTS agent_data.v_snapshot_manifest (
    snapshot_name          text        NOT NULL PRIMARY KEY,
    catalog_version        text        NOT NULL,
    window_start           timestamptz NOT NULL,
    window_end             timestamptz NOT NULL,
    area_ids               text        NOT NULL,
    passage_schema_version text        NOT NULL,
    area_algorithm_version text        NOT NULL,
    source_scope           text        NOT NULL,
    detail_truncated       boolean     NOT NULL,
    notes                  text        NOT NULL,
    built_at               timestamptz NOT NULL
);

COMMENT ON TABLE agent_data.v_passage_evidence IS
'Catalog v3 snapshot: one row per gate side transition from query_strait_passages over daily 24h detection windows; observed_completion_at is the first fix on the completion side, not the exact crossing moment.';
COMMENT ON TABLE agent_data.v_passage_daily IS
'Catalog v3 snapshot: per-UTC-day x direction counts; daily unique ships must not be summed as a larger-window dedup.';
COMMENT ON TABLE agent_data.v_area_visit IS
'Catalog v3 snapshot: one row per area visit from area_activity query_activity; snapshots only cover registered area_ids; missing-report intervals are not interpolated.';
COMMENT ON TABLE agent_data.v_area_daily IS
'Catalog v3 snapshot: per-area x UTC-day aggregates; daily unique ships must not be summed.';
COMMENT ON TABLE agent_data.v_data_coverage IS
'Catalog v3 snapshot: per-UTC-day corridor coverage/quality metadata; corridor subset is not full source coverage.';
COMMENT ON TABLE agent_data.v_snapshot_manifest IS
'Catalog v3 meta: snapshot build manifest; attested by the query_analytics executor, never exposed to the model.';

ALTER TABLE agent_data.v_passage_evidence OWNER TO agent_view_owner;
ALTER TABLE agent_data.v_passage_daily OWNER TO agent_view_owner;
ALTER TABLE agent_data.v_area_visit OWNER TO agent_view_owner;
ALTER TABLE agent_data.v_area_daily OWNER TO agent_view_owner;
ALTER TABLE agent_data.v_data_coverage OWNER TO agent_view_owner;
ALTER TABLE agent_data.v_snapshot_manifest OWNER TO agent_view_owner;

-- Keep the 016 invariant: future agent_data objects stay closed until a
-- reviewed migration grants them; only DML on the listed tables is delegated.
REVOKE CREATE ON SCHEMA agent_data FROM pg_database_owner;

-- Reader keeps SELECT-only on every snapshot object; no other privilege.
-- v_snapshot_manifest stays SELECTable by agent_reader on purpose: the
-- executor attests its rows before every execution. It is still unreachable
-- for the model, because the catalog does not list it and the policy
-- validator rejects any relation outside the catalog.
REVOKE ALL ON agent_data.v_passage_evidence,
    agent_data.v_passage_daily,
    agent_data.v_area_visit,
    agent_data.v_area_daily,
    agent_data.v_data_coverage,
    agent_data.v_snapshot_manifest
    FROM PUBLIC, agent_reader, agent_reader_login;
GRANT SELECT ON agent_data.v_passage_evidence,
    agent_data.v_passage_daily,
    agent_data.v_area_visit,
    agent_data.v_area_daily,
    agent_data.v_data_coverage,
    agent_data.v_snapshot_manifest
    TO agent_reader;

-- The builder refreshes snapshots through the application role (a member of
-- pg_database_owner). agent_view_owner itself is NOLOGIN and never connects.
GRANT INSERT, UPDATE, DELETE, TRUNCATE ON agent_data.v_passage_evidence,
    agent_data.v_passage_daily,
    agent_data.v_area_visit,
    agent_data.v_area_daily,
    agent_data.v_data_coverage,
    agent_data.v_snapshot_manifest
    TO pg_database_owner;

COMMIT;
