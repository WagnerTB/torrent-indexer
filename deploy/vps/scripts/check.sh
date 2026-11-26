#!/usr/bin/env bash
# Validação rápida no VPS. Uso: ./scripts/check.sh tunnel|public
set -euo pipefail

MODE="${1:-tunnel}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
	echo "ERRO: .env ausente." >&2
	exit 1
fi

# shellcheck disable=SC1091
set -a
. ./.env
set +a

PI_WG_IP="${PI_WG_IP:-10.8.0.2}"

echo "== WireGuard"
wg show || true

echo
echo "== Ping Pi (${PI_WG_IP})"
ping -c1 -W2 "$PI_WG_IP" || true

echo
echo "== Jellyfin via WireGuard"
curl -fsS --max-time 5 "http://${PI_WG_IP}:8096/health" && echo || true

echo
echo "== Containers"
docker compose -f "docker-compose.${MODE}.yml" ps || true

echo
echo "== HTTPS público"
curl -sSI --max-time 10 "https://jellyfin.${DOMAIN}" | head -n 5 || true

if [[ "$MODE" == "tunnel" ]]; then
	echo
	echo "== cloudflared (últimas linhas)"
	docker compose -f docker-compose.tunnel.yml logs --tail=20 cloudflared || true
fi

echo
echo "Lembrete Jellyfin: Dashboard -> Networking -> Known proxies: 10.8.0.1, 172.18.0.1, 127.0.0.1"
