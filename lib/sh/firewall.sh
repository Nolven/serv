#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: firewall.sh <staged-config-dir>}"
RULESET_STAGED="$DEST/nftables.conf"
INSTALL_PATH_FILE="$DEST/install_path"
OVERRIDE_DIR="/etc/systemd/system/nftables.service.d"
OVERRIDE_FILE="$OVERRIDE_DIR/override.conf"

if [[ ! -f "$RULESET_STAGED" || ! -f "$INSTALL_PATH_FILE" ]]; then
    echo "[ERROR] $DEST is missing nftables.conf or install_path - run --generate first" >&2
    exit 1
fi

install_path=$(cat "$INSTALL_PATH_FILE")

if ! command -v nft >/dev/null 2>&1; then
    echo "[INFO] installing nftables"
    apt-get install -y --no-install-recommends nftables >/dev/null
fi

# the ruleset flushes only this table (not "flush ruleset") - safe even
# alongside iptables-nft's tables for wireguard/docker - but that means the
# table must already exist before it can be flushed/checked at all
nft list table inet filter >/dev/null 2>&1 || nft add table inet filter

nft -c -f "$RULESET_STAGED"

mkdir -p "$(dirname "$install_path")"

changed=false
if ! cmp -s "$RULESET_STAGED" "$install_path" 2>/dev/null; then
    install -m 0640 "$RULESET_STAGED" "$install_path"
    changed=true
    echo "[INFO] installed $install_path"
fi

if [[ "$install_path" != "/etc/nftables.conf" ]]; then
    desired_override=$'[Service]\nExecStart=\nExecStart=/usr/sbin/nft -f '"$install_path"$'\nExecReload=\nExecReload=/usr/sbin/nft -f '"$install_path"$'\n'
    mkdir -p "$OVERRIDE_DIR"
    if [[ ! -f "$OVERRIDE_FILE" ]] || [[ "$(cat "$OVERRIDE_FILE")" != "$desired_override" ]]; then
        printf '%s' "$desired_override" > "$OVERRIDE_FILE"
        systemctl daemon-reload
        changed=true
        echo "[INFO] installed systemd override for nftables.service -> $install_path"
    fi
elif [[ -f "$OVERRIDE_FILE" ]]; then
    rm -f "$OVERRIDE_FILE"
    systemctl daemon-reload
    changed=true
    echo "[INFO] removed stale systemd override (install_path is the default /etc/nftables.conf)"
fi

systemctl enable --now nftables

if [[ "$changed" == true ]]; then
    systemctl reload-or-restart nftables
    echo "[INFO] reloaded nftables"
else
    echo "[INFO] nftables already up to date and running"
fi
