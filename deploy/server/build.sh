#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
# Serial builds keep memory pressure lower on the 4 GB trial server.
bash dc.sh build api
bash dc.sh build web
