#!/usr/bin/env sh
set -eu

DEFAULT_OUTPUT="/srv/PiMedia/docker/media-agent/state/pi-status.json"
OUTPUT="${PI_STATUS_FILE:-$DEFAULT_OUTPUT}"
ACTION="once"

usage() {
  cat <<'EOF'
Uso: pi-status-probe.sh [--once|--daemon|--install] [--output CAMINHO]

  --once      grava o status uma vez e sai (padrão)
  --daemon    grava o status a cada 2 segundos
  --install   instala este script em /usr/local/bin e cria o serviço systemd
  --output    caminho do JSON (padrão: /srv/PiMedia/docker/media-agent/state/pi-status.json)
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --once)
      ACTION="once"
      ;;
    --daemon)
      ACTION="daemon"
      ;;
    --install)
      ACTION="install"
      ;;
    --output)
      shift
      if [ "$#" -eq 0 ]; then
        echo "faltou o caminho após --output" >&2
        exit 2
      fi
      OUTPUT="$1"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "opção desconhecida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [ -n "${PI_STATUS_PENDING_FILE:-}" ]; then
  PENDING_FILE="$PI_STATUS_PENDING_FILE"
else
  PENDING_FILE="${OUTPUT}.pending"
fi

if [ -n "${PI_STATUS_CLEAR_FILE:-}" ]; then
  CLEAR_REQUEST="$PI_STATUS_CLEAR_FILE"
else
  CLEAR_REQUEST="${OUTPUT}.clear"
fi

json_number() {
  case "${1:-}" in
    ''|*[!0-9.eE+-]*)
      printf 'null'
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

json_throttle() {
  case "${1:-}" in
    '')
      printf 'null'
      ;;
    *)
      printf '"%s"' "$1"
      ;;
  esac
}

to_int() {
  case "${1:-}" in
    '')
      printf '0'
      ;;
    0x*|0X*)
      hex=${1#0x}
      hex=${hex#0X}
      case "$hex" in
        ''|*[!0-9a-fA-F]*)
          printf '0'
          ;;
        *)
          printf '%s' "$(( 0x$hex ))"
          ;;
      esac
      ;;
    *[!0-9]*)
      printf '0'
      ;;
    *)
      printf '%s' "$1"
      ;;
  esac
}

read_core_volts() {
  vcgencmd measure_volts core 2>/dev/null | sed -n 's/.*=\([0-9][0-9.]*\)V.*/\1/p' | head -n 1
}

read_temperature() {
  vcgencmd measure_temp 2>/dev/null | sed -n "s/.*=\([0-9][0-9.]*\)'C.*/\1/p" | head -n 1
}

read_throttled() {
  vcgencmd get_throttled 2>/dev/null | sed -n 's/.*=\(0x[0-9a-fA-F]*\).*/\1/p' | head -n 1
}

read_recent_throttle() {
  vcgencmd get_throttled 0x0F 2>/dev/null | sed -n 's/.*=\(0x[0-9a-fA-F]*\).*/\1/p' | head -n 1
}

read_pending() {
  if [ -f "$PENDING_FILE" ]; then
    value=$(cat "$PENDING_FILE" 2>/dev/null || true)
    case "$value" in
      0x*|0X*)
        printf '%s' "$value"
        ;;
      *)
        printf '0x0'
        ;;
    esac
  fi
}

process_clear_request() {
  if [ -f "$CLEAR_REQUEST" ]; then
    printf '0x0\n' > "$PENDING_FILE"
    rm -f "$CLEAR_REQUEST"
  fi
}

write_status() {
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  core=$(read_core_volts || true)
  temperature=$(read_temperature || true)
  throttled=$(read_throttled || true)
  recent=$(read_recent_throttle || true)
  [ -n "$throttled" ] || throttled="0x0"
  [ -n "$recent" ] || recent="0x0"
  pending=$(read_pending)
  if [ -z "$pending" ]; then
    pending=$(printf '0x%x' "$(( $(to_int "$throttled") & 983040 ))")
  fi
  pending_int=$(to_int "$pending")
  recent_int=$(to_int "$recent")
  pending_int=$((pending_int | (recent_int & 983040)))
  pending=$(printf '0x%x' "$pending_int")
  printf '%s\n' "$pending" > "$PENDING_FILE"
  directory=$(dirname "$OUTPUT")
  mkdir -p "$directory"
  temporary="${OUTPUT}.tmp.$$"
  printf '{"generatedAt":"%s","coreVolts":%s,"temperature":%s,"throttled":%s,"recentThrottled":%s,"pendingThrottled":%s}\n' \
    "$timestamp" \
    "$(json_number "$core")" \
    "$(json_number "$temperature")" \
    "$(json_throttle "$throttled")" \
    "$(json_throttle "$recent")" \
    "$(json_throttle "$pending")" > "$temporary"
  mv "$temporary" "$OUTPUT"
  chmod 0644 "$OUTPUT" 2>/dev/null || true
}

run_daemon() {
  while :; do
    process_clear_request
    write_status || true
    sleep 2
  done
}

install_probe() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "execute como root: sudo $0 --install" >&2
    exit 1
  fi
  if ! command -v vcgencmd >/dev/null 2>&1; then
    echo "aviso: vcgencmd não encontrado; voltagem/throttling ficará N/D" >&2
  fi
  self=$(readlink -f "$0" 2>/dev/null || printf '%s' "$0")
  target=/usr/local/bin/pi-status-probe
  if [ "$self" != "$target" ]; then
    install -D -m 0755 "$self" "$target"
  fi
  cat > /etc/systemd/system/pi-status-probe.service <<EOF
[Unit]
Description=Raspberry Pi status probe
After=local-fs.target

[Service]
Type=simple
Environment=PI_STATUS_FILE=$OUTPUT
Environment=PI_STATUS_CLEAR_FILE=$CLEAR_REQUEST
Environment=PI_STATUS_PENDING_FILE=$PENDING_FILE
ExecStart=/usr/local/bin/pi-status-probe --daemon
Restart=always
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now pi-status-probe.service
  echo "probe instalado; saída: $OUTPUT"
}

case "$ACTION" in
  once)
    process_clear_request
    write_status
    ;;
  daemon)
    run_daemon
    ;;
  install)
    install_probe
    ;;
esac
