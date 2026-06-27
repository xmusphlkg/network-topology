from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db_models import CableLink, Device, Port, Topology, TopologyDevice, TopologyLayout
from ..schemas import (
    CableLinkRead,
    DeviceRead,
    LayoutNodeUpdate,
    PortRead,
    TopologyEdge,
    TopologyGraphRead,
    TopologyLayoutState,
    TopologyNode,
    TopologyRead,
)
from .profiles import profile_for_model, port_sort_key


def layout_key_for_topology(topology_id: int) -> str:
    return f"topology:{topology_id}"


async def build_topology_graph(session: AsyncSession, topology: Topology) -> TopologyGraphRead:
    device_ids_result = await session.execute(select(TopologyDevice.device_id).where(TopologyDevice.topology_id == topology.id))
    device_ids = list(device_ids_result.scalars().all())
    devices_result = await session.execute(
        select(Device)
        .where(Device.enabled.is_(True), Device.stale.is_(False), Device.id.in_(device_ids))
        .options(selectinload(Device.ports)),
    )
    devices = list(devices_result.scalars().all())
    devices.sort(key=lambda device: ({"switch": 0, "server": 1}.get(device.role, 3), device.display_name))

    ports = [port for device in devices for port in device.ports if not port.stale and not port.virtual]
    port_ids = [port.id for port in ports]

    links_result = await session.execute(
        select(CableLink).where(
            CableLink.endpoint_a_port_id.in_(port_ids),
            CableLink.endpoint_b_port_id.in_(port_ids),
        ),
    ) if port_ids else None
    links = list(links_result.scalars().all()) if links_result is not None else []

    layout_result = await session.execute(
        select(TopologyLayout).where(TopologyLayout.layout_key == layout_key_for_topology(topology.id)),
    )
    layout_rows = list(layout_result.scalars().all())
    layout_by_node = {layout.node_id: layout for layout in layout_rows}
    layout_viewport: dict | None = None
    for layout_row in layout_rows:
        if not layout_row.viewport_json:
            continue
        try:
            parsed = json.loads(layout_row.viewport_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            layout_viewport = parsed
            break

    role_indexes = {"switch": 0, "endpoint": 0}
    nodes: list[TopologyNode] = []
    for device in devices:
        role_key = "switch" if device.role == "switch" else "endpoint"
        role_index = role_indexes[role_key]
        role_indexes[role_key] += 1
        nodes.append(_build_node(device, role_index, layout_by_node.get(f"device-{device.id}")))

    device_by_port = {port.id: port.device_id for port in ports}
    port_by_id = {port.id: port for port in ports}
    edges: list[TopologyEdge] = []
    for link in links:
        source_device = device_by_port.get(link.endpoint_a_port_id)
        target_device = device_by_port.get(link.endpoint_b_port_id)
        if not source_device or not target_device:
            continue
        vlan = link.vlan_id if link.vlan_id is not None else link_vlan(port_by_id.get(link.endpoint_a_port_id), port_by_id.get(link.endpoint_b_port_id))
        stroke = vlan_color(vlan) if vlan is not None else link.color or "#4f8cff"
        edges.append(
            TopologyEdge(
                id=f"cable-{link.id}",
                source=f"device-{source_device}",
                target=f"device-{target_device}",
                sourceHandle=f"port-{link.endpoint_a_port_id}",
                targetHandle=f"port-{link.endpoint_b_port_id}",
                label=edge_label(link, vlan),
                style={"stroke": stroke, "strokeWidth": 3},
                data={
                    "linkId": link.id,
                    "cableNo": link.cable_no,
                    "notes": link.notes,
                    "vlan": vlan,
                    "vlanSource": "cable" if link.vlan_id is not None else "ports",
                },
            ),
        )

    return TopologyGraphRead(
        generatedAt=datetime.now(timezone.utc),
        topology_id=topology.id,
        topology_name=topology.name,
        summary=TopologyRead.model_validate(topology),
        layout=TopologyLayoutState(
            topologyId=topology.id,
            layoutKey=layout_key_for_topology(topology.id),
            viewport=layout_viewport,
            nodes=[
                LayoutNodeUpdate(
                    nodeId=layout.node_id,
                    x=layout.x,
                    y=layout.y,
                    width=layout.width,
                    height=layout.height,
                    groupName=layout.group_name,
                    hidden=layout.hidden,
                )
                for layout in layout_rows
            ],
        ),
        nodes=nodes,
        edges=edges,
        devices=[DeviceRead.model_validate(device) for device in devices],
        ports=[PortRead.model_validate(port) for port in ports],
        cableLinks=[CableLinkRead.model_validate(link) for link in links],
        switchPanels=[_build_switch_panel(device) for device in devices if device.role == "switch"],
    )


def _build_node(device: Device, index: int, layout: TopologyLayout | None) -> TopologyNode:
    if layout:
        position = {"x": layout.x, "y": layout.y}
    elif device.role == "switch":
        position = {"x": 80, "y": 80 + index * 260}
    else:
        position = {"x": 720 + (index % 3) * 300, "y": 80 + (index // 3) * 140}
    ports = sorted([port for port in device.ports if not port.virtual], key=lambda port: port_sort_key(port.name))
    return TopologyNode(
        id=f"device-{device.id}",
        type="switchNode" if device.role == "switch" else "endpointNode",
        position=position,
        data={
            "device": DeviceRead.model_validate(device).model_dump(by_alias=False),
            "ports": [PortRead.model_validate(port).model_dump(by_alias=False) for port in ports],
        },
    )


def _build_switch_panel(device: Device) -> dict:
    profile = profile_for_model(device.model)
    ports = sorted(device.ports, key=lambda port: port_sort_key(port.name))
    return {
        "deviceId": device.id,
        "modelKey": profile.key if profile else None,
        "displayName": device.display_name,
        "health": device.health,
        "ports": [PortRead.model_validate(port).model_dump(by_alias=False) for port in ports],
    }


def link_vlan(port_a: Port | None, port_b: Port | None) -> int | None:
    vlan_a = vlan_numbers(port_a.vlan_summary if port_a else None)
    vlan_b = vlan_numbers(port_b.vlan_summary if port_b else None)
    if vlan_a and vlan_b:
        common = sorted(vlan_a.intersection(vlan_b))
        if common:
            return common[0]
    if vlan_a:
        return sorted(vlan_a)[0]
    if vlan_b:
        return sorted(vlan_b)[0]
    return None


def edge_label(link: CableLink, vlan: int | None) -> str:
    base = link.label or link.cable_no
    vlan_text = f"VLAN {vlan}" if vlan is not None else None
    if base and vlan_text:
        return f"{base} · {vlan_text}"
    if base:
        return base
    if vlan_text:
        return vlan_text
    return f"线缆 #{link.id}"


def vlan_numbers(value: str | None) -> set[int]:
    if not value:
        return set()
    numbers: set[int] = set()
    for token in value.replace(",", " ").replace("/", " ").replace(";", " ").split():
        text = token.strip().lower().removeprefix("vlan").removeprefix("pvid")
        if "-" in text:
            start, _, end = text.partition("-")
            if start.isdigit() and end.isdigit():
                first = int(start)
                last = int(end)
                if 0 < first <= last <= 4094 and last - first <= 64:
                    numbers.update(range(first, last + 1))
                continue
        if text.isdigit():
            number = int(text)
            if 0 < number <= 4094:
                numbers.add(number)
    return numbers


def vlan_color(vlan: int | None) -> str | None:
    if vlan is None:
        return None
    palette = [
        "#2563eb",
        "#16a34a",
        "#dc2626",
        "#9333ea",
        "#ea580c",
        "#0891b2",
        "#be123c",
        "#4f46e5",
        "#0f766e",
        "#a16207",
    ]
    return palette[vlan % len(palette)]
