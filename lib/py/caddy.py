from pathlib import Path, PurePosixPath
from typing import Any

from utils import info, write_text


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    path = str(PurePosixPath(general["install"]) / "caddy" / "Caddyfile")
    capabilities: dict[str, Any] = {"config_file": {"path": path}}
    if config.get("wan_enable", False):
        capabilities["firewall_rule"] = {"proto": "tcp", "port": 443}

    fileserver = config.get("fileserver") or {}
    if fileserver.get("enable", False):
        if "subdomain" not in fileserver:
            raise ValueError("caddy.fileserver missing required key(s): subdomain")
        if "fileserver_root" not in general:
            raise ValueError("general.fileserver_root is required")
        # declared like any other static site so consumers (an index page, say)
        # see it through the registry instead of reading caddy's own config
        capabilities["static_site"] = {
            "subdomain": fileserver["subdomain"],
            "root": general["fileserver_root"],
            "browsable": fileserver.get("browsable", False),
            "wan": fileserver.get("wan", False),
        }
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


def _require(
    name: str, kind: str, route: dict[str, Any], keys: tuple[str, ...]
) -> None:
    missing = [k for k in keys if k not in route]
    if missing:
        raise ValueError(f"{name}: {kind} missing key(s): {', '.join(missing)}")


def _body(name: str, kind: str, route: dict[str, Any]) -> list[str]:
    if kind == "http_route":
        _require(name, kind, route, ("subdomain", "port"))
        lines = []
        redir = route.get("redir")
        if redir:
            lines.append(f"\tredir / {redir}")
        lines.append(f"\treverse_proxy localhost:{route['port']}")
        return lines

    _require(name, kind, route, ("root",))
    file_server = (
        "file_server browse" if route.get("browsable", False) else "file_server"
    )
    return [f"\troot * {route['root']}", f"\t{file_server}"]


def _site_blocks(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any]
) -> list[str]:
    for key in ("apex_domain", "host_ip"):
        if key not in general:
            raise ValueError(f"general.{key} is required")

    scheme = "https" if config.get("https", False) else "http"
    wan_enable = config.get("wan_enable", False)
    apex = general["apex_domain"]

    lines: list[str] = []
    claimed: dict[str, str] = {}
    for name in sorted(registry):
        # http_route is proxied to a port, static_site is served off disk;
        # both are just "an address caddy answers on", so they share this loop
        for kind in ("http_route", "static_site"):
            route = registry[name].get(kind)
            if not route:
                continue
            subdomain = route.get("subdomain")
            address = (
                f"{scheme}://{subdomain}.{apex}" if subdomain else f"{scheme}://{apex}"
            )
            if address in claimed:
                raise ValueError(
                    f"{name}: {address} is already served by '{claimed[address]}' - "
                    "two components cannot claim the same address"
                )
            claimed[address] = name

            block = [f"{address} {{"]
            bind_line = _bind_line(
                name, route.get("wan", False), wan_enable, general["host_ip"]
            )
            if bind_line:
                block.append(bind_line)
            block += _body(name, kind, route)
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
    lines += _site_blocks(config, general, registry)

    text = "\n".join(lines).rstrip("\n") + "\n"
    caddyfile_text = write_text(out / "Caddyfile", text, mode=0o644)
    info(f"Generated Caddyfile:\n{caddyfile_text}")

    if config.get("fileserver", {}).get("enable", False):
        write_text(
            out / "fileserver_root", f"{general['fileserver_root']}\n", mode=0o644
        )
