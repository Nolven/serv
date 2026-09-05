#!/usr/bin/env bash
set -euo pipefail
# Not part of the deploy pipeline - run manually to onboard a peer:
#   bash lib/sh/wireguard_add_peer.sh <peer_name> <peer_ip>
# Generates that peer's keypair, registers it live on wg0, and saves the
# running config back to wg0.conf so the deploy pipeline (which never
# touches an existing wg0.conf) doesn't clobber it later.

PEER_NAME="${1:?usage: wireguard_add_peer.sh <peer_name> <peer_ip>}"
PEER_IP="${2:?usage: wireguard_add_peer.sh <peer_name> <peer_ip>}"

PEERS_DIR="/etc/wireguard/peers"
PEER_KEY="$PEERS_DIR/$PEER_NAME.key"
PEER_PUB="$PEERS_DIR/$PEER_NAME.pub"
SERVER_PUB="/etc/wireguard/server_public.key"

if [[ -f "$PEER_KEY" ]]; then
    echo "[ERROR] peer '$PEER_NAME' already has a keypair at $PEER_KEY" >&2
    exit 1
fi

if ! systemctl is-active --quiet wg-quick@wg0; then
    echo "[ERROR] wg-quick@wg0 is not running - deploy wireguard first" >&2
    exit 1
fi

mkdir -p "$PEERS_DIR"
umask 077
wg genkey | tee "$PEER_KEY" | wg pubkey > "$PEER_PUB"
chmod 600 "$PEER_KEY"

wg set wg0 peer "$(cat "$PEER_PUB")" allowed-ips "$PEER_IP/32"
wg-quick save wg0

echo "[INFO] peer '$PEER_NAME' added: $PEER_IP"
echo "[INFO] peer private key: $(cat "$PEER_KEY")"
echo "[INFO] server public key: $(cat "$SERVER_PUB")"
