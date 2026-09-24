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


def _public_host(
    name: str, route: dict[str, Any], config: dict[str, Any], general: dict[str, Any]
) -> str:
    public = route["public"]
    _require(name, "http_route.public", public, ("subdomain", "paths"))
    paths = public["paths"]
    if (
        not isinstance(paths, list)
        or not paths
        or not all(isinstance(p, str) and p.startswith("/") for p in paths)
    ):
        raise ValueError(
            f"{name}: http_route.public.paths must be a non-empty list of "
            "absolute path patterns (e.g. /shares/*)"
        )
    if route.get("wan", False):
        raise ValueError(
            f"{name}: http_route sets both wan and public - public already "
            "decides what the WAN sees; drop wan"
        )
    if not config.get("wan_enable", False):
        raise ValueError(
            f"{name}: http_route.public needs caddy.wan_enable: true - "
            "it is served on the WAN-facing listener"
        )
    if not config.get("https", False):
        raise ValueError(
            f"{name}: http_route.public needs caddy.https: true - "
            "its address gets a real Let's Encrypt certificate"
        )
    if not general.get("wan_host"):
        raise ValueError(f"{name}: http_route.public needs general.wan_host")
    return f"{public['subdomain']}.{general['wan_host']}"


# browsers outside the tunnel have never seen caddy's local CA, so a public
# address needs a publicly trusted certificate. TLS-ALPN on 443 only - port 80
# is never opened on the WAN, so the HTTP challenge could only time out
_ACME_TLS = [
    "\ttls {",
    "\t\tissuer acme {",
    "\t\t\tdisable_http_challenge",
    "\t\t}",
    "\t}",
]


def _public_blocks(
    name: str, host: str, route: dict[str, Any], host_ip: str
) -> list[str]:
    address = f"https://{host}"
    # the same address twice: caddy keeps sites with different binds on
    # separate listeners, so the tunnel gets the whole service while the WAN
    # listener only ever sees the allowed paths. Certificates are per hostname,
    # not per listener - the tls issuer goes on one block only, since two
    # policies for one name is a config error
    tunnel = [f"{address} {{", f"\tbind {host_ip}"]
    tunnel += _body(name, "http_route", route)
    tunnel += ["}", ""]
    wan = [
        f"{address} {{",
        *_ACME_TLS,
        f"\t@public path {' '.join(route['public']['paths'])}",
        "\thandle @public {",
        f"\t\treverse_proxy localhost:{route['port']}",
        "\t}",
        "\thandle {",
        "\t\trespond 404",
        "\t}",
        "}",
        "",
    ]
    return tunnel + wan


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
    lines = [f"\troot * {route['root']}"]
    if not route.get("cache", True):
        # must-revalidate alongside no-cache: the etag still gets cheap 304s,
        # but a stale copy is never served without asking first
        lines.append('\theader Cache-Control "no-cache, must-revalidate"')
    lines.append(f"\t{file_server}")
    return lines


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
            public_host = None
            if kind == "http_route" and route.get("public"):
                public_host = _public_host(name, route, config, general)

            public_address = f"https://{public_host}" if public_host else None
            for claim in filter(None, (address, public_address)):
                if claim in claimed:
                    raise ValueError(
                        f"{name}: {claim} is already served by '{claimed[claim]}' - "
                        "two components cannot claim the same address"
                    )
                claimed[claim] = name

            block = [f"{address} {{"]
            bind_line = _bind_line(
                name, route.get("wan", False), wan_enable, general["host_ip"]
            )
            if bind_line:
                block.append(bind_line)
            if public_host:
                # one canonical address: the service is reached (and builds
                # its own links) under its public name, over the tunnel too
                block.append(f"\tredir https://{public_host}{{uri}}")
            else:
                block += _body(name, kind, route)
            block += ["}", ""]
            lines += block

            if public_host:
                lines += _public_blocks(name, public_host, route, general["host_ip"])
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
