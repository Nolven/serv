#!/bin/bash

apt update
apt install python3 python3-pip

exec python3 lib/py/main.py "$@"