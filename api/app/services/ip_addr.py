from __future__ import annotations

import re

from .mac import extract_mac_address
from .mapper import is_virtual_port_name


PHYSICAL_INTERFACE_RE = re.compile(
    r"^(?:eth\d+|eno\d+|ens\d+\w*|enp\d+s\d+\w*|enx[0-9a-f]+|em\d+|p\d+p\d+|ib\d+|wan\d*|lan\d*|xge\d*|xe\d*|te\d*|ge\d*|gi\d*|idrac\d*|ipmi\d*|bmc\d*|ilo\d*)$",
    re.IGNORECASE,
)
VIRTUAL_INTERFACE_PREFIXES = (
    "bond",
    "br",
    "bridge",
    "cali",
    "cni",
    "docker",
    "dummy",
    "flannel",
    "gre",
    "gretap",
    "ip6tnl",
    "ipip",
    "ipvlan",
    "lxc",
    "macvlan",
    "podman",
    "ppp",
    "sit",
    "tap",
    "tailscale",
    "tun",
    "vboxnet",
    "veth",
    "virbr",
    "vmnet",
    "vti",
    "vxlan",
    "wg",
    "zt",
)
VIRTUAL_DETAIL_PREFIXES = (
    "bond ",
    "bridge ",
    "geneve ",
    "gretap ",
    "ip6tnl ",
    "ipip ",
    "ipvlan ",
    "macvlan ",
    "team ",
    "tun ",
    "veth ",
    "vlan ",
    "vrf ",
    "vxlan ",
    "wireguard ",
)


def parse_ip_addr_ports(output: str) -> list[dict]:
    ports: dict[str, dict] = {}
    current_name: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        brief = re.match(r"^\s*([A-Za-z0-9_.:@-]+)\s+(UP|DOWN|UNKNOWN|LOWERLAYERDOWN)\s+(.+)$", line)
        if brief and not re.match(r"^\s*\d+:", line):
            raw_name = brief.group(1)
            name = interface_base_name(raw_name)
            if is_physical_linux_interface(name, raw_name=raw_name):
                state = brief.group(2).lower()
                port = ports.setdefault(
                    name,
                    {
                        "name": name,
                        "alias": None,
                        "operStatus": "up" if state == "up" else "down" if state == "down" else "unknown",
                        "adminStatus": "up" if state == "up" else "down",
                        "media": infer_media(name),
                        "portRole": infer_server_port_role(name),
                    },
                )
                append_interface_details(port, brief.group(3))
            current_name = None
            continue

        header = re.match(r"^\s*\d+:\s+([^:\s]+):\s+<([^>]*)>(.*)$", line)
        if header:
            raw_name = header.group(1).strip()
            name = interface_base_name(raw_name)
            flags = {item.strip().upper() for item in header.group(2).split(",") if item.strip()}
            tail = header.group(3)
            current_name = name if is_physical_linux_interface(name, raw_name=raw_name, detail=tail) else None
            if current_name:
                port = ports.setdefault(
                    current_name,
                    {
                        "name": current_name,
                        "alias": None,
                        "operStatus": status_from_ip_addr(flags, tail),
                        "adminStatus": "up" if "UP" in flags else "down",
                        "media": infer_media(current_name),
                        "portRole": infer_server_port_role(current_name),
                    },
                )
                port["operStatus"] = status_from_ip_addr(flags, tail)
                port["adminStatus"] = "up" if "UP" in flags else "down"
                append_interface_details(port, line)
            continue

        if current_name:
            if is_virtual_interface_detail(line):
                ports.pop(current_name, None)
                current_name = None
                continue
            append_interface_details(ports[current_name], line)

    return list(ports.values())


def is_physical_linux_interface(name: str, *, raw_name: str | None = None, detail: str | None = None) -> bool:
    text = name.strip().lower()
    raw_text = (raw_name or name).strip().lower()
    if not text or text == "lo" or is_virtual_port_name(text):
        return False
    if "@" in raw_text or "." in text or ":" in raw_text:
        return False
    if text.startswith(VIRTUAL_INTERFACE_PREFIXES):
        return False
    if detail and is_virtual_interface_detail(detail):
        return False
    return bool(PHYSICAL_INTERFACE_RE.match(text))


def is_virtual_interface_detail(line: str) -> bool:
    text = line.strip().lower()
    if not text:
        return False
    return text.startswith(VIRTUAL_DETAIL_PREFIXES) or " link-netns" in f" {text}" or "link-netnsid" in text


def interface_base_name(name: str) -> str:
    return name.strip().split("@", 1)[0].rstrip(":")


def status_from_ip_addr(flags: set[str], tail: str) -> str:
    state_match = re.search(r"\bstate\s+(\S+)", tail, re.IGNORECASE)
    state = state_match.group(1).lower() if state_match else ""
    if state == "up" or "LOWER_UP" in flags:
        return "up"
    if state in {"down", "dormant"}:
        return "down"
    if "UP" in flags:
        return "unknown"
    return "down"


def append_interface_details(port: dict, line: str) -> None:
    mac_address = extract_mac_address(line)
    if mac_address:
        port["macAddress"] = mac_address
    append_address(port, line)


def append_address(port: dict, line: str) -> None:
    addresses = re.findall(r"\binet6?\s+([0-9a-fA-F:.]+/\d+)", line)
    if not addresses:
        addresses = re.findall(r"(?<![0-9A-Fa-f:.])((?:\d{1,3}\.){3}\d{1,3}/\d+|[0-9A-Fa-f:]*:[0-9A-Fa-f:.]+/\d+)", line)
    if not addresses:
        return
    existing = [item.strip() for item in str(port.get("alias") or "").split(",") if item.strip()]
    for address in addresses:
        if address not in existing:
            existing.append(address)
    port["alias"] = ", ".join(existing) if existing else None


def infer_server_port_role(name: str) -> str:
    text = name.lower()
    if text.startswith(("idrac", "ipmi", "bmc", "ilo")):
        return "management"
    return "access"


def infer_media(name: str) -> str:
    text = name.lower()
    if text.startswith(("ib", "xge", "xe", "te")):
        return "fiber"
    return "copper"
