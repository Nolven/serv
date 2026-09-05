#!/usr/bin/env bash
set -euo pipefail
# Shared by any component whose rendered output includes a compose.yaml -
# main.py's deploy_component() calls this before every "docker compose up -d",
# not tied to any one component's name.

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    exit 0
fi

echo "[INFO] installing docker (official apt repo)"

apt-get install -y --no-install-recommends ca-certificates curl gnupg >/dev/null

install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
fi

if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $VERSION_CODENAME stable" \
        | tee /etc/apt/sources.list.d/docker.list >/dev/null
    apt-get update -qq
fi

apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker
