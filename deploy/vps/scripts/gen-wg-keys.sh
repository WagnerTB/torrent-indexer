#!/usr/bin/env bash
# Gera os pares de chaves WireGuard e renderiza as configs do VPS e do Pi.
# Rodar em deploy/vps (no VPS ou no Pi, tanto faz), depois de criar o .env.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env ]]; then
	echo "ERRO: crie o .env a partir de .env.example antes." >&2
	exit 1
fi

# shellcheck disable=SC1091
set -a
. ./.env
set +a

: "${VPS_PUBLIC_IP:?defina VPS_PUBLIC_IP no .env}"
: "${VPS_WG_IP:=10.8.0.1}"
: "${PI_WG_IP:=10.8.0.2}"
: "${WG_PORT:=51820}"

if [[ "$VPS_PUBLIC_IP" == "203.0.113.10" || -z "$VPS_PUBLIC_IP" ]]; then
	echo "ERRO: troque VPS_PUBLIC_IP no .env pelo IP público da Oracle." >&2
	exit 1
fi

if ! command -v wg >/dev/null 2>&1; then
	echo "ERRO: instale wireguard-tools (apt install wireguard-tools)." >&2
	exit 1
fi

umask 077
mkdir -p wireguard/generated

VPS_PRIVATE="$(wg genkey)"
VPS_PUBLIC="$(printf '%s' "$VPS_PRIVATE" | wg pubkey)"
PI_PRIVATE="$(wg genkey)"
PI_PUBLIC="$(printf '%s' "$PI_PRIVATE" | wg pubkey)"
PSK="$(wg genpsk)"
WG_SUBNET="${VPS_WG_IP%.*}.0/24"

render() {
	local src="$1" dst="$2"
	sed \
		-e "s|__VPS_WG_IP__|${VPS_WG_IP}|g" \
		-e "s|__PI_WG_IP__|${PI_WG_IP}|g" \
		-e "s|__WG_PORT__|${WG_PORT}|g" \
		-e "s|__VPS_PUBLIC_IP__|${VPS_PUBLIC_IP}|g" \
		-e "s|__WG_SUBNET__|${WG_SUBNET}|g" \
		-e "s|__VPS_PRIVATE_KEY__|${VPS_PRIVATE}|g" \
		-e "s|__VPS_PUBLIC_KEY__|${VPS_PUBLIC}|g" \
		-e "s|__PI_PRIVATE_KEY__|${PI_PRIVATE}|g" \
		-e "s|__PI_PUBLIC_KEY__|${PI_PUBLIC}|g" \
		-e "s|__PSK__|${PSK}|g" \
		"$src" >"$dst"
}

render wireguard/wg0.conf.vps.example wireguard/generated/wg0.conf.vps
render wireguard/wg0.conf.pi.example wireguard/generated/wg0.conf.pi
chmod 600 wireguard/generated/wg0.conf.vps wireguard/generated/wg0.conf.pi

cat <<EOF

WireGuard gerado.

VPS (Oracle):
  config:     wireguard/generated/wg0.conf.vps
  public key: ${VPS_PUBLIC}

Pi:
  config:     wireguard/generated/wg0.conf.pi
  public key: ${PI_PUBLIC}

Próximos passos:
  VPS: sudo ./scripts/setup.sh tunnel|public
  Pi:  copie wg0.conf.pi e rode sudo ./scripts/install-pi-wg.sh wg0.conf.pi

Não comite wireguard/generated/ (já está no .gitignore).
EOF
