-- Retire the SQL-02 simulation-only ship view. 013 remains a historical
-- migration/fixture; it must not be replayed on the current real-AIS database.
-- This operation is idempotent and does not touch ships, positions, news,
-- events, the other two news views, or roles. Dependencies make it fail closed.

DO $retire$
DECLARE
    existing_kind "char";
BEGIN
    SELECT c.relkind INTO existing_kind
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'agent_data' AND c.relname = 'v_ships';

    IF existing_kind IS NOT NULL THEN
        IF existing_kind <> 'v' THEN
            RAISE EXCEPTION 'agent_data.v_ships exists but is not a view';
        END IF;
        EXECUTE 'DROP VIEW agent_data.v_ships RESTRICT';
    END IF;
END
$retire$;
