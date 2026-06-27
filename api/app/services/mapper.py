from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..config import Settings
from .mac import normalize_mac_address
from .profiles import profile_for_model, port_sort_key


@dataclass
class PortSnapshot:
    identity: str
    name: str
    if_index: int | None = None
    alias: str | None = None
    oper_status: str = "unknown"
    admin_status: str = "unknown"
    speed_mbps: float | None = None
    media: str | None = None
    mac_address: str | None = None
    port_role: str | None = None
    vlan_summary: str | None = None
    poe_status: str | None = None
    last_traffic_in_bps: float | None = None
    last_traffic_out_bps: float | None = None
    rx_errors: float | None = None
    tx_errors: float | None = None
    traffic_in_itemid: str | None = None
    traffic_out_itemid: str | None = None
    oper_itemid: str | None = None
    last_seen_at: datetime | None = None
    virtual: bool = False


@dataclass
class DeviceSnapshot:
    zabbix_hostid: str
    role: str
    display_name: str
    model: str | None = None
    mgmt_ip: str | None = None
    status: str = "unknown"
    health: str = "unknown"
    last_seen_at: datetime | None = None
    ports: list[PortSnapshot] = field(default_factory=list)


def map_zabbix_inventory(hosts: list[dict[str, Any]], items: list[dict[str, Any]], settings: Settings) -> list[DeviceSnapshot]:
    host_by_id = {str(host.get("hostid")): host for host in hosts if host.get("hostid")}
    items_by_host: dict[str, list[dict[str, Any]]] = {hostid: [] for hostid in host_by_id}
    for item in items:
        hostid = str(item.get("hostid") or "")
        if hostid in items_by_host:
            items_by_host[hostid].append(item)

    snapshots: list[DeviceSnapshot] = []
    for hostid, host in host_by_id.items():
        role = classify_host(host, settings)
        host_items = items_by_host.get(hostid, [])
        model = best_model(host, host_items)
        if role == "custom" and model_indicates_server(model):
            role = "server"
        ports = parse_ports(host_items)
        if not ports:
            continue
        snapshot = DeviceSnapshot(
            zabbix_hostid=hostid,
            role=role,
            display_name=str(host.get("name") or host.get("host") or f"host-{hostid}"),
            model=model,
            mgmt_ip=host_mgmt_ip(host),
            status="disabled" if str(host.get("status")) == "1" else "active",
            health=device_health_from_ports(ports),
            last_seen_at=latest_seen(host_items),
            ports=ports,
        )
        snapshots.append(snapshot)
    return snapshots


def classify_host(host: dict[str, Any], settings: Settings) -> str:
    text = host_text(host)
    if any(term in text for term in settings.switch_terms()):
        return "switch"
    if any(term in text for term in settings.server_terms()):
        return "server"
    inventory = host.get("inventory") or {}
    model = str(inventory.get("model") or inventory.get("type") or "")
    if profile_for_model(model) or any(token in text for token in ["s6220", "s5750", "rg-s"]):
        return "switch"
    if any(token in text for token in ["cisco", "nexus", "catalyst", "huawei", "h3c", "arista", "juniper", "dell networking", "mellanox", "sonic", "routeros"]):
        return "switch"
    if any(token in text for token in ["linux", "ubuntu", "debian", "centos", "windows", "server", "poweredge", "proliant", "esxi", "vmware"]):
        return "server"
    return "custom"


def host_text(host: dict[str, Any]) -> str:
    parts = [str(host.get("host") or ""), str(host.get("name") or "")]
    groups = host.get("groups") or host.get("hostgroups") or []
    parts.extend(str(group.get("name") or "") for group in groups)
    tags = host.get("tags") or []
    parts.extend(f"{tag.get('tag', '')}:{tag.get('value', '')}" for tag in tags)
    inventory = host.get("inventory") or {}
    parts.extend(str(inventory.get(key) or "") for key in ["type", "model", "os", "location"])
    return " ".join(parts).lower()


def host_mgmt_ip(host: dict[str, Any]) -> str | None:
    interfaces = host.get("interfaces") or []
    for iface in interfaces:
        ip = str(iface.get("ip") or "").strip()
        if ip:
            return ip
        dns = str(iface.get("dns") or "").strip()
        if dns:
            return dns
    return None


