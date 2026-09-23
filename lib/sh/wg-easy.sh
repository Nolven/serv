#!/usr/bin/env bash
set -euo pipefail

# Host-side prerequisites and fixups for the wg-easy container. Runs before
# main.py's own "docker compose up -d" for this component.
#
# 1. sysctls: the container runs with network_mode: host, where docker
#    refuses compose-level sysctls (they'd modify the host's own kernel), so
#    they're persisted here instead.
# 2. masquerade device: wg-easy seeds its interface's "device" (the -o in its
#    PostUp MASQUERADE rule) as eth0 and has no INIT_* var to change it, so
#    it's patched straight into wg-easy's sqlite db - from $DEST/device if
#    wg-easy.device is set, else the host's default-route interface.

DEST="${1:?usage: wg-easy.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
COMPOSE="$DEST/compose.yaml"
SYSCTL_CONF="/etc/sysctl.d/99-wg-easy.conf"
DB="$DEST/etc_wireguard/wg-easy.db"
WG_IFACE="wg0"

if [[ ! -f "$COMPOSE" ]]; then
    echo "[ERROR] $DEST is missing compose.yaml - run --generate first" >&2
    exit 1
fi

desired=$'net.ipv4.ip_forward=1\nnet.ipv4.conf.all.src_valid_mark=1\n'

if [[ "$FORCE" == true ]] || [[ ! -f "$SYSCTL_CONF" ]] || [[ "$(cat "$SYSCTL_CONF")"$'\n' != "$desired" ]]; then
    printf '%s' "$desired" > "$SYSCTL_CONF"
    echo "[INFO] installed $SYSCTL_CONF"
fi

# applied unconditionally (cheap, idempotent) so the live values match even
# if something changed them at runtime since the file was written
sysctl -p "$SYSCTL_CONF" >/dev/null

if [[ -f "$DEST/device" ]]; then
    device=$(tr -d '[:space:]' < "$DEST/device")
else
    device=$(ip -4 route show default | awk '{for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | head -n1)
    if [[ -z "$device" ]]; then
        echo "[ERROR] could not auto-detect the LAN interface from the default route - set wg-easy.device in config.yaml" >&2
        exit 1
    fi
fi
if ! ip link show "$device" >/dev/null 2>&1; then
    echo "[ERROR] wg-easy masquerade device '$device' does not exist on this host - fix wg-easy.device in config.yaml (see 'ip -br link')" >&2
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "[INFO] installing sqlite3"
    apt-get install -y --no-install-recommends sqlite3 >/dev/null
fi

# the db only exists once wg-easy has started at least once - on a first
# deploy, start it here (main.py's own "up -d" afterwards is then a no-op)
# and wait for its first-start setup to bring the tunnel up
if [[ ! -f "$DB" ]]; then
    bash "$(dirname "${BASH_SOURCE[0]}")/ensure_docker.sh"
    echo "[INFO] first start of wg-easy, waiting for its setup to finish"
    docker compose -f "$COMPOSE" up -d
    for _ in $(seq 1 60); do
        if [[ -f "$DB" ]] && ip link show "$WG_IFACE" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    if ! ip link show "$WG_IFACE" >/dev/null 2>&1; then
        echo "[ERROR] wg-easy did not bring up $WG_IFACE within 60s - check 'docker logs wg-easy'" >&2
        exit 1
    fi
fi

current=$(sqlite3 "$DB" "SELECT device FROM interfaces_table WHERE name = '$WG_IFACE';")
if [[ -z "$current" ]]; then
    echo "[ERROR] no '$WG_IFACE' row in $DB interfaces_table - wg-easy's schema may have changed" >&2
    exit 1
fi

if [[ "$current" == "$device" ]]; then
    echo "[INFO] wg-easy masquerade device already $device"
else
    echo "[INFO] wg-easy masquerade device: $current -> $device"
    # stopped around the write so wg-easy never has the db open mid-change,
    # and so its PostUp re-runs against the new device on start
    docker compose -f "$COMPOSE" stop
    sqlite3 "$DB" "UPDATE interfaces_table SET device = '$device' WHERE name = '$WG_IFACE';"
    docker compose -f "$COMPOSE" start
fi
