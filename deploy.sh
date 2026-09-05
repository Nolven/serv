#!/bin/bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

apt-get update -qq
apt-get install -y --no-install-recommends python3 python3-venv

# python3-venv alone isn't enough - Debian splits ensurepip support into the
# version-pinned package (e.g. python3.13-venv), without which `python3 -m
# venv` fails at creation time even though "import venv" already succeeds
python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
apt-get install -y --no-install-recommends "python${python_version}-venv"

if [[ ! -x .venv/bin/pip ]]; then
    rm -rf .venv
    python3 -m venv .venv
fi

.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

exec .venv/bin/python lib/py/main.py "$@"