def best_model(host: dict[str, Any], items: list[dict[str, Any]]) -> str | None:
    inventory = host.get("inventory") or {}
    for key in ["model", "type", "os"]:
        value = clean_model_value(inventory.get(key))
        if value:
            return value
    for item in items:
        text = item_text(item)
        raw = clean_model_value(item.get("lastvalue"))
        if raw and ("sysdescr" in text or "system description" in text or "firmware" in text):
            return raw
    return None


def clean_model_value(value: Any) -> str | None:
    text = compact(str(value or ""))
    if text.lower() in {"", "null", "none", "n/a", "na", "unknown"}:
        return None
    return text


def model_indicates_server(model: str | None) -> bool:
    if not model:
        return False
    text = model.lower()
    return any(token in text for token in ["linux", "windows", "ubuntu", "debian", "centos", "server", "truenas", "pve", "vmware", "esxi"])


def parse_ports(items: list[dict[str, Any]]) -> list[PortSnapshot]:
    builders: dict[str, PortSnapshot] = {}
    pending_name_items: list[tuple[str, str]] = []

    for item in items:
        key = str(item.get("key_") or "")
        text = item_text(item)
        value = str(item.get("lastvalue") or "").strip()
        if not looks_like_interface_item(text, value):
            continue
        index = extract_if_index(key)
        name_from_value = interface_name_value(value) if is_name_item(text, value) else None
        name_from_key = clean_port_name_from_key(key)
        name = name_from_value or name_from_key
        if is_virtual_port_name(name or value or key):
            continue
        identity = f"ifindex:{index}" if index is not None else f"name:{normalize_port_name(name or value or key)}"
        port_virtual = is_virtual_port_name(name or "")
        port = builders.get(identity)
        if port is None:
            port = PortSnapshot(
                identity=identity,
                name=name or (f"ifIndex {index}" if index is not None else compact(value or key, 60)),
                virtual=port_virtual,
                if_index=index,
            )
            builders[identity] = port

        apply_item_to_port(port, item)
        seen = lastclock_datetime(item)
        if seen and (port.last_seen_at is None or seen > port.last_seen_at):
            port.last_seen_at = seen
        if name_from_value:
            pending_name_items.append((identity, name_from_value))

    for identity, name in pending_name_items:
        if is_virtual_port_name(name):
            builders.pop(identity, None)
            continue
        builders[identity].name = name
        builders[identity].virtual = False

    ports = [port for port in builders.values() if is_real_port(port)]
    for port in ports:
        if port.media is None:
            port.media = infer_media(port.name, port.speed_mbps)
        if port.port_role is None:
            port.port_role = infer_port_role(port.name)
    ports.sort(key=lambda port: port_sort_key(port.name))
    return ports


def apply_item_to_port(port: PortSnapshot, item: dict[str, Any]) -> None:
    text = item_text(item)
    raw = str(item.get("lastvalue") or "").strip()
    value = to_float(raw)
    itemid = str(item.get("itemid") or "") or None

    if is_name_item(text, raw):
        name = clean_port_name(raw)
        if name:
            port.name = name
            port.virtual = is_virtual_port_name(name)
        return
    if "ifalias" in text or "alias" in text or "description" in text or "接口描述" in text:
        if raw and not raw.isdigit():
            port.alias = compact(raw, 240)
        return
    if any(token in text for token in ["ifoperstatus", "operstatus", "operational status", "oper status", "运行状态"]):
        port.oper_status = normalize_status(raw)
        port.oper_itemid = itemid
        return
    if any(token in text for token in ["ifadminstatus", "adminstatus", "admin status", "administrative status", "管理状态"]):
        port.admin_status = normalize_status(raw)
        return
    if "ifspeed" in text or "ifhighspeed" in text or "speed" in text or "协商速率" in text:
        port.speed_mbps = normalize_speed_mbps(value, str(item.get("units") or ""), text)
        return
    if is_in_traffic_item(text):
        port.last_traffic_in_bps = value
        port.traffic_in_itemid = itemid
        return
    if is_out_traffic_item(text):
        port.last_traffic_out_bps = value
        port.traffic_out_itemid = itemid
        return
    if "ifinerrors" in text or "in errors" in text or "rx errors" in text:
        port.rx_errors = value
        return
    if "ifouterrors" in text or "out errors" in text or "tx errors" in text:
        port.tx_errors = value
        return
    if is_vlan_item(text):
        port.vlan_summary = compact(raw, 240) if raw else None
        return
    if "poe" in text:
        port.poe_status = compact(raw, 80) if raw else None
        return
    if "iftype" in text or "port type" in text or "端口类型" in text:
        if raw and not raw.isdigit():
            port.media = compact(raw, 80)
        return
    if is_mac_item(text):
        port.mac_address = normalize_mac_address(raw)


