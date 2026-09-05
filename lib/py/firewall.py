from pathlib import Path
from typing import Any

from utils import info, write_text

WG_INTERFACE = "wg0"


def declare(config: dict[str, Any], general: dict[str, Any]) -> dict[str, Any]:
    nft_file_path = config.get("nft_file_path")
    if not nft_file_path:
        raise ValueError("firewall.nft_file_path is required")
    return {"config_file": {"path": nft_file_path}}


def _rules_from_registry(registry: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for name in sorted(registry):
        rule = registry[name].get("firewall_rule")
        if not rule:
            continue
        missing = [k for k in ("proto", "port") if k not in rule]
        if missing:
            raise ValueError(
                f"{name}: firewall_rule missing key(s): {', '.join(missing)}"
            )
        proto = rule["proto"]
        if proto not in ("tcp", "udp"):
            raise ValueError(
                f"{name}: firewall_rule.proto must be 'tcp' or 'udp', got '{proto}'"
            )
        lines.append(f"\t\t{proto} dport {rule['port']} accept # {name}")
    return lines


def _ruleset(general: dict[str, Any], registry: dict[str, Any]) -> str:
    wan_rules = _rules_from_registry(registry)

    ssh_port = general.get("ssh", {}).get("port")
    if ssh_port:
        wan_rules.append(f"\t\ttcp dport {ssh_port} accept # ssh")

    lines = [
        "#!/usr/sbin/nft -f",
        "",
        "flush ruleset",
        "",
        "table inet filter {",
        "\tchain input {",
        "\t\ttype filter hook input priority 0; policy drop;",
        "",
        "\t\tiif lo accept",
        "\t\tct state established,related accept",
        "\t\tct state invalid drop",
        "",
        "\t\t# WireGuard tunnel is fully trusted once connected - services",
        "\t\t# behind it don't need their own rule here",
        f'\t\tiifname "{WG_INTERFACE}" accept',
    ]
    if wan_rules:
        lines += [
            "",
            "\t\t# must be reachable from the WAN before/outside the tunnel",
            *wan_rules,
        ]
    lines += [
        "\t}",
        "}",
        "",
    ]
    return "\n".join(lines)


def render(
    config: dict[str, Any], general: dict[str, Any], registry: dict[str, Any], out: Path
) -> None:
    nft_file_path = config.get("nft_file_path")
    if not nft_file_path:
        raise ValueError("firewall.nft_file_path is required")

    ruleset_text = write_text(
        out / "nftables.conf", _ruleset(general, registry), mode=0o644
    )
    info(f"Generated nftables ruleset:\n{ruleset_text}")

    write_text(out / "install_path", f"{nft_file_path}\n", mode=0o644)
