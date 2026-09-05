#!/usr/bin/env bash
set -euo pipefail

DEST="${1:?usage: wireguard.sh <staged-config-dir> [--force]}"
FORCE=false
[[ "${2:-}" == "--force" ]] && FORCE=true
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

# not pulled in by the wireguard package, but PostUp/PostDown (below) shell
# out to it directly
if ! command -v iptables >/dev/null 2>&1; then
    echo "[INFO] installing iptables"
    apt-get install -y --no-install-recommends iptables >/dev/null
fi

lan_iface=$(ip -4 route show default | awk '{for (i=1;i<=NF;i++) if ($i=="dev") print $(i+1)}' | head -n1)
if [[ -z "$lan_iface" ]]; then
    echo "[ERROR] could not auto-detect the LAN interface from the default route" >&2
    exit 1
fi
post_up="iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o $lan_iface -j MASQUERADE; iptables -N DOCKER-USER 2>/dev/null || true; iptables -I DOCKER-USER 1 -i %i -j ACCEPT"
post_down="iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o $lan_iface -j MASQUERADE; iptables -D DOCKER-USER -i %i -j ACCEPT || true"

if [[ -f "$WG_CONF" ]]; then
    if [[ "$FORCE" == true ]]; then
        echo "[INFO] --force: updating $WG_CONF, preserving the existing PrivateKey and peers"

        private_key=$(sed -n 's/^PrivateKey = //p' "$WG_CONF" | head -n1)
        if [[ -z "$private_key" ]]; then
            echo "[ERROR] could not find an existing PrivateKey in $WG_CONF - refusing to proceed" >&2
            exit 1
        fi
        peer_blocks=$(sed -n '/^\[Peer\]/,$p' "$WG_CONF")

        tmp_conf=$(mktemp)
        {
            echo "[Interface]"
            cat "$INTERFACE_STAGED"
            echo "PrivateKey = $private_key"
            echo "PostUp = $post_up"
            echo "PostDown = $post_down"
            if [[ -n "$peer_blocks" ]]; then
                echo ""
                printf '%s\n' "$peer_blocks"
            fi
        } > "$tmp_conf"
        chmod 600 "$tmp_conf"
        mv "$tmp_conf" "$WG_CONF"

        systemctl restart wg-quick@wg0
        echo "[INFO] restarted wg-quick@wg0 with updated settings (key and peers preserved)"
    else
        echo "[INFO] $WG_CONF already exists - leaving it untouched (peers may have been added since; re-run with --force to update Address/ListenPort/etc while preserving the key and peers)"
    fi
else
    echo "[INFO] bootstrapping wireguard for the first time"
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
        echo "PostUp = $post_up"
        echo "PostDown = $post_down"
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
elif [[ "$FORCE" != true ]]; then
    echo "[INFO] wg-quick@wg0 already running"
fi
