#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: wireguard.sh <staged-config-dir>}"
INTERFACE_STAGED="$DEST/interface.conf"
WG_DIR="/etc/wireguard"
WG_CONF="$WG_DIR/wg0.conf"

if [[ ! -f "$INTERFACE_STAGED" ]]; then
    echo "[ERROR] $DEST is missing interface.conf - run --generate first" >&2
    exit 1
fi

if ! command -v wg >/dev/null 2>&1; then
    echo "[INFO] installing wireguard-tools"
    apt-get install -y --no-install-recommends wireguard >/dev/null
fi

if [[ -f "$WG_CONF" ]]; then
    echo "[INFO] $WG_CONF already exists - leaving it untouched (peers may have been added since)"
else
    echo "[INFO] bootstrapping wireguard for the first time"

    lan_iface=$(ip -4 route show default | awk '{for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | head -n1)

    if [[ -z "$lan_iface" ]]; then
        echo "[ERROR] could not auto-detect the LAN interface from the default route" >&2
        exit 1
    fi
    echo "[INFO] using $lan_iface for NAT masquerade"

    mkdir -p "$WG_DIR"
    umask 077
    wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
    chmod 600 "$WG_DIR/server_private.key"
    chmod 644 "$WG_DIR/server_public.key"

    {
        echo "[Interface]"
        cat "$INTERFACE_STAGED"
        echo "PrivateKey = $(cat "$WG_DIR/server_private.key")"
        echo "PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $lan_iface -j MASQUERADE"
        echo "PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -t nat -D POSTROUTING -o $lan_iface -j MASQUERADE"
    } > "$WG_CONF"
    chmod 600 "$WG_CONF"

    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-wireguard-forward.conf
    sysctl -p /etc/sysctl.d/99-wireguard-forward.conf >/dev/null

    echo "[INFO] server public key: $(cat "$WG_DIR/server_public.key")"
fi

systemctl enable --quiet wg-quick@wg0

if ! systemctl is-active --quiet wg-quick@wg0; then
    systemctl start wg-quick@wg0
    echo "[INFO] started wg-quick@wg0"
else
    echo "[INFO] wg-quick@wg0 already running"
fi
