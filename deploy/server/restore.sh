#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test -f "${HORMUZ_ENV_FILE:-.env.server}"
data_root=${HORMUZ_DATA_ROOT:-deployment-data}
test -f "$data_root/database/application.dump"
test -f "$data_root/database/database-manifest.json"
(cd "$data_root/database" && sha256sum --check --quiet SHA256SUMS)
compose=(docker compose -f compose.server.yaml --env-file "${HORMUZ_ENV_FILE:-.env.server}")
"${compose[@]}" build api
"${compose[@]}" up -d --wait db
existing=$("${compose[@]}" exec -T db sh -c 'psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind='r' AND NOT EXISTS (
 SELECT FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e'
);
SQL
)
if [[ "$existing" != 0 ]]; then
    echo 'Refusing restore: application tables already exist. Existing data was preserved.' >&2
    exit 1
fi
"${compose[@]}" exec -T db sh -c 'exec pg_restore --exit-on-error --single-transaction --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB" /backup/application.dump'
"${compose[@]}" exec -T db sh -c 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
GRANT USAGE ON SCHEMA public TO hormuz_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO hormuz_app;
ANALYZE;
SQL
"${compose[@]}" run --rm --no-deps --entrypoint python api /app/deploy/verify_database.py
echo 'Database restored and row counts verified. Start application with: bash deploy/server/start.sh'
