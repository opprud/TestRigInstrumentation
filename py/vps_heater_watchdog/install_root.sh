#!/usr/bin/env bash
# Install the heater-safety watchdog as a systemd service. RUN AS ROOT on the broker VPS.
#   sudo bash install_root.sh
# Idempotent: re-running updates the unit and restarts the service.
set -euo pipefail

SRC=/home/claude-win/heater-watchdog
UNIT=/etc/systemd/system/heater-watchdog.service

[ -f "$SRC/watchdog.py" ]      || { echo "missing $SRC/watchdog.py"; exit 1; }
[ -f "$SRC/config.json" ]      || { echo "missing $SRC/config.json (copy config.example.json)"; exit 1; }
[ -d "$SRC/vendor/paho" ]      || { echo "missing $SRC/vendor/paho (vendored paho-mqtt)"; exit 1; }

install -m 644 "$SRC/heater-watchdog.service" "$UNIT"
systemctl daemon-reload
systemctl enable --now heater-watchdog.service
sleep 2
systemctl status --no-pager heater-watchdog.service || true
echo
echo "Deployed. armed = $(grep -o '\"armed\"[^,]*' "$SRC/config.json"). Watch: journalctl -u heater-watchdog -f"
