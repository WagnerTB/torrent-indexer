#!/usr/bin/env bash
# Rollback: para containers, WireGuard e remove regras 80/443/51820 do UFW.
# Preserva configs e volumes. Uso: sudo ./scripts/teardown.sh tunnel|public
set -euo pipefail

MODE="${1:-tunnel}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ $EUID -ne 0 ]]; then
	echo "ERRO: rode com sudo." >&2
	exit 1
fi

WG_PORT="${WG_PORT:-51820}"
if [[ -f .env ]]; then
	# shellcheck disable=SC1091
	set -a
	. ./.env
	set +a
	WG_PORT="${WG_PORT:-51820}"
fi

docker compose -f "docker-compose.${MODE}.yml" down || true
systemctl disable --now wg-quick@wg0 || true

ufw delete allow 80/tcp || true
ufw delete allow 443/tcp || true
ufw delete allow "${WG_PORT}"/udp || true

echo "Parado. Configs preservadas em /etc/wireguard e no diretório do compose."
