#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: ssh.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
CONF_STAGED="$DEST/sshd_serv.conf"
CONF_INSTALLED="/etc/ssh/sshd_config.d/99-serv.conf"

if [[ ! -f "$CONF_STAGED" ]]; then
    echo "[ERROR] $DEST is missing sshd_serv.conf - run --generate first" >&2
    exit 1
fi

if ! command -v sshd >/dev/null 2>&1; then
    echo "[INFO] installing openssh-server"
    apt-get install -y --no-install-recommends openssh-server >/dev/null
fi

if [[ "$FORCE" != true ]] && cmp -s "$CONF_STAGED" "$CONF_INSTALLED" 2>/dev/null; then
    echo "[INFO] sshd config already up to date"
    exit 0
fi

mkdir -p "$(dirname "$CONF_INSTALLED")"

# Include /etc/ssh/sshd_config.d/*.conf sits at the top of Debian's default
# sshd_config, so this drop-in's directives take priority over the defaults
# below it - no need to touch sshd_config itself.
backup=""
if [[ -f "$CONF_INSTALLED" ]]; then
    backup=$(mktemp)
    cp "$CONF_INSTALLED" "$backup"
fi

install -m 0644 "$CONF_STAGED" "$CONF_INSTALLED"

if ! sshd -t; then
    echo "[ERROR] new sshd config failed validation - reverting, NOT restarting ssh" >&2
    if [[ -n "$backup" ]]; then
        install -m 0644 "$backup" "$CONF_INSTALLED"
    else
        rm -f "$CONF_INSTALLED"
    fi
    rm -f "$backup"
    exit 1
fi
rm -f "$backup"

systemctl restart ssh
echo "[INFO] restarted ssh with updated config"
