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

# site blocks bind general.host_ip, which may not exist on the host yet
# (e.g. it lives on a tunnel interface another service brings up later, at
# deploy or at boot). Without this, reload/start fails with "cannot assign
# requested address" - with it, caddy binds regardless and starts serving on
# that address as soon as it appears
NONLOCAL_BIND_CONF="/etc/sysctl.d/99-caddy-nonlocal-bind.conf"
nonlocal_desired=$'net.ipv4.ip_nonlocal_bind=1\n'
if [[ ! -f "$NONLOCAL_BIND_CONF" ]] || [[ "$(cat "$NONLOCAL_BIND_CONF")"$'\n' != "$nonlocal_desired" ]]; then
    printf '%s' "$nonlocal_desired" > "$NONLOCAL_BIND_CONF"
    echo "[INFO] installed $NONLOCAL_BIND_CONF"
fi
sysctl -p "$NONLOCAL_BIND_CONF" >/dev/null

mkdir -p "$(dirname "$CADDYFILE_INSTALLED")"

changed=false
backup=""
if [[ "$FORCE" == true ]] || ! cmp -s "$CADDYFILE_STAGED" "$CADDYFILE_INSTALLED" 2>/dev/null; then
    if [[ -f "$CADDYFILE_INSTALLED" ]]; then
        backup=$(mktemp)
        cp -p "$CADDYFILE_INSTALLED" "$backup"
    fi
    install -m 0644 "$CADDYFILE_STAGED" "$CADDYFILE_INSTALLED"
    changed=true
    echo "[INFO] installed $CADDYFILE_INSTALLED"
fi

# a failed reload leaves caddy running its *previous* config - if the new
# file stayed installed, the next deploy's cmp would see "no change" and
# never retry, silently leaving the running config stale. Putting the old
# file back keeps the installed file matching what caddy actually runs.
rollback() {
    if [[ -n "$backup" ]]; then
        mv "$backup" "$CADDYFILE_INSTALLED"
    else
        rm -f "$CADDYFILE_INSTALLED"
    fi
    echo "[ERROR] $1 - restored the previous $CADDYFILE_INSTALLED so the next deploy retries; see 'journalctl -xeu caddy.service'" >&2
    exit 1
}

if [[ "$changed" == true ]] && ! systemctl is-active --quiet caddy; then
    # only when caddy isn't already running - "caddy validate" provisions a
    # full temporary instance (admin API included), which hangs trying to
    # bind the same default admin socket (localhost:2019) the live systemd
    # instance already holds. Once caddy is running, "systemctl reload"
    # below validates via that instance's own /load endpoint instead.
    caddy validate --config "$CADDYFILE_INSTALLED" --adapter caddyfile         || rollback "new Caddyfile failed validation"
fi

systemctl enable --quiet caddy

if [[ "$changed" == true ]]; then
    if systemctl is-active --quiet caddy; then
        systemctl reload caddy || rollback "caddy reload failed"
        echo "[INFO] reloaded caddy"
    else
        systemctl start caddy || rollback "caddy failed to start"
        echo "[INFO] started caddy"
    fi
    if [[ -n "$backup" ]]; then
        rm -f "$backup"
    fi
elif ! systemctl is-active --quiet caddy; then
    systemctl start caddy
    echo "[INFO] started caddy"
else
    echo "[INFO] caddy already up to date and running"
fi
