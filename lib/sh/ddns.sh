#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: ddns.sh <staged-config-dir>}"
SERVICE_UNIT="duckdns_keepup.service"
SCRIPT_NAME="duckdns_keepup.py"
SYSTEMD_DIR="/etc/systemd/system"

SCRIPT_STAGED="$DEST/$SCRIPT_NAME"
SERVICE_STAGED="$DEST/$SERVICE_UNIT"

if [[ ! -f "$SCRIPT_STAGED" || ! -f "$SERVICE_STAGED" ]]; then
    echo "[ERROR] $DEST is missing $SCRIPT_NAME or $SERVICE_UNIT - run --generate first" >&2
    exit 1
fi

script_path=$(sed -n 's/^ExecStart=python3 //p' "$SERVICE_STAGED")
if [[ -z "$script_path" ]]; then
    echo "[ERROR] could not read ExecStart path from $SERVICE_STAGED" >&2
    exit 1
fi

echo "[INFO] ensuring python3-requests and python3-systemd are installed"
apt-get install -y --no-install-recommends python3-requests python3-systemd >/dev/null

mkdir -p "$(dirname "$script_path")"

changed=false

if ! cmp -s "$SCRIPT_STAGED" "$script_path" 2>/dev/null; then
    install -m 0600 "$SCRIPT_STAGED" "$script_path"
    changed=true
    echo "[INFO] installed $script_path"
fi

if ! cmp -s "$SERVICE_STAGED" "$SYSTEMD_DIR/$SERVICE_UNIT" 2>/dev/null; then
    install -m 0644 "$SERVICE_STAGED" "$SYSTEMD_DIR/$SERVICE_UNIT"
    changed=true
    echo "[INFO] installed $SYSTEMD_DIR/$SERVICE_UNIT"
fi

if [[ "$changed" == true ]]; then
    systemctl daemon-reload
fi

systemctl enable --quiet "$SERVICE_UNIT"

if [[ "$changed" == true ]] || ! systemctl is-active --quiet "$SERVICE_UNIT"; then
    systemctl restart "$SERVICE_UNIT"
    echo "[INFO] (re)started $SERVICE_UNIT"
else
    echo "[INFO] $SERVICE_UNIT already up to date and running"
fi
