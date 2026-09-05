#!/bin/bash

SCRIPT_NAME="duckdns_keepup.py"
SERVICE_NAME="duckdns_keepup.service"
SERVICE_DIR="/etc/systemd/system"
SCRIPT_DIR="/usr/local/bin"  # or wherever you want to place your script
SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_NAME"
SERVICE_PATH="$SERVICE_DIR/$SERVICE_NAME"

if [ ! -f "$SERVICE_NAME" ]; then
    echo "Error: $SERVICE_NAME not found in the current directory."
    exit 1
fi
if [ ! -f "$SCRIPT_NAME" ]; then
    echo "Error: $SCRIPT_NAME not found in the current directory."
    exit 1
fi

sudo cp "$SCRIPT_NAME" "$SCRIPT_PATH"

sudo cp "$SERVICE_NAME" "$SERVICE_DIR"
sed -i "s|NEEDS_TO_BE_REPLACED|$SCRIPT_PATH|g" "$SERVICE_PATH"

sudo systemctl daemon-reload

sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo "Service $SERVICE_NAME has been installed and started successfully."
