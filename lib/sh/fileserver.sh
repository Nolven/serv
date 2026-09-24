#!/usr/bin/env bash
set -euo pipefail

# Host-side half of the fileserver component. Runs before main.py's own
# "docker compose up -d" for this component.
#
# 1. the account that owns general.fileserver_root - samba writes as it and
#    sftpgo's container runs as it
# 2. samba (apt + systemd), or stopping it if fileserver.samba is disabled
# 3. sftpgo's host-side prerequisites (owned state dirs, the uid/gid .env
#    compose reads), or removing its container if fileserver.sftpgo is
#    disabled - its sftpgo_data/ (accounts, links) is always kept

DEST="${1:?usage: fileserver.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
SETTINGS="$DEST/settings.env"
SMB_CONF_STAGED="$DEST/smb.conf"
SMB_CONF_INSTALLED="/etc/samba/smb.conf"
CREDENTIALS="$DEST/samba_credentials"
# samba keeps only its own hash of the password, so "is it already set" is
# tracked by the checksum of the credentials last handed to smbpasswd
CREDENTIALS_APPLIED="$DEST/.samba_credentials.applied"
COMPOSE="$DEST/compose.yaml"

if [[ ! -f "$SETTINGS" ]]; then
    echo "[ERROR] $DEST is missing settings.env - run --generate first" >&2
    exit 1
fi

declare -A cfg=()
while IFS='=' read -r key value; do
    [[ -n "$key" ]] && cfg["$key"]="$value"
done < "$SETTINGS"
for key in FILESERVER_USER FILESERVER_ROOT SAMBA_ENABLE SFTPGO_ENABLE; do
    if [[ -z "${cfg[$key]:-}" ]]; then
        echo "[ERROR] $SETTINGS has no $key - re-run --generate" >&2
        exit 1
    fi
done
owner="${cfg[FILESERVER_USER]}"
root="${cfg[FILESERVER_ROOT]}"

# --- 1. file store owner ------------------------------------------------------

if ! id -u "$owner" >/dev/null 2>&1; then
    useradd --system --user-group --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin "$owner"
    echo "[INFO] created system user $owner (no shell, no login)"
fi
uid=$(id -u "$owner")
gid=$(id -g "$owner")

mkdir -p "$root"
if [[ "$(stat -c %U "$root")" != "$owner" ]]; then
    # first adoption only: anything already in there (e.g. created as root)
    # has to become writable through samba and sftpgo too
    chown -R "$owner:$owner" "$root"
    echo "[INFO] $root is now owned by $owner (recursively, first time only)"
fi

# --- 2. samba -----------------------------------------------------------------

samba_unit_exists() {
    systemctl cat smbd.service >/dev/null 2>&1
}

