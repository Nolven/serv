#!/usr/bin/env bash
set -euo pipefail

# The landing page is a single static file the reverse proxy serves directly -
# there is no service to start, so this only fixes up permissions so the proxy
# (running as its own user) can traverse the directory and read the file.
DEST="${1:?usage: landing.sh <staged-config-dir> [--force]}"
SITE="$DEST/site"
INDEX="$SITE/index.html"

if [[ ! -f "$INDEX" ]]; then
    echo "[ERROR] $SITE is missing index.html - run --generate first" >&2
    exit 1
fi

chmod 0755 "$DEST" "$SITE"
chmod 0644 "$INDEX"
echo "[INFO] landing page installed at $INDEX"
