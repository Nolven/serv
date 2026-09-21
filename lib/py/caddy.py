from pathlib import Path, PurePosixPath
from typing import Any

from utils import info, write_text


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    path = str(PurePosixPath(general["install"]) / "caddy" / "Caddyfile")
    capabilities: dict[str, Any] = {"config_file": {"path": path}}
    if config.get("wan_enable", False):
        capabilities["firewall_rule"] = {"proto": "tcp", "port": 443}
    return capabilities


def _bind_line(name: str, wan: bool, wan_enable: bool, host_ip: str) -> str | None:
    if wan and not wan_enable:
        raise ValueError(
            f"{name}: wan is true but caddy.wan_enable is false - "
            "enable caddy.wan_enable to open it to WAN"
        )
    if wan:
        return None
    return f"\tbind {host_ip}"


def _fileserver_block(config: dict[str, Any], general: dict[str, Any]) -> list[str]:
    fileserver = config.get("fileserver", {})
    if not fileserver.get("enable", False):
        return []

    if "subdomain" not in fileserver:
        raise ValueError("caddy.fileserver missing required key(s): subdomain")
    if "apex_domain" not in general:
        raise ValueError("general.apex_domain is required")
    if "fileserver_root" not in general:
        raise ValueError("general.fileserver_root is required")
    if "host_ip" not in general:
        raise ValueError("general.host_ip is required")

    scheme = "https" if config.get("https", False) else "http"
    address = f"{scheme}://{fileserver['subdomain']}.{general['apex_domain']}"
    file_server = (
        "file_server browse" if fileserver.get("browsable", False) else "file_server"
    )

    block = [f"{address} {{"]
    bind_line = _bind_line(
        "caddy.fileserver",
        fileserver.get("wan", False),
        config.get("wan_enable", False),
        general["host_ip"],
    )
    if bind_line:
        block.append(bind_line)
    block += [
        f"\troot * {general['fileserver_root']}",
        f"\t{file_server}",
        "}",
        "",
    ]
    return block


def _reverse_proxy_blocks(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any]
) -> list[str]:
    if not registry:
        return []
    if "apex_domain" not in general:
        raise ValueError("general.apex_domain is required")
    if "host_ip" not in general:
        raise ValueError("general.host_ip is required")

    scheme = "https" if config.get("https", False) else "http"
    wan_enable = config.get("wan_enable", False)

    lines: list[str] = []
    for name in sorted(registry):
        route = registry[name].get("http_route")
        if not route:
            continue
        missing = [k for k in ("subdomain", "port") if k not in route]
        if missing:
            raise ValueError(f"{name}: http_route missing key(s): {', '.join(missing)}")
        address = f"{scheme}://{route['subdomain']}.{general['apex_domain']}"
        block = [f"{address} {{"]
        bind_line = _bind_line(name, route.get("wan", False), wan_enable, general["host_ip"])
        if bind_line:
            block.append(bind_line)
        redir = route.get("redir")
        if redir:
            block.append(f"\tredir / {redir}")
        block.append(f"\treverse_proxy localhost:{route['port']}")
        block += ["}", ""]
        lines += block
    return lines


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    https = config.get("https", False)
    if https:
        lines = ["{", "\tlocal_certs", "}", ""]
    else:
        lines = ["{", "\tauto_https off", "}", ""]
    lines += _fileserver_block(config, general)
    lines += _reverse_proxy_blocks(config, general, registry)

    text = "\n".join(lines).rstrip("\n") + "\n"
    caddyfile_text = write_text(out / "Caddyfile", text, mode=0o644)
    info(f"Generated Caddyfile:\n{caddyfile_text}")

    if config.get("fileserver", {}).get("enable", False):
        write_text(
            out / "fileserver_root", f"{general['fileserver_root']}\n", mode=0o644
        )