def looks_like_interface_item(text: str, value: str) -> bool:
    markers = [
        "net.if.",
        "net.if",
        "ifname",
        "ifdescr",
        "ifalias",
        "ifoperstatus",
        "operstatus",
        "ifadminstatus",
        "adminstatus",
        "ifspeed",
        "ifhighspeed",
        "ifphysaddress",
        "physaddress",
        "mac",
        "physical address",
        "硬件地址",
        "物理地址",
        "ifhcin",
        "ifhcout",
        "ifinerrors",
        "ifouterrors",
        "interface",
        "接口",
        "vlan",
        "pvid",
        "dot1q",
        "tagged",
        "untagged",
        "trunk",
    ]
    return any(marker in text for marker in markers) or bool(clean_port_name(value))


def is_name_item(text: str, value: str) -> bool:
    return (
        "ifname" in text
        or "ifdescr" in text
        or "interface name" in text
        or "接口名称" in text
    ) and bool(interface_name_value(value))


def interface_name_value(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text or text.isdigit():
        return None
    return clean_port_name(text) or compact(text, 60)


def is_in_traffic_item(text: str) -> bool:
    return any(token in text for token in ["ifhcin", "ifinoctets", "incoming", "bits received", "net.if.in", "入口流量", "上行"])


def is_out_traffic_item(text: str) -> bool:
    return any(token in text for token in ["ifhcout", "ifoutoctets", "outgoing", "bits sent", "net.if.out", "出口流量", "下行"])


def is_vlan_item(text: str) -> bool:
    return any(token in text for token in ["vlan", "pvid", "dot1q", "tagged", "untagged", "trunk"])


def is_mac_item(text: str) -> bool:
    return any(token in text for token in ["ifphysaddress", "physaddress", "mac address", "physical address", "硬件地址", "物理地址"])


def extract_if_index(key: str) -> int | None:
    bracket = re.search(r"\[(.*)\]", key)
    candidates = []
    if bracket:
        candidates.extend(re.findall(r"(?:^|[.,])(\d+)(?:$|[,\]])", bracket.group(1)))
    candidates.extend(re.findall(r"(?:if[A-Za-z]+\.|\.)(\d+)(?:\]?$|[,\]])", key))
    if candidates:
        return int(candidates[-1])
    return None


def clean_port_name_from_key(key: str) -> str | None:
    bracket = re.search(r"\[(.*)\]", key)
    if not bracket:
        return None
    for part in bracket.group(1).split(","):
        port = clean_port_name(part.strip().strip('"'))
        if port:
            return port
    return None


def clean_port_name(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if not text or text.isdigit():
        return None
    patterns = [
        r"\b(?:XGE|QXGE|GE|GI|GIGABITETHERNET|TENGIGABITETHERNET|TEN-GIGABITETHERNET|TWENTYFIVEGIGE|FORTYGIGE|HUNDREDGIGE|ETHERNET|ETH|ET|PORT-CHANNEL|PORTCHANNEL|ETH-TRUNK)\s*\d+(?:/\d+)*\b",
        r"\b(?:XE|GE|ET)-\d+/\d+/\d+(?::\d+)?\b",
        r"\b(?:ENP\d+S\d+F?\d*|ENS\d+F?\d*|ENO\d+|ENX[0-9A-F]+|EM\d+|ETH\d+|BOND\d+|BR\d+|IB\d+)\b",
        r"\b(?:MGMT|MANAGEMENT)\s*\d+(?:/\d+)*\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_port_label(match.group(0))
    if re.match(r"^[A-Za-z]+[A-Za-z-]*\d+/\d+(?:/\d+)?$", text):
        return normalize_port_label(text)
    return None


def normalize_port_label(value: str) -> str:
    text = re.sub(r"\s+", "", value.strip())
    replacements = {
        "GIGABITETHERNET": "GE",
        "TENGIGABITETHERNET": "XGE",
        "TEN-GIGABITETHERNET": "XGE",
        "TWENTYFIVEGIGE": "25GE",
        "FORTYGIGE": "QXGE",
        "HUNDREDGIGE": "HGE",
        "PORTCHANNEL": "Po",
        "PORT-CHANNEL": "Po",
        "ETH-TRUNK": "Eth-Trunk",
    }
    upper = text.upper()
    for src, dst in replacements.items():
        if upper.startswith(src):
            return dst + text[len(src):]
    return text


def normalize_port_name(value: str) -> str:
    return re.sub(r"[^a-z0-9/.-]+", "-", value.lower()).strip("-")[:120]


def normalize_status(value: str) -> str:
    text = value.strip().lower()
    mapping = {
        "1": "up",
        "2": "down",
        "3": "testing",
        "4": "unknown",
        "5": "dormant",
        "6": "not-present",
        "7": "lower-layer-down",
        "up": "up",
        "down": "down",
        "shutdown": "shutdown",
        "disabled": "shutdown",
    }
    return mapping.get(text, text or "unknown")


def normalize_speed_mbps(value: float | None, units: str, text: str) -> float | None:
    if value is None or value < 0:
        return None
    units_lower = units.lower()
    text_lower = text.lower()
    if "gbps" in units_lower:
        return value * 1000
    if "mbps" in units_lower:
        return value
    if "kbps" in units_lower:
        return value / 1000
    if "bps" in units_lower:
        return value / 1_000_000
    if "ifhighspeed" in text_lower:
        return value / 1_000_000 if value >= 1_000_000 else value
    if value >= 1_000_000:
        return value / 1_000_000
    return value


def infer_media(name: str, speed_mbps: float | None) -> str | None:
    upper = name.upper()
    if upper.startswith(("XGE", "QXGE", "TE", "25GE", "HGE", "XE-", "ET-", "ETHERNET")) or (speed_mbps and speed_mbps >= 10000):
        return "fiber"
    if upper.startswith(("GE", "GI", "GIGABITETHERNET")):
        return "copper"
    return None


def infer_port_role(name: str) -> str:
    upper = name.upper()
    if upper.startswith(("QXGE", "HGE", "ETH-TRUNK", "PORT-CHANNEL", "PO")):
        return "uplink"
    match = re.search(r"(\d+)(?!.*\d)", upper)
    if match and int(match.group(1)) >= 49:
        return "uplink"
    return "access"


def is_real_port(port: PortSnapshot) -> bool:
    if port.virtual:
        return False
    return bool(clean_port_name(port.name) or port.if_index is not None)


def is_virtual_port_name(name: str) -> bool:
    text = name.strip().lower()
    return bool(
        re.match(
            r"^(vlan|vwan)\d*[./:\-]?\w*|^(loopback|lo|docker|veth|virbr|tun|tap|wg|br\d*|bridge\d*)\b|^v\w{0,2}lan\d*[./:.-]?\w*$",
            text,
        )
        or re.match(r"^\w*?(vlan|vwan)\d*[./-]", text)
        or re.search(r"(?:^|[^a-z0-9])(vlan|vwan|vxlan)\d*[a-z0-9_.:@-]*", text)
        or re.search(r"(?:^|[^a-z0-9])interface\s+(vlan|vwan|vxlan)\d*", text)
    )


def device_health_from_ports(ports: list[PortSnapshot]) -> str:
    if not ports:
        return "unknown"
    if any(port.oper_status == "up" for port in ports):
        return "ok"
    if any(port.oper_status in {"down", "lower-layer-down"} for port in ports):
        return "warning"
    return "unknown"


def latest_seen(items: list[dict[str, Any]]) -> datetime | None:
    values = [dt for item in items if (dt := lastclock_datetime(item))]
    return max(values) if values else None


def lastclock_datetime(item: dict[str, Any]) -> datetime | None:
    try:
        clock = int(float(item.get("lastclock") or 0))
    except (TypeError, ValueError):
        return None
    if clock <= 0:
        return None
    return datetime.fromtimestamp(clock, timezone.utc)


def item_text(item: dict[str, Any]) -> str:
    return f"{item.get('key_', '')} {item.get('name', '')}".lower()


def to_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compact(value: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]
