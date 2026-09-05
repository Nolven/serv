from pathlib import Path
from typing import Any

from utils import info, write_text


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    return {}


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    host_ip = general.get("host_ip")
    server_mask = config.get("server_mask")
    listen_port = config.get("listen_port")

    missing = [
        label
        for label, value in (
            ("general.host_ip", host_ip),
            ("wireguard.server_mask", server_mask),
            ("wireguard.listen_port", listen_port),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"wireguard missing required config: {', '.join(missing)}")

    # PrivateKey and PostUp/PostDown (LAN interface is host-specific) are
    # assembled by lib/sh/wireguard.sh on first deploy, never here - the
    # server key must persist and never flow through --generate output.
    text = f"Address = {host_ip}/{server_mask}\nListenPort = {listen_port}\n"
    interface_text = write_text(out / "interface.conf", text, mode=0o644)
    info(f"Generated wireguard interface.conf:\n{interface_text}")
