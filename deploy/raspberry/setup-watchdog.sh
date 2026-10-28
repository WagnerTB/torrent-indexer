#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

if [ ! -e /dev/watchdog ]; then
  echo "watchdog device not found" >&2
  echo "add 'dtparam=watchdog=on' to /boot/firmware/config.txt, reboot and retry" >&2
  exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -D -m 0644 "$SCRIPT_DIR/watchdog.conf" /etc/systemd/system.conf.d/watchdog.conf
systemctl daemon-reexec
sleep 1
systemctl show -p RuntimeWatchdogUSec -p RebootWatchdogUSec -p ShutdownWatchdogUSec
wdctl
