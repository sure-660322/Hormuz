#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test -f "${HORMUZ_ENV_FILE:-.env.server}"
test -s "${HORMUZ_AUTH_FILE:-deploy/server/config/htpasswd}"
docker compose -f compose.server.yaml --env-file "${HORMUZ_ENV_FILE:-.env.server}" up -d --wait
docker compose -f compose.server.yaml --env-file "${HORMUZ_ENV_FILE:-.env.server}" ps
