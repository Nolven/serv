#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: caddy.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
CADDYFILE_STAGED="$DEST/Caddyfile"
CADDYFILE_INSTALLED="/etc/caddy/Caddyfile"
FILESERVER_ROOT_FILE="$DEST/fileserver_root"

if [[ ! -f "$CADDYFILE_STAGED" ]]; then
    echo "[ERROR] $DEST is missing Caddyfile - run --generate first" >&2
    exit 1
fi

if [[ -f "$FILESERVER_ROOT_FILE" ]]; then
    fileserver_root=$(cat "$FILESERVER_ROOT_FILE")
    mkdir -p "$fileserver_root"
fi

if ! command -v caddy >/dev/null 2>&1; then
    echo "[INFO] installing caddy from the official apt repo"
    apt-get install -y --no-install-recommends \
        debian-keyring debian-archive-keyring apt-transport-https curl gnupg >/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -qq
    apt-get install -y caddy
fi

mkdir -p "$(dirname "$CADDYFILE_INSTALLED")"

changed=false
if [[ "$FORCE" == true ]] || ! cmp -s "$CADDYFILE_STAGED" "$CADDYFILE_INSTALLED" 2>/dev/null; then
    install -m 0644 "$CADDYFILE_STAGED" "$CADDYFILE_INSTALLED"
    changed=true
    echo "[INFO] installed $CADDYFILE_INSTALLED"
fi

if [[ "$changed" == true ]] && ! systemctl is-active --quiet caddy; then
    # only when caddy isn't already running - "caddy validate" provisions a
    # full temporary instance (admin API included), which hangs trying to
    # bind the same default admin socket (localhost:2019) the live systemd
    # instance already holds. Once caddy is running, "systemctl reload"
    # below validates via that instance's own /load endpoint instead.
    caddy validate --config "$CADDYFILE_INSTALLED" --adapter caddyfile
fi

systemctl enable --quiet caddy

if [[ "$changed" == true ]]; then
    if systemctl is-active --quiet caddy; then
        systemctl reload caddy
        echo "[INFO] reloaded caddy"
    else
        systemctl start caddy
        echo "[INFO] started caddy"
    fi
elif ! systemctl is-active --quiet caddy; then
    systemctl start caddy
    echo "[INFO] started caddy"
else
    echo "[INFO] caddy already up to date and running"
fi
