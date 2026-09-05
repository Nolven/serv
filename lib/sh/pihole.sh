#!/usr/bin/env bash
set -euo pipefail

: "${1:?usage: pihole.sh <staged-config-dir>}"

DROPIN_DIR="/etc/systemd/resolved.conf.d"
DROPIN_FILE="$DROPIN_DIR/pihole-stub-listener.conf"
DESIRED=$'[Resolve]\nDNSStubListener=no\n'

mkdir -p "$DROPIN_DIR"

if [[ ! -f "$DROPIN_FILE" ]] || [[ "$(cat "$DROPIN_FILE")" != "$DESIRED" ]]; then
    printf '%s' "$DESIRED" > "$DROPIN_FILE"
    systemctl restart systemd-resolved
    echo "[INFO] disabled systemd-resolved's DNS stub listener (frees port 53 for pihole)"
else
    echo "[INFO] systemd-resolved stub listener already disabled"
fi
