-- P2 event-ship link layer (docs/mobility_capability_plan.md section 2.2).
-- Source tables are never modified; this file only creates the derived link table.
-- link_type semantics (red lines):
--   mentioned = text evidence from events.mentioned_vessels (real-news vessels);
--     ship_id stays NULL — identity with any ship in this database is NOT asserted.
--   observed = spatio-temporal proximity computed on simulated tracks only;
--     always a teaching demo, never real-world causality.
CREATE TABLE IF NOT EXISTS event_ship_links (
    id bigserial PRIMARY KEY,
    event_id bigint NOT NULL REFERENCES events(id),
    ship_id bigint REFERENCES ships(id),
    link_type varchar(16) NOT NULL CHECK (link_type IN ('mentioned', 'observed')),
    vessel_name text,
    confidence double precision,
    evidence jsonb NOT NULL,
    built_at timestamptz NOT NULL DEFAULT now(),
    CHECK (link_type = 'mentioned' OR ship_id IS NOT NULL),
    CHECK (link_type = 'observed' OR confidence IS NULL)
);
CREATE INDEX IF NOT EXISTS event_ship_links_event_idx ON event_ship_links(event_id);
CREATE INDEX IF NOT EXISTS event_ship_links_ship_idx ON event_ship_links(ship_id)
    WHERE ship_id IS NOT NULL;

COMMENT ON TABLE event_ship_links IS
'P2 derived links. mentioned: real-news vessel names from events.mentioned_vessels, ship_id NULL (no identity asserted). observed: simulation-only spatio-temporal proximity, teaching demo, not real causality. Rebuild via backend/build_event_ship_links.py.';
