from pathlib import Path, PurePosixPath
from typing import Any

from utils import info, write_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "wg-easy"

# wg-easy has no IPv6 story in this project; a client-subnet CIDR is required
# alongside INIT_IPV4_CIDR (same "group" in wg-easy's unattended-setup env
# vars - it's all-or-nothing) but nothing here ever routes over it
INIT_IPV6_CIDR = "fd00:dead:beef::/64"

_INIT_ONLY_NOTE = (
    "wg-easy's INIT_* setup only runs on its container's very first start. "
    "Everything it seeds (listen port, public host, admin credentials, "
    "client DNS, peers) now lives in wg-easy's own state - changing "
    "wg-easy.* or general.wan_host in config.yaml and redeploying (even "
    "--force) will NOT change a running wg-easy; use the webui at {host} "
    "for that. The one exception is wg-easy.device (the masquerade "
    "interface), which every deploy enforces."
)


def _subdomain(config: dict[str, Any]) -> dict[str, Any]:
    subdomain = config.get("subdomain") or {}
    missing = [k for k in ("name", "port") if k not in subdomain]
    if missing:
        raise ValueError(
            f"wg-easy.subdomain missing required key(s): {', '.join(missing)}"
        )
    return subdomain


def _dns(config: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    """Explicit wg-easy.dns wins; otherwise every declared dns_resolver."""
    dns = config.get("dns")
    if dns:
        return [dns] if isinstance(dns, str) else [str(d) for d in dns]
    addresses: list[str] = []
    for name in sorted(registry):
        resolver = registry[name].get("dns_resolver")
        if not resolver:
            continue
        if "address" not in resolver:
            raise ValueError(f"{name}: dns_resolver missing key: address")
        addresses.append(resolver["address"])
    return addresses


def _require(config: dict[str, Any], general: dict[str, Any]) -> None:
    missing = [
        label
        for label, value in (
            ("wg-easy.server_mask", config.get("server_mask")),
            ("wg-easy.listen_port", config.get("listen_port")),
            ("wg-easy.admin_user", config.get("admin_user")),
            ("wg-easy.admin_pass", config.get("admin_pass")),
            ("general.host_ip", general.get("host_ip")),
            ("general.wan_host", general.get("wan_host")),
            ("general.apex_domain", general.get("apex_domain")),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"wg-easy missing required config: {', '.join(missing)}")


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    if "install" not in general:
        raise ValueError("general.install is required")
    _require(config, general)
    subdomain = _subdomain(config)

    capabilities: dict[str, Any] = {
        "firewall_rule": {"proto": "udp", "port": config["listen_port"]},
        "http_route": {"subdomain": subdomain["name"], "port": subdomain["port"]},
        "config_file": {
            "path": str(PurePosixPath(general["install"]) / "wg-easy" / "compose.yaml")
        },
        "post_deploy_note": {
            "message": _INIT_ONLY_NOTE.format(
                host=f"{subdomain['name']}.{general['apex_domain']}"
            )
        },
    }
    if subdomain.get("wan", False):
        capabilities["http_route"]["wan"] = True
    return capabilities


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    _require(config, general)
    subdomain = _subdomain(config)

    ipv4_cidr = f"{general['host_ip']}/{config['server_mask']}"

    lines = [
        "INIT_ENABLED=true",
        f"INIT_USERNAME={config['admin_user']}",
        f"INIT_PASSWORD={config['admin_pass']}",
        f"INIT_HOST={general['wan_host']}",
        f"INIT_PORT={config['listen_port']}",
        f"INIT_IPV4_CIDR={ipv4_cidr}",
        f"INIT_IPV6_CIDR={INIT_IPV6_CIDR}",
        # webui: loopback only - reached exclusively through caddy's
        # reverse_proxy localhost:<port>, same as every other proxied
        # component; INSECURE because the hop from caddy to here is plain
        # HTTP, TLS is already terminated at caddy
        "HOST=127.0.0.1",
        f"PORT={subdomain['port']}",
        "INSECURE=true",
    ]
    dns = _dns(config, registry)
    if dns:
        lines.append(f"INIT_DNS={','.join(dns)}")
        info(f"wg-easy default client DNS: {', '.join(dns)}")
    else:
        info("wg-easy default client DNS: wg-easy's own default (no dns_resolver)")

    write_text(out / "wg-easy.env", "\n".join(lines) + "\n", mode=0o600)
    info("Generated wg-easy.env (contains admin password - content not printed)")

    # no INIT_* var exists for the masquerade device (wg-easy seeds "eth0"),
    # so lib/sh/wg-easy.sh patches it into wg-easy's db on the host - left
    # unset here, it auto-detects from the host's default route
    device = config.get("device")
    if device:
        write_text(out / "device", f"{device}\n", mode=0o644)
    else:
        (out / "device").unlink(missing_ok=True)

    # nothing in compose.yaml is config-driven (everything goes through
    # wg-easy.env), so it's copied verbatim
    compose_text = write_text(
        out / "compose.yaml", (DEFAULTS_DIR / "compose.yaml").read_text()
    )
    info(f"Generated wg-easy compose:\n{compose_text}")
