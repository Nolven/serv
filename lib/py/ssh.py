from pathlib import Path
from typing import Any

from utils import info, write_text

VALID_PERMIT_ROOT_LOGIN = ("yes", "no", "prohibit-password", "forced-commands-only")


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    port = config.get("port")
    if not port:
        raise ValueError("ssh.port is required")
    return {"firewall_rule": {"proto": "tcp", "port": port}}


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    port = config.get("port")
    if not port:
        raise ValueError("ssh.port is required")

    permit_root_login = config.get("permit_root_login", "no")
    if permit_root_login not in VALID_PERMIT_ROOT_LOGIN:
        raise ValueError(
            f"ssh.permit_root_login must be one of {VALID_PERMIT_ROOT_LOGIN}, "
            f"got '{permit_root_login}'"
        )
    password_authentication = "yes" if config.get("password_authentication") else "no"

    text = (
        f"Port {port}\n"
        f"PermitRootLogin {permit_root_login}\n"
        f"PasswordAuthentication {password_authentication}\n"
    )
    conf_text = write_text(out / "sshd_serv.conf", text, mode=0o644)
    info(f"Generated sshd drop-in:\n{conf_text}")
