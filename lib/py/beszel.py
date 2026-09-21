from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from utils import info, write_text, write_yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "beszel"

# the hub always serves on this port inside its container; config.yaml's port
# is the host-side port, so only the published mapping is configurable
HUB_CONTAINER_PORT = 8090

# PocketBase (the hub's backend) rejects shorter passwords, and a rejected
# USER_PASSWORD fails silently - no initial user is created and the login
# screen just refuses the credentials
MIN_PASSWORD_LEN = 10

_PAIRING_NOTE = (
    "beszel's agent can't be paired automatically - the hub generates its "
    "public key and registration token on first run, so they can't be known "
    "before it starts. Until they're set, only the hub runs. To finish: open "
    "{host} , log in as {email}, go to Settings -> Tokens & Fingerprints, "
    "enable the universal token, then copy that token and the public key into "
    "config.yaml (beszel.agent.token / beszel.agent.key) and re-run a deploy."
)


def _subdomain(config: dict[str, Any]) -> dict[str, Any]:
    subdomain = config.get("subdomain") or {}
    missing = [k for k in ("name", "port") if k not in subdomain]
    if missing:
        raise ValueError(
            f"beszel.subdomain missing required key(s): {', '.join(missing)}"
        )
    return subdomain


def _agent_paired(config: dict[str, Any]) -> bool:
    agent = config.get("agent") or {}
    return bool(agent.get("key")) and bool(agent.get("token"))


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    if "install" not in general:
        raise ValueError("general.install is required")
    subdomain = _subdomain(config)

    capabilities: dict[str, Any] = {
        "config_file": {
            "path": str(PurePosixPath(general["install"]) / "beszel" / "compose.yaml")
        },
        "http_route": {"subdomain": subdomain["name"], "port": subdomain["port"]},
    }
    if subdomain.get("wan", False):
        capabilities["http_route"]["wan"] = True

    if not _agent_paired(config):
        if "apex_domain" not in general:
            raise ValueError("general.apex_domain is required")
        capabilities["post_deploy_note"] = {
            "message": _PAIRING_NOTE.format(
                host=f"{subdomain['name']}.{general['apex_domain']}",
                email=config.get("admin_email") or "the admin user",
            )
        }
    return capabilities


def _validate(config: dict[str, Any]) -> tuple[str, str]:
    email = config.get("admin_email")
    password = config.get("admin_pass")
    missing = [
        label
        for label, value in (
            ("beszel.admin_email", email),
            ("beszel.admin_pass", password),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"beszel missing required config: {', '.join(missing)}")
    if len(str(password)) < MIN_PASSWORD_LEN:
        raise ValueError(
            f"beszel.admin_pass must be at least {MIN_PASSWORD_LEN} characters - "
            "the hub silently skips creating the initial user for shorter ones"
        )
    return str(email), str(password)


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    subdomain = _subdomain(config)
    email, password = _validate(config)

    with open(DEFAULTS_DIR / "compose.yaml", "r") as f:
        compose: dict[str, Any] = yaml.safe_load(f)

    # published on loopback only: caddy proxies to localhost, and a published
    # docker port is DNAT'd past the host's INPUT policy, so binding all
    # interfaces would expose the hub on the LAN regardless of the firewall
    compose["services"]["beszel"]["ports"] = [
        f"127.0.0.1:{subdomain['port']}:{HUB_CONTAINER_PORT}"
    ]

    agent = config.get("agent") or {}
    paired = _agent_paired(config)
    if paired:
        write_text(
            out / "beszel-agent.env",
            "\n".join(
                (
                    # loopback: the hub is on the same host, so the agent's
                    # listener never needs to be reachable from the LAN
                    f"LISTEN=127.0.0.1:{agent.get('listen_port', 45876)}",
                    f"HUB_URL=http://127.0.0.1:{subdomain['port']}",
                    f"KEY={agent['key']}",
                    f"TOKEN={agent['token']}",
                )
            )
            + "\n",
            mode=0o600,
        )
    else:
        # an agent with no key/token can't authenticate; leaving it out beats
        # shipping a container that restart-loops until pairing is done
        del compose["services"]["beszel-agent"]

    compose_text = write_yaml(out / "compose.yaml", compose, mode=0o644)
    info(f"Generated beszel compose:\n{compose_text}")

    write_text(
        out / "beszel.env",
        f"USER_EMAIL={email}\nUSER_PASSWORD={password}\n",
        mode=0o600,
    )
    info("Generated beszel.env (contains admin password - content not printed)")
    if paired:
        info("Generated beszel-agent.env (contains pairing secrets - not printed)")
    else:
        info(
            "beszel.agent.key/token not set - rendering the hub only; "
            "see the reminder at the end of a --deploy run to finish pairing"
        )
