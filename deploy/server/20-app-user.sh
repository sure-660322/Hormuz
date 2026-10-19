#!/bin/sh
set -eu
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE hormuz_app LOGIN PASSWORD %L', :'app_password') \gexec
ALTER ROLE hormuz_app SET default_transaction_read_only = on;
ALTER ROLE hormuz_app SET statement_timeout = '90s';
ALTER ROLE hormuz_app SET idle_in_transaction_session_timeout = '30s';
SQL
