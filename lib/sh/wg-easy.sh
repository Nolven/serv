#!/usr/bin/env bash
set -euo pipefail

# Host-side prerequisites for the wg-easy container. It runs with
# network_mode: host, where docker refuses compose-level sysctls (they'd
# modify the host's own kernel), so they're persisted here instead. Runs
# before main.py's "docker compose up -d" for this component.

DEST="${1:?usage: wg-easy.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
SYSCTL_CONF="/etc/sysctl.d/99-wg-easy.conf"

if [[ ! -f "$DEST/compose.yaml" ]]; then
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
