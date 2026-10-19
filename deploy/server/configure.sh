#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
command -v openssl >/dev/null
docker compose version >/dev/null
umask 077
mkdir -p deploy/server/config
if [[ -e .env.server || -e deploy/server/config/htpasswd ]]; then
    echo 'Configuration already exists; edit .env.server or manage deploy/server/config/htpasswd explicitly.' >&2
    exit 1
fi
read -r -p 'Website username [team]: ' username
username=${username:-team}
[[ "$username" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Use letters, digits, _ or -.' >&2; exit 1; }
read -r -s -p 'Website password (at least 12 characters): ' password
echo
[[ ${#password} -ge 12 ]] || { echo 'Password is too short.' >&2; exit 1; }
read -r -s -p 'Repeat website password: ' confirmation
echo
[[ "$password" == "$confirmation" ]] || { echo 'Passwords differ.' >&2; exit 1; }
{
    printf '%s:' "$username"
    printf '%s' "$password" | openssl passwd -6 -stdin
} > deploy/server/config/htpasswd
chmod 644 deploy/server/config/htpasswd
{
    printf 'DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'APP_DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'BIND_IP=127.0.0.1\nHTTP_PORT=8088\n'
    printf 'DEEPSEEK_API_KEY=\nDEEPSEEK_BASE_URL=\nDEEPSEEK_MODEL=\n'
} > .env.server
unset password confirmation
echo 'Created .env.server and deploy/server/config/htpasswd. Configure HTTPS proxy or SSH tunnel before sharing.'
