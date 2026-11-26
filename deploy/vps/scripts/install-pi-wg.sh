#!/usr/bin/env bash
# Roda no Pi: instala o cliente WireGuard e ativa a config gerada no VPS.
# Uso: sudo ./install-pi-wg.sh wg0.conf.pi
set -euo pipefail

CONFIG="${1:-}"
if [[ -z "$CONFIG" || ! -f "$CONFIG" ]]; then
	echo "uso: sudo ./install-pi-wg.sh wg0.conf.pi" >&2
	exit 1
fi

if [[ $EUID -ne 0 ]]; then
	echo "ERRO: rode com sudo." >&2
	exit 1
fi

echo "==> Instalando WireGuard no Pi"
apt-get update
apt-get install -y wireguard

echo "==> Instalando config"
install -d -m 700 /etc/wireguard
install -m 600 -o root -g root "$CONFIG" /etc/wireguard/wg0.conf
systemctl enable wg-quick@wg0
systemctl restart wg-quick@wg0

echo "==> Status"
wg show wg0 || true
echo
echo "Teste no Pi:  ping -c3 10.8.0.1"
echo "Teste no VPS: curl -fsS http://10.8.0.2:8096/health"
