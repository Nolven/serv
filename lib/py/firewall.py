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


def _tunnel_address_rule(host_ip: str | None) -> list[str]:
    """Only accept traffic for the tunnel's own address from the tunnel.

    Linux accepts a packet for any of its addresses on any interface, so
    without this a LAN device could route host_ip via this host's LAN address
    and reach every service that binds only host_ip - as soon as some port
    (e.g. 443) is opened for the WAN.
    """
    if not host_ip:
        return []
    family = "ip6" if ":" in host_ip else "ip"
    return [
        "",
        "\t\t# the tunnel address is only reachable through the tunnel - services",
        "\t\t# bound to it stay wg0-only even on ports opened for the WAN below",
        f'\t\tiifname != "{WG_INTERFACE}" {family} daddr {host_ip} drop',
    ]


def _ruleset(registry: dict[str, Any], host_ip: str | None) -> str:
    wan_rules = _rules_from_registry(registry)

    lines = [
        "#!/usr/sbin/nft -f",
        "",
        # scoped to our own table only - a global "flush ruleset" would also
        # wipe whatever iptables-nft has installed for wireguard's NAT/
        # FORWARD/DOCKER-USER rules (lib/sh/wireguard.sh), since both share
        # the same nf_tables backend on modern Debian.
        # "add" before "flush" so this file is self-sufficient on its own -
        # nftables.service reloads it directly on every boot (netfilter
        # state doesn't survive a reboot), with no help from firewall.sh
        "add table inet filter",
        "flush table inet filter",
        "",
        "table inet filter {",
        "\tchain input {",
        "\t\ttype filter hook input priority 0; policy drop;",
        "",
        "\t\tiif lo accept",
        "\t\tct state established,related accept",
        "\t\tct state invalid drop",
        *_tunnel_address_rule(host_ip),
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
        out / "nftables.conf",
        _ruleset(registry, general.get("host_ip")),
        mode=0o644,
    )
    info(f"Generated nftables ruleset:\n{ruleset_text}")

    write_text(out / "install_path", f"{nft_file_path}\n", mode=0o644)
