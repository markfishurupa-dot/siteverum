#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
config="$root/deploy/.env"
compose="$root/deploy/compose.yaml"
trap 'echo "SiteVerum setup failed. Check Docker and run docker compose -f deploy/compose.yaml logs." >&2' ERR
command -v docker >/dev/null || { echo 'Install Docker and the Compose plugin first.' >&2; exit 1; }
command -v openssl >/dev/null || { echo 'Install OpenSSL to generate credentials.' >&2; exit 1; }
docker compose version >/dev/null
docker info >/dev/null
if [[ ! -e "$config" ]]; then
  database=$(openssl rand -hex 32)
  administrator=$(openssl rand -hex 32)
  (umask 077; set -o noclobber; printf 'SV_DB_PASSWORD=%s\nSV_ADMIN_PASSWORD=%s\n' "$database" "$administrator" > "$config")
fi
docker compose -f "$compose" up -d --build --wait
address=$(docker compose -f "$compose" port api 8000 | head -n 1)
echo "SiteVerum is running at http://$address/."
echo "Sign in as admin using SV_ADMIN_PASSWORD in $config. Keep this file private and preserve it."
