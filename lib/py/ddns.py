import re
from pathlib import Path, PurePosixPath
from typing import Any

from utils import info

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "ddns"

SCRIPT_NAME = "duckdns_keepup.py"
SERVICE_NAME = "duckdns_keepup.service"


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    return {}


def _require(config: dict[str, Any]) -> tuple[str, str, str]:
    domain = config.get("domain")
    token = config.get("token")
    bin_path = config.get("bin_path")
    missing = [
        k
        for k, v in (("domain", domain), ("token", token), ("bin_path", bin_path))
        if not v
    ]
    if missing:
        raise ValueError(f"ddns missing required key(s): {', '.join(missing)}")
    if not bin_path.startswith("/"):
        raise ValueError(
            f"ddns.bin_path must be an absolute path (starting with /), got '{bin_path}'"
        )
    return domain, token, bin_path


def _render_script(domain: str, token: str) -> str:
    text = (DEFAULTS_DIR / SCRIPT_NAME).read_text()
    text, n_domain = re.subn(
        r'(?m)^domain = ".*"$', lambda _m: f'domain = "{domain}"', text, count=1
    )
    text, n_token = re.subn(
        r'(?m)^token = ".*"$', lambda _m: f'token = "{token}"', text, count=1
    )
    if n_domain != 1 or n_token != 1:
        raise ValueError(
            f"{DEFAULTS_DIR / SCRIPT_NAME} no longer has a single 'domain = \"...\"' / "
            f"'token = \"...\"' line to template - vendored script changed upstream"
        )
    return text


def _render_service(script_path: PurePosixPath) -> str:
    text = (DEFAULTS_DIR / SERVICE_NAME).read_text()
    text, n = re.subn(
        r"NEEDS_TO_BE_REPLACED", lambda _m: str(script_path), text, count=1
    )
    if n != 1:
        raise ValueError(
            f"{DEFAULTS_DIR / SERVICE_NAME} no longer has a NEEDS_TO_BE_REPLACED placeholder - "
            f"vendored service file changed upstream"
        )
    return text


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    domain, token, bin_path = _require(config)
    script_path = PurePosixPath(bin_path) / SCRIPT_NAME

    script_text = _render_script(domain, token)
    out_script = out / SCRIPT_NAME
    out_script.parent.mkdir(parents=True, exist_ok=True)
    with open(out_script, "w", newline="\n") as f:
        f.write(script_text)
    out_script.chmod(0o600)
    info(f"Generated {SCRIPT_NAME} (contains ddns token - content not printed)")

    service_text = _render_service(script_path)
    with open(out / SERVICE_NAME, "w", newline="\n") as f:
        f.write(service_text)
    (out / SERVICE_NAME).chmod(0o644)
    info(f"Generated {SERVICE_NAME}:\n{service_text}")