if [[ "${cfg[SAMBA_ENABLE]}" == true ]]; then
    if [[ ! -f "$SMB_CONF_STAGED" || ! -f "$CREDENTIALS" ]]; then
        echo "[ERROR] $DEST is missing smb.conf or samba_credentials - run --generate first" >&2
        exit 1
    fi

    if ! command -v smbd >/dev/null 2>&1; then
        echo "[INFO] installing samba"
        apt-get install -y --no-install-recommends samba >/dev/null
    fi

    # NetBIOS is off in smb.conf, so nmbd has nothing left to do
    if systemctl is-enabled --quiet nmbd 2>/dev/null || systemctl is-active --quiet nmbd; then
        systemctl disable --now --quiet nmbd
        echo "[INFO] stopped and disabled nmbd (NetBIOS is off)"
    fi

    if ! testparm_out=$(testparm -s "$SMB_CONF_STAGED" 2>&1 >/dev/null); then
        echo "[ERROR] $SMB_CONF_STAGED failed testparm - samba left untouched:" >&2
        echo "$testparm_out" >&2
        exit 1
    fi

    login=$(sed -n 1p "$CREDENTIALS")
    password=$(sed -n 2p "$CREDENTIALS")
    if ! id -u "$login" >/dev/null 2>&1; then
        useradd --system --no-create-home --home-dir /nonexistent \
            --shell /usr/sbin/nologin "$login"
        echo "[INFO] created user $login for samba (no shell, no login)"
    fi

    applied=$(sha256sum < "$CREDENTIALS" | cut -d' ' -f1)
    if [[ "$FORCE" == true ]] \
        || ! pdbedit -L -u "$login" >/dev/null 2>&1 \
        || [[ "$(cat "$CREDENTIALS_APPLIED" 2>/dev/null)" != "$applied" ]]; then
        printf '%s\n%s\n' "$password" "$password" | smbpasswd -s -a "$login" >/dev/null
        smbpasswd -e "$login" >/dev/null
        (umask 077 && printf '%s\n' "$applied" > "$CREDENTIALS_APPLIED")
        echo "[INFO] set samba password for $login"
    fi

    conf_changed=false
    if [[ "$FORCE" == true ]] || ! cmp -s "$SMB_CONF_STAGED" "$SMB_CONF_INSTALLED" 2>/dev/null; then
        install -m 0644 "$SMB_CONF_STAGED" "$SMB_CONF_INSTALLED"
        conf_changed=true
        echo "[INFO] installed $SMB_CONF_INSTALLED"
    fi

    systemctl enable --quiet smbd
    if [[ "$FORCE" == true ]]; then
        systemctl restart smbd
        echo "[INFO] restarted smbd"
    elif ! systemctl is-active --quiet smbd; then
        systemctl start smbd
        echo "[INFO] started smbd"
    elif [[ "$conf_changed" == true ]]; then
        # reload, not restart: open sessions (e.g. a mounted drive mid-copy)
        # survive, and smbd applies the new config to them as well
        systemctl reload smbd
        echo "[INFO] reloaded smbd"
    else
        echo "[INFO] samba already up to date and running"
    fi
elif samba_unit_exists && { systemctl is-enabled --quiet smbd 2>/dev/null || systemctl is-active --quiet smbd; }; then
    systemctl disable --now --quiet smbd
    echo "[INFO] fileserver.samba is disabled - stopped and disabled smbd (package and config left installed)"
fi

# --- 3. sftpgo ----------------------------------------------------------------

if [[ "${cfg[SFTPGO_ENABLE]}" == true ]]; then
    outbox="${cfg[OUTBOX_DIR]:-}"
    if [[ ! -f "$COMPOSE" || ! -f "$DEST/provision/provision.json" || -z "$outbox" ]]; then
        echo "[ERROR] $DEST is missing sftpgo's compose.yaml/provision.json - run --generate first" >&2
        exit 1
    fi

    mkdir -p "$outbox"
    chown "$owner:$owner" "$outbox"

    # created here, owned by the container's user, before compose would
    # create them as root - sftpgo runs as $owner and must write into them
    for dir in sftpgo_data sftpgo_home; do
        mkdir -p "$DEST/$dir"
        chown "$owner:$owner" "$DEST/$dir"
    done
    chown -R "$owner:$owner" "$DEST/provision"
    chmod 0700 "$DEST/provision"
    chmod 0600 "$DEST/provision/provision.json"

    env_desired="FILESERVER_UID=$uid"$'\n'"FILESERVER_GID=$gid"$'\n'
    if [[ ! -f "$DEST/.env" ]] || [[ "$(cat "$DEST/.env")"$'\n' != "$env_desired" ]]; then
        printf '%s' "$env_desired" > "$DEST/.env"
        echo "[INFO] wrote $DEST/.env (sftpgo runs as $owner, $uid:$gid)"
    fi
elif [[ -f "$COMPOSE" ]]; then
    # left behind by an earlier deploy - main.py would otherwise keep
    # bringing the container up from it
    if command -v docker >/dev/null 2>&1; then
        docker compose -f "$COMPOSE" down
    fi
    rm -rf "$COMPOSE" "$DEST/.env" "$DEST/provision"
    echo "[INFO] fileserver.sftpgo is disabled - removed its container (sftpgo_data/ with accounts and links kept)"
fi
