#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec docker compose -f compose.server.yaml --env-file "${HORMUZ_ENV_FILE:-.env.server}" "$@"
