#!/usr/bin/env bash
# Instala dependências, WireGuard, firewall e sobe Caddy (e cloudflared no modo tunnel).
# Uso: sudo ./scripts/setup.sh tunnel|public
set -euo pipefail

MODE="${1:-}"
case "$MODE" in
tunnel | public) ;;
*)
	echo "uso: sudo ./scripts/setup.sh tunnel|public" >&2
	exit 1
	;;
esac

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ $EUID -ne 0 ]]; then
	echo "ERRO: rode com sudo." >&2
	exit 1
fi

if [[ ! -f .env ]]; then
	echo "ERRO: cp .env.example .env e edite antes." >&2
	exit 1
fi

# shellcheck disable=SC1091
set -a
. ./.env
set +a

: "${DOMAIN:?defina DOMAIN no .env}"
: "${ACME_EMAIL:?defina ACME_EMAIL no .env}"
: "${VPS_PUBLIC_IP:?defina VPS_PUBLIC_IP no .env}"
: "${WG_PORT:=51820}"

echo "==> Instalando dependências (Ubuntu/Debian)"
apt-get update
apt-get install -y wireguard-tools ufw curl ca-certificates

if ! command -v docker >/dev/null 2>&1; then
	echo "==> Instalando Docker"
	curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
	echo "ERRO: Docker Compose plugin não encontrado." >&2
	exit 1
fi

if [[ ! -f wireguard/generated/wg0.conf.vps ]]; then
	echo "==> Gerando chaves/configs WireGuard"
	./scripts/gen-wg-keys.sh
fi

echo "==> Instalando WireGuard"
install -d -m 700 /etc/wireguard
if [[ -f /etc/wireguard/wg0.conf && "${FORCE:-0}" != "1" ]]; then
	echo "AVISO: /etc/wireguard/wg0.conf já existe; mantendo. Use FORCE=1 para sobrescrever." >&2
else
	install -m 600 -o root -g root wireguard/generated/wg0.conf.vps /etc/wireguard/wg0.conf
fi
systemctl enable wg-quick@wg0
systemctl restart wg-quick@wg0

echo "==> Firewall (UFW)"
ufw allow 22/tcp
ufw allow "${WG_PORT}"/udp
if [[ "$MODE" == "public" ]]; then
	ufw allow 80/tcp
	ufw allow 443/tcp
fi
ufw --force enable

echo "==> Subindo Caddy (${MODE})"
if [[ "$MODE" == "tunnel" && -z "${TUNNEL_TOKEN:-}" ]]; then
	echo "AVISO: TUNNEL_TOKEN vazio; o Caddy sobe, mas o cloudflared não conecta." >&2
fi
docker compose -f "docker-compose.${MODE}.yml" up -d

if [[ -n "${SUDO_USER:-}" ]]; then
	chown -R "${SUDO_USER}:$(id -gn "${SUDO_USER}")" wireguard/generated 2>/dev/null || true
fi

cat <<EOF

==> Pronto.

VPS (Oracle):
  WireGuard: $(wg show wg0 2>/dev/null | head -n 1 || true)
  Caddy:     docker compose -f docker-compose.${MODE}.yml ps

Pi:
  copie wireguard/generated/wg0.conf.pi e rode lá:
    sudo ./scripts/install-pi-wg.sh wg0.conf.pi

Cloudflare:
  tunnel: public hostname jellyfin.${DOMAIN} -> http://caddy:8080
  public: A jellyfin.${DOMAIN} -> ${VPS_PUBLIC_IP} (DNS only) e libere 80/443

Valide com:
  ./scripts/check.sh ${MODE}
EOF
