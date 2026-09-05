#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if ! python3 -c "import venv" >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y --no-install-recommends python3 python3-venv
fi

if [[ ! -d .venv ]]; then
    python3 -m venv .venv
fi

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

exec .venv/bin/python lib/py/main.py "$@"