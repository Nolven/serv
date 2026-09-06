from pathlib import Path, PurePosixPath
from typing import Any

from utils import info, write_text


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    path = str(PurePosixPath(general["install"]) / "caddy" / "Caddyfile")
    return {"config_file": {"path": path}}


def _fileserver_block(config: dict[str, Any], general: dict[str, Any]) -> list[str]:
    fileserver = config.get("fileserver", {})
    if not fileserver.get("enable", False):
        return []

    missing = [k for k in ("subdomain", "port") if k not in fileserver]
    if missing:
        raise ValueError(
            f"caddy.fileserver missing required key(s): {', '.join(missing)}"
        )
    if "apex_domain" not in general:
        raise ValueError("general.apex_domain is required")
    if "fileserver_root" not in general:
        raise ValueError("general.fileserver_root is required")

    address = f"http://{fileserver['subdomain']}.{general['apex_domain']}:{fileserver['port']}"
    file_server = (
        "file_server browse" if fileserver.get("browsable", False) else "file_server"
    )

    return [
        f"{address} {{",
        f"\troot * {general['fileserver_root']}",
        f"\t{file_server}",
        "}",
        "",
    ]


def _reverse_proxy_blocks(
    general: dict[str, Any], registry: dict[str, Any]
) -> list[str]:
    if not registry:
        return []
    if "apex_domain" not in general:
        raise ValueError("general.apex_domain is required")

    lines: list[str] = []
    for name in sorted(registry):
        route = registry[name].get("http_route")
        if not route:
            continue
        missing = [k for k in ("subdomain", "port") if k not in route]
        if missing:
            raise ValueError(f"{name}: http_route missing key(s): {', '.join(missing)}")
        address = f"http://{route['subdomain']}.{general['apex_domain']}"
        block = [f"{address} {{"]
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
    lines = ["{", "\tauto_https off", "}", ""]
    lines += _fileserver_block(config, general)
    lines += _reverse_proxy_blocks(general, registry)

    text = "\n".join(lines).rstrip("\n") + "\n"
    caddyfile_text = write_text(out / "Caddyfile", text, mode=0o644)
    info(f"Generated Caddyfile:\n{caddyfile_text}")

    if config.get("fileserver", {}).get("enable", False):
        write_text(
            out / "fileserver_root", f"{general['fileserver_root']}\n", mode=0o644
        )
