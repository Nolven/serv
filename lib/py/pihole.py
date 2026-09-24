from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from utils import info, write_text, write_yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS_DIR = ROOT / "components" / "pihole"


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    host_ip = general.get("host_ip")
    if not host_ip:
        raise ValueError("general.host_ip is required by pihole")
    capabilities: dict[str, Any] = {
        "config_file": {
            "path": str(PurePosixPath(general["install"]) / "pihole" / "compose.yaml")
        },
        # port 53 is published on every host address, so peers reach it at
        # host_ip over the tunnel
        "dns_resolver": {"address": host_ip},
    }

    subdomain = config.get("subdomain")
    if not subdomain:
        return capabilities
    missing = [k for k in ("name", "port") if k not in subdomain]
    if missing:
        raise ValueError(
            f"pihole.subdomain missing required key(s): {', '.join(missing)}"
        )
    route: dict[str, Any] = {"subdomain": subdomain["name"], "port": subdomain["port"]}
    redir = subdomain.get("redir")
    if redir:
        route["redir"] = redir
    if subdomain.get("wan", False):
        route["wan"] = True
    capabilities["http_route"] = route
    return capabilities


def _public_hosts(general: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    """Every http_route's public address, answered with host_ip for peers.

    Publicly these resolve to the WAN address, where only a route's public
    paths are served - resolving them to host_ip over the tunnel lets peers
    reach the whole service under that same name.
    """
    hosts: list[str] = []
    for name in sorted(registry):
        public = (registry[name].get("http_route") or {}).get("public")
        if not public:
            continue
        wan_host = general.get("wan_host")
        if not wan_host:
            raise ValueError(
                f"{name}: http_route.public needs general.wan_host to be resolved"
            )
        hosts.append(f"{public['subdomain']}.{wan_host}")
    return hosts


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    admin_pass = config.get("admin_pass")
    upstream_dns = config.get("upstream_dns")
    port = config.get("subdomain", {}).get("port")
    apex_domain = general.get("apex_domain")
    host_ip = general.get("host_ip")

    missing = [
        label
        for label, value in (
            ("pihole.admin_pass", admin_pass),
            ("pihole.upstream_dns", upstream_dns),
            ("pihole.subdomain.port", port),
            ("general.apex_domain", apex_domain),
            ("general.host_ip", host_ip),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"pihole missing required config: {', '.join(missing)}")

    if isinstance(upstream_dns, str):
        upstream_dns = [upstream_dns]

    with open(DEFAULTS_DIR / "compose.yaml", "r") as f:
        compose: dict[str, Any] = yaml.safe_load(f)

    service = compose["services"]["pihole"]
    service["environment"]["FTLCONF_webserver_port"] = port
    service["environment"]["FTLCONF_dns_upstreams"] = ";".join(
        str(d) for d in upstream_dns
    )
    service["environment"]["FTLCONF_misc_dnsmasq_lines"] = ";".join(
        [f"address=/{apex_domain}/{host_ip}"]
        + [f"address=/{host}/{host_ip}" for host in _public_hosts(general, registry)]
    )
    service["ports"] = ["53:53/tcp", "53:53/udp", f"{port}:{port}/tcp"]

    compose_text = write_yaml(out / "compose.yaml", compose, mode=0o644)
    info(f"Generated pihole compose:\n{compose_text}")

    write_text(
        out / "pihole.env",
        f"FTLCONF_webserver_api_password={admin_pass}\n",
        mode=0o600,
    )
    info("Generated pihole.env (contains admin password - content not printed)")
