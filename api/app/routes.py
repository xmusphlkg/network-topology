from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .clients.zabbix import ZabbixClient
from .config import Settings, get_settings
from .database import get_session
from .db_models import CableLink, Device, Port, Topology, TopologyDevice, TopologyLayout, ZabbixSyncRun
from .schemas import (
    CableLinkCreate,
    CableLinkRead,
    CableLinkUpdate,
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
    LayoutUpdate,
    PortCreate,
    PortRead,
    PortSeries,
    PortUpdate,
    SeriesPoint,
    SyncRunRead,
    SyncStatus,
    LayoutNodeUpdate,
    TopologyCreate,
    TopologyDeviceIds,
    TopologyGraphRead,
    TopologyImportRequest,
    TopologyRead,
    TopologyUpdate,
    ZabbixDiscoveredDevice,
    TopologyEdge,
    TopologyNode,
)
from .services.profiles import PROFILES, port_sort_key, profile_for_model
from .services.sync import collect_zabbix_snapshots, run_zabbix_sync, run_zabbix_sync_from_snapshots, upsert_zabbix_snapshots

router = APIRouter(prefix="/api")


def zabbix_from_request(request: Request) -> ZabbixClient:
    return request.app.state.zabbix


def sync_lock_from_request(request: Request) -> asyncio.Lock:
    lock = getattr(request.app.state, "sync_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.sync_lock = lock
    return lock


async def run_zabbix_sync_serialized(
    request: Request,
    session: AsyncSession,
    zabbix: ZabbixClient,
    settings: Settings,
) -> ZabbixSyncRun:
    async with sync_lock_from_request(request):
        return await run_zabbix_sync(session, zabbix, settings)


async def run_zabbix_sync_from_snapshots_serialized(
    request: Request,
    session: AsyncSession,
    settings: Settings,
    snapshots: list,
) -> ZabbixSyncRun:
    async with sync_lock_from_request(request):
        return await run_zabbix_sync_from_snapshots(session, settings, snapshots)


def layout_key_for_topology(topology_id: int) -> str:
    return f"topology:{topology_id}"


async def get_topology_by_id(session: AsyncSession, topology_id: int) -> Topology:
    result = await session.execute(select(Topology).where(Topology.id == topology_id))
    topology = result.scalar_one_or_none()
    if topology is None:
        raise HTTPException(status_code=404, detail="Topology not found")
    return topology


async def get_default_topology(session: AsyncSession) -> Topology:
    result = await session.execute(select(Topology).where(Topology.is_default.is_(True)))
    topology = result.scalar_one_or_none()
    if topology is None:
        result = await session.execute(select(Topology).order_by(Topology.created_at))
        topology = result.scalar_one_or_none()
    if topology is None:
        topology = Topology(name="默认拓扑", is_default=True)
        session.add(topology)
        await session.flush()
        await session.commit()
    return topology


async def get_topology_ids_for_graph(session: AsyncSession, topology_id: int) -> list[int]:
    result = await session.execute(
        select(TopologyDevice.device_id).where(TopologyDevice.topology_id == topology_id),
    )
    return list(result.scalars().all())


async def attach_devices_to_topology(
    session: AsyncSession,
    topology: Topology,
    device_ids: list[int],
) -> int:
    if not device_ids:
        return 0
    existing = await session.execute(
        select(TopologyDevice.device_id).where(
            TopologyDevice.topology_id == topology.id,
            TopologyDevice.device_id.in_(device_ids),
        ),
    )
    already = set(existing.scalars().all())
    created = 0
    for device_id in dict.fromkeys(device_ids):
        if device_id in already:
            continue
        session.add(TopologyDevice(topology_id=topology.id, device_id=device_id))
        already.add(device_id)
        created += 1
    if created:
        await session.flush()
    return created


async def seed_default_memberships(session: AsyncSession, topology: Topology) -> None:
    if not topology.is_default:
        return
    existing = set(await get_topology_ids_for_graph(session, topology.id))
    if existing:
        return
    result = await session.execute(select(Device.id).where(Device.enabled.is_(True)))
    all_device_ids = list(result.scalars().all())
    if not all_device_ids:
        return
    for device_id in all_device_ids:
        session.add(TopologyDevice(topology_id=topology.id, device_id=device_id))
    await session.flush()
    await session.commit()


async def hydrate_topology_counts(session: AsyncSession, topology: Topology) -> Topology:
    await session.refresh(topology)
    result = await session.execute(select(func.count(TopologyDevice.id)).where(TopologyDevice.topology_id == topology.id))
    topology.device_count = result.scalar_one() or 0
    return topology


def clean_required_text(value: object, detail: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail=detail)
    return text


async def ensure_topology_name_available(session: AsyncSession, name: str, current_id: int | None = None) -> None:
    stmt = select(Topology.id).where(Topology.name == name)
    if current_id is not None:
        stmt = stmt.where(Topology.id != current_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Topology name already exists")


async def ensure_zabbix_hostid_available(session: AsyncSession, hostid: str | None, current_id: int | None = None) -> None:
    if not hostid:
        return
    stmt = select(Device.id).where(Device.zabbix_hostid == hostid)
    if current_id is not None:
        stmt = stmt.where(Device.id != current_id)
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Zabbix host already exists")


def normalized_port_create_items(ports: list[PortCreate]) -> list[tuple[PortCreate, str]]:
    seen: set[str] = set()
    normalized: list[tuple[PortCreate, str]] = []
    for item in ports:
        name = clean_required_text(item.name, "Port name is required")
        identity = manual_port_identity(name)
        if identity in seen:
            raise HTTPException(status_code=409, detail="Duplicate port names in request")
        seen.add(identity)
        normalized.append((item, name))
    return normalized


@router.get("/devices", response_model=list[DeviceRead])
async def devices(
    role: str | None = None,
    search: str | None = None,
    topology_id: int | None = Query(None, alias="topologyId"),
    include_disabled: bool = Query(False, alias="includeDisabled"),
    session: AsyncSession = Depends(get_session),
) -> list[Device]:
    stmt = select(Device)
    if role:
        stmt = stmt.where(Device.role == role)
    if topology_id is not None:
        await get_topology_by_id(session, topology_id)
        stmt = (
            stmt.join(TopologyDevice, TopologyDevice.device_id == Device.id)
            .where(TopologyDevice.topology_id == topology_id)
        )
    if not include_disabled:
        stmt = stmt.where(Device.enabled.is_(True))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Device.display_name.like(like), Device.model.like(like), Device.mgmt_ip.like(like)))
    stmt = stmt.order_by(Device.role, Device.display_name)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/device-profiles")
async def device_profiles() -> list[dict]:
    return [
        {
            "key": profile.key,
            "models": list(profile.models),
            "portCount": len(profile.ports),
            "ports": [
                {
                    "name": port.name,
                    "media": port.media,
                    "speedMbps": port.speed_mbps,
                    "role": port.role,
                    "row": port.row,
                    "order": port.order,
                }
                for port in profile.ports
            ],
        }
        for profile in PROFILES
    ]


@router.get("/topologies", response_model=list[TopologyRead])
async def topologies(session: AsyncSession = Depends(get_session)) -> list[Topology]:
    result = await session.execute(
        select(Topology).order_by(Topology.is_default.desc(), Topology.created_at)
    )
    items = list(result.scalars().all())
    if not items:
        topology = Topology(name="默认拓扑", is_default=True)
        session.add(topology)
        await session.flush()
        items = [topology]
        await session.commit()
    counts = await session.execute(
        select(
            Topology.id,
            func.count(TopologyDevice.id),
        ).outerjoin(TopologyDevice, Topology.id == TopologyDevice.topology_id).group_by(Topology.id),
    )
    count_map = {topology_id: count for topology_id, count in counts.all()}
    for item in items:
        item.device_count = count_map.get(item.id, 0)
    return items


@router.post("/topologies", response_model=TopologyRead)
async def create_topology(
    payload: TopologyCreate,
    session: AsyncSession = Depends(get_session),
) -> Topology:
    name = clean_required_text(payload.name, "Topology name is required")
    await ensure_topology_name_available(session, name)
    if payload.isDefault:
        await session.execute(update(Topology).values(is_default=False))
    topology = Topology(
        name=name,
        description=payload.description,
        is_default=payload.isDefault,
    )
    session.add(topology)
    await session.flush()
    topology.device_count = 0
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.patch("/topologies/{topology_id}", response_model=TopologyRead)
async def update_topology(
    topology_id: int,
    payload: TopologyUpdate,
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        data["name"] = clean_required_text(data["name"], "Topology name is required")
        await ensure_topology_name_available(session, data["name"], current_id=topology.id)
    field_map = {"isDefault": "is_default"}
    for key, value in data.items():
        setattr(topology, field_map.get(key, key), value)
    if payload.isDefault:
        await session.execute(update(Topology).where(Topology.id != topology.id).values(is_default=False))
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.post("/topologies/{topology_id}/devices", response_model=TopologyRead)
async def link_devices_to_topology(
    topology_id: int,
    payload: TopologyDeviceIds,
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    if payload.deviceIds:
        result = await session.execute(select(Device.id).where(Device.id.in_(payload.deviceIds)))
        existing_ids = [device_id for device_id in result.scalars().all()]
        if not existing_ids:
            raise HTTPException(status_code=400, detail="No valid device ids")
        await attach_devices_to_topology(session, topology, existing_ids)
        await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.get("/zabbix/discovered-devices", response_model=list[ZabbixDiscoveredDevice])
async def discovered_zabbix_devices(
    topology_id: int | None = Query(None, alias="topologyId"),
    session: AsyncSession = Depends(get_session),
    zabbix: ZabbixClient = Depends(zabbix_from_request),
    settings: Settings = Depends(get_settings),
) -> list[ZabbixDiscoveredDevice]:
    if not settings.zabbix_configured():
        raise HTTPException(status_code=503, detail="Zabbix credentials are not configured")
    topology = await (get_default_topology(session) if topology_id is None else get_topology_by_id(session, topology_id))
    try:
        snapshots = await collect_zabbix_snapshots(zabbix, settings)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Zabbix discovery failed: {exc}") from exc
    member_ids = await get_topology_ids_for_graph(session, topology.id)
    if member_ids:
        exists = await session.execute(
            select(Device.id, Device.zabbix_hostid).where(Device.id.in_(member_ids), Device.zabbix_hostid.is_not(None)),
        )
        synced_hostids = {row[1] for row in exists.all()}
    else:
        synced_hostids = set()
    return [
        ZabbixDiscoveredDevice(
            zabbixHostid=snapshot.zabbix_hostid,
            displayName=snapshot.display_name,
            role=snapshot.role,
            model=snapshot.model,
            mgmtIp=snapshot.mgmt_ip,
            portCount=len(snapshot.ports),
            synced=snapshot.zabbix_hostid in synced_hostids,
        )
        for snapshot in snapshots
    ]


@router.post("/topologies/{topology_id}/sync-and-import", response_model=TopologyRead)
async def sync_and_import_topology(
    topology_id: int,
    payload: TopologyImportRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    zabbix: ZabbixClient = Depends(zabbix_from_request),
    settings: Settings = Depends(get_settings),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    if not settings.zabbix_configured():
        raise HTTPException(status_code=503, detail="Zabbix credentials are not configured")
    snapshots = await collect_zabbix_snapshots(zabbix, settings)
    discovered_ids = {snapshot.zabbix_hostid for snapshot in snapshots}
    selected = set(payload.hostids) if payload.hostids else discovered_ids
    if payload.hostids:
        selected = {hostid for hostid in discovered_ids if hostid in payload.hostids}
        if not selected:
            raise HTTPException(status_code=400, detail="No selected host is currently discoverable")
    if not discovered_ids:
        raise HTTPException(status_code=400, detail="No discoverable host in Zabbix")
    run = await run_zabbix_sync_from_snapshots_serialized(request, session, settings, snapshots)
    if run.status != "success":
        raise HTTPException(status_code=500, detail=run.error_message or "Zabbix sync failed")
    result = await session.execute(select(Device.id).where(Device.zabbix_hostid.in_(selected)))
    device_ids = [device_id for device_id in result.scalars().all()]
    if not device_ids:
        raise HTTPException(status_code=400, detail="No discovered host selected")
    await attach_devices_to_topology(session, topology, device_ids)
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.post("/devices", response_model=DeviceRead)
async def create_device(payload: DeviceCreate, session: AsyncSession = Depends(get_session)) -> Device:
    display_name = clean_required_text(payload.displayName, "Device display name is required")
    zabbix_hostid = clean_optional_str(payload.zabbixHostid)
    await ensure_zabbix_hostid_available(session, zabbix_hostid)
    port_items = normalized_port_create_items(payload.ports)
    device = Device(
        source=payload.source,
        zabbix_hostid=zabbix_hostid,
        role=payload.role,
        model=payload.model,
        mgmt_ip=payload.mgmtIp,
        display_name=display_name,
        status="manual",
        health="unknown",
        enabled=payload.enabled,
        stale=False,
    )
    session.add(device)
    await session.flush()
    for item, name in port_items:
        session.add(port_from_create(device.id, item, name=name))
    topology = await (get_default_topology(session) if payload.topologyId is None else get_topology_by_id(session, payload.topologyId))
    await attach_devices_to_topology(session, topology, [device.id])
    await session.commit()
    await session.refresh(device)
    return device


@router.patch("/devices/{device_id}", response_model=DeviceRead)
async def update_device(device_id: int, payload: DeviceUpdate, session: AsyncSession = Depends(get_session)) -> Device:
    device = await get_device_or_404(session, device_id)
    data = payload.model_dump(exclude_unset=True)
    if "displayName" in data:
        data["displayName"] = clean_required_text(data["displayName"], "Device display name is required")
    if "zabbixHostid" in data:
        data["zabbixHostid"] = clean_optional_str(data["zabbixHostid"])
        await ensure_zabbix_hostid_available(session, data["zabbixHostid"], current_id=device.id)
    field_map = {
        "displayName": "display_name",
        "zabbixHostid": "zabbix_hostid",
        "mgmtIp": "mgmt_ip",
    }
    for key, value in data.items():
        setattr(device, field_map.get(key, key), value)
    await session.commit()
    await session.refresh(device)
    return device


@router.delete("/devices/{device_id}")
async def delete_device(device_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    device = await get_device_or_404(session, device_id)
    ports_result = await session.execute(select(Port.id).where(Port.device_id == device.id))
    port_ids = list(ports_result.scalars().all())
    if port_ids:
        await session.execute(
            delete(CableLink).where(
                or_(
                    CableLink.endpoint_a_port_id.in_(port_ids),
                    CableLink.endpoint_b_port_id.in_(port_ids),
                )
            )
        )
    await session.execute(delete(TopologyDevice).where(TopologyDevice.device_id == device.id))
    await session.delete(device)
    await session.commit()
    return {"ok": True}


@router.get("/devices/{device_id}/ports", response_model=list[PortRead])
async def device_ports(device_id: int, session: AsyncSession = Depends(get_session)) -> list[Port]:
    await get_device_or_404(session, device_id)
    result = await session.execute(select(Port).where(Port.device_id == device_id))
    ports = list(result.scalars().all())
    return sorted(ports, key=lambda port: port_sort_key(port.name))


@router.post("/devices/{device_id}/ports", response_model=PortRead)
async def create_port(device_id: int, payload: PortCreate, session: AsyncSession = Depends(get_session)) -> Port:
    device = await get_device_or_404(session, device_id)
    name = clean_required_text(payload.name, "Port name is required")
    identity = manual_port_identity(name)
    existing = await session.execute(select(Port.id).where(Port.device_id == device_id, Port.identity == identity))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Port already exists on this device")
    port = port_from_create(device_id, payload, name=name)
    session.add(port)
    device.enabled = True
    device.stale = False
    if device.health == "stale":
        device.health = "unknown"
    await session.commit()
    await session.refresh(port)
    return port


@router.delete("/ports/{port_id}")
async def delete_port(port_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    port = await get_port_or_404(session, port_id)
    await session.execute(
        delete(CableLink).where(
            or_(
                CableLink.endpoint_a_port_id == port.id,
                CableLink.endpoint_b_port_id == port.id,
            )
        )
    )
    await session.delete(port)
    await session.commit()
    return {"ok": True}


@router.get("/ports", response_model=list[PortRead])
async def ports(
    device_id: int | None = Query(None, alias="deviceId"),
    topology_id: int | None = Query(None, alias="topologyId"),
    status: str | None = Query(None),
    include_stale: bool = Query(True, alias="includeStale"),
    limit: int | None = Query(None, ge=1),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Port]:
    stmt = select(Port)
    if device_id:
        stmt = stmt.where(Port.device_id == device_id)
    if topology_id is not None:
        await get_topology_by_id(session, topology_id)
        stmt = stmt.join(TopologyDevice, TopologyDevice.device_id == Port.device_id).where(TopologyDevice.topology_id == topology_id)
    if status == "stale":
        stmt = stmt.where(Port.stale.is_(True))
    elif status:
        stmt = stmt.where(Port.oper_status == status)
    if not include_stale and status != "stale":
        stmt = stmt.where(Port.stale.is_(False))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Port.name.like(like), Port.alias.like(like), Port.vlan_summary.like(like)))
    stmt = stmt.order_by(Port.device_id, Port.name)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.patch("/ports/{port_id}", response_model=PortRead)
async def update_port(port_id: int, payload: PortUpdate, session: AsyncSession = Depends(get_session)) -> Port:
    port = await get_port_or_404(session, port_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        name = clean_required_text(data["name"], "Port name is required")
        data["name"] = name
        if port.source == "manual":
            identity = manual_port_identity(name)
            if identity != port.identity:
                existing = await session.execute(
                    select(Port.id).where(Port.device_id == port.device_id, Port.identity == identity, Port.id != port.id)
                )
                if existing.scalar_one_or_none() is not None:
                    raise HTTPException(status_code=409, detail="Port already exists on this device")
                port.identity = identity
    field_map = {
        "ifIndex": "if_index",
        "operStatus": "oper_status",
        "adminStatus": "admin_status",
        "speedMbps": "speed_mbps",
        "portRole": "port_role",
        "vlanSummary": "vlan_summary",
        "poeStatus": "poe_status",
    }
    for key, value in data.items():
        setattr(port, field_map.get(key, key), value)
    await session.commit()
    await session.refresh(port)
    return port


@router.get("/topology", response_model=TopologyGraphRead)
async def topology(
    topologyId: int | None = Query(None, alias="topologyId"),
    session: AsyncSession = Depends(get_session),
) -> TopologyGraphRead:
    topology = await (get_default_topology(session) if topologyId is None else get_topology_by_id(session, topologyId))
    await seed_default_memberships(session, topology)
    device_ids = await get_topology_ids_for_graph(session, topology.id)
    devices_result = await session.execute(
        select(Device)
        .where(Device.enabled.is_(True), Device.stale.is_(False), Device.id.in_(device_ids))
        .options(selectinload(Device.ports)),
    )
    devices = list(devices_result.scalars().all())
    role_order = {"switch": 0, "server": 1, "custom": 2}
    devices.sort(key=lambda device: (role_order.get(device.role, 3), device.display_name))
    ports = [port for device in devices for port in device.ports if not port.stale]
    port_ids = [port.id for port in ports]
    if port_ids:
        links_result = await session.execute(
            select(CableLink).where(
                CableLink.endpoint_a_port_id.in_(port_ids),
                CableLink.endpoint_b_port_id.in_(port_ids),
            ),
        )
        links = list(links_result.scalars().all())
    else:
        links = []
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
    nodes = []
    for device in devices:
        role_key = "switch" if device.role == "switch" else "endpoint"
        role_index = role_indexes[role_key]
        role_indexes[role_key] += 1
        nodes.append(build_node(device, role_index, layout_by_node.get(f"device-{device.id}")))
    device_by_port = {port.id: port.device_id for port in ports}
    edges: list[TopologyEdge] = []
    for link in links:
        source_device = device_by_port.get(link.endpoint_a_port_id)
        target_device = device_by_port.get(link.endpoint_b_port_id)
        if not source_device or not target_device:
            continue
        edges.append(
            TopologyEdge(
                id=f"cable-{link.id}",
                source=f"device-{source_device}",
                target=f"device-{target_device}",
                sourceHandle=f"port-{link.endpoint_a_port_id}",
                targetHandle=f"port-{link.endpoint_b_port_id}",
                label=link.label or link.cable_no,
                style={"stroke": link.color or "#4f8cff", "strokeWidth": 2},
                data={"linkId": link.id, "cableNo": link.cable_no, "notes": link.notes},
            )
        )

    return TopologyGraphRead(
        generatedAt=datetime.now(timezone.utc),
        topology_id=topology.id,
        topology_name=topology.name,
        summary=TopologyRead.model_validate(await hydrate_topology_counts(session, topology)),
        nodes=nodes,
        edges=edges,
        devices=[DeviceRead.model_validate(device) for device in devices],
        ports=[PortRead.model_validate(port) for port in ports],
        cableLinks=[CableLinkRead.model_validate(link) for link in links],
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
        switchPanels=[switch_panel(device) for device in devices if device.role == "switch"],
    )


@router.get("/topologies/{topology_id}/json-export")
async def export_topology_json(topology_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    topology = await get_topology_by_id(session, topology_id)
    device_ids = await get_topology_ids_for_graph(session, topology.id)
    devices_result = await session.execute(
        select(Device)
        .where(Device.id.in_(device_ids))
        .options(selectinload(Device.ports)),
    )
    devices = list(devices_result.scalars().all())
    ports = [port for device in devices for port in device.ports]
    port_by_id = {port.id: port for port in ports}
    device_by_id = {device.id: device for device in devices}
    port_ids = list(port_by_id)
    if port_ids:
        links_result = await session.execute(
            select(CableLink).where(
                CableLink.endpoint_a_port_id.in_(port_ids),
                CableLink.endpoint_b_port_id.in_(port_ids),
            ),
        )
        links = list(links_result.scalars().all())
    else:
        links = []
    layout_result = await session.execute(
        select(TopologyLayout).where(TopologyLayout.layout_key == layout_key_for_topology(topology.id)),
    )
    layouts = list(layout_result.scalars().all())
    layout_viewport: dict | None = None
    for layout in layouts:
        if not layout.viewport_json:
            continue
        try:
            candidate = json.loads(layout.viewport_json)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(candidate, dict):
            layout_viewport = candidate
            break
    return {
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "topology": TopologyRead.model_validate(await hydrate_topology_counts(session, topology)).model_dump(mode="json", by_alias=False),
        "devices": [
            {
                **DeviceRead.model_validate(device).model_dump(mode="json", by_alias=False),
                "ports": [PortRead.model_validate(port).model_dump(mode="json", by_alias=False) for port in sorted(device.ports, key=lambda port: port_sort_key(port.name))],
            }
            for device in devices
        ],
        "cableLinks": [
            {
                **CableLinkRead.model_validate(link).model_dump(mode="json", by_alias=False),
                "endpointA": export_endpoint_ref(link.endpoint_a_port_id, port_by_id, device_by_id),
                "endpointB": export_endpoint_ref(link.endpoint_b_port_id, port_by_id, device_by_id),
            }
            for link in links
        ],
        "layout": {
            "layoutKey": layout_key_for_topology(topology.id),
            "viewport": layout_viewport,
            "nodes": [
                {
                    "nodeId": layout.node_id,
                    "x": layout.x,
                    "y": layout.y,
                    "width": layout.width,
                    "height": layout.height,
                    "groupName": layout.group_name,
                    "hidden": layout.hidden,
                }
                for layout in layouts
            ],
        },
    }


@router.post("/topologies/{topology_id}/json-import", response_model=TopologyRead)
async def import_topology_json(
    topology_id: int,
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    await import_topology_payload(session, topology, payload)
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.patch("/topology/layout")
async def save_layout(payload: LayoutUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    for node in payload.nodes:
        result = await session.execute(
            select(TopologyLayout).where(TopologyLayout.layout_key == payload.layoutKey, TopologyLayout.node_id == node.nodeId)
        )
        layout = result.scalar_one_or_none()
        if layout is None:
            layout = TopologyLayout(layout_key=payload.layoutKey, node_id=node.nodeId)
            session.add(layout)
        layout.x = node.x
        layout.y = node.y
        layout.width = node.width
        layout.height = node.height
        layout.group_name = node.groupName
        layout.hidden = node.hidden
        layout.viewport_json = json.dumps(payload.viewport) if payload.viewport is not None else layout.viewport_json
    if payload.viewport is not None and not payload.nodes:
        layout_result = await session.execute(select(TopologyLayout).where(TopologyLayout.layout_key == payload.layoutKey))
        for layout in layout_result.scalars().all():
            layout.viewport_json = json.dumps(payload.viewport)
    await session.commit()
    return {"ok": True}


def export_endpoint_ref(port_id: int, port_by_id: dict[int, Port], device_by_id: dict[int, Device]) -> dict:
    port = port_by_id.get(port_id)
    device = device_by_id.get(port.device_id) if port else None
    return {
        "deviceId": device.id if device else None,
        "deviceName": device.display_name if device else None,
        "zabbixHostid": device.zabbix_hostid if device else None,
        "portId": port.id if port else None,
        "portIdentity": port.identity if port else None,
        "portName": port.name if port else None,
    }


async def import_topology_payload(session: AsyncSession, topology: Topology, payload: dict) -> None:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid topology JSON")
    devices_data = payload.get("devices")
    if not isinstance(devices_data, list):
        raise HTTPException(status_code=400, detail="Topology JSON must include devices")

    flat_ports_by_device: dict[str, list[dict]] = {}
    for port_data in payload.get("ports") or []:
        if not isinstance(port_data, dict):
            continue
        device_key = str(port_data.get("deviceId") or port_data.get("device_id") or "")
        flat_ports_by_device.setdefault(device_key, []).append(port_data)

    old_device_to_new: dict[str, Device] = {}
    old_port_to_new: dict[str, Port] = {}
    imported_devices: list[Device] = []

    for device_data in devices_data:
        if not isinstance(device_data, dict):
            continue
        device = await upsert_import_device(session, device_data)
        imported_devices.append(device)
        old_device_id = str(device_data.get("id") or "")
        if old_device_id:
            old_device_to_new[old_device_id] = device
        nested_ports = device_data.get("ports") if isinstance(device_data.get("ports"), list) else []
        ports_data = [*nested_ports, *flat_ports_by_device.get(old_device_id, [])]
        for port_data in ports_data:
            if not isinstance(port_data, dict):
                continue
            port = await upsert_import_port(session, device, port_data)
            old_port_id = str(port_data.get("id") or "")
            if old_port_id:
                old_port_to_new[old_port_id] = port

    await attach_devices_to_topology(session, topology, [device.id for device in imported_devices])

    for link_data in payload.get("cableLinks") or payload.get("cables") or []:
        if isinstance(link_data, dict):
            await import_cable_link(session, link_data, old_device_to_new, old_port_to_new)

    layout_data = payload.get("layout") or {}
    if isinstance(layout_data, dict):
        await import_layout(session, topology, layout_data, old_device_to_new)


async def upsert_import_device(session: AsyncSession, data: dict) -> Device:
    zabbix_hostid = clean_optional_str(data.get("zabbixHostid") or data.get("zabbix_hostid"))
    device: Device | None = None
    if zabbix_hostid:
        result = await session.execute(select(Device).where(Device.zabbix_hostid == zabbix_hostid))
        device = result.scalar_one_or_none()
    if device is None:
        display_name = clean_optional_str(data.get("displayName") or data.get("display_name")) or "导入设备"
        role = import_role(data.get("role"))
        result = await session.execute(select(Device).where(Device.display_name == display_name, Device.role == role))
        device = result.scalar_one_or_none()
    if device is None:
        device = Device(display_name=clean_optional_str(data.get("displayName") or data.get("display_name")) or "导入设备")
        session.add(device)
        await session.flush()

    device.source = import_source(data.get("source"), zabbix_hostid)
    device.zabbix_hostid = zabbix_hostid
    device.role = import_role(data.get("role"))
    device.model = clean_optional_str(data.get("model"))
    device.mgmt_ip = clean_optional_str(data.get("mgmtIp") or data.get("mgmt_ip"))
    device.display_name = clean_optional_str(data.get("displayName") or data.get("display_name")) or device.display_name
    device.status = clean_optional_str(data.get("status")) or "imported"
    device.health = clean_optional_str(data.get("health")) or "unknown"
    device.enabled = bool(data.get("enabled", True))
    device.stale = bool(data.get("stale", False))
    return device


async def upsert_import_port(session: AsyncSession, device: Device, data: dict) -> Port:
    name = clean_optional_str(data.get("name")) or "port"
    identity = clean_optional_str(data.get("identity")) or f"import:{name.lower()}"
    result = await session.execute(select(Port).where(Port.device_id == device.id, Port.identity == identity))
    port = result.scalar_one_or_none()
    if port is None:
        result = await session.execute(select(Port).where(Port.device_id == device.id, Port.name == name))
        port = result.scalar_one_or_none()
    if port is None:
        port = Port(device_id=device.id, identity=identity, name=name)
        session.add(port)
        await session.flush()

    port.source = import_source(data.get("source"), device.zabbix_hostid)
    port.identity = identity
    port.if_index = int_or_none(data.get("ifIndex") or data.get("if_index"))
    port.name = name
    port.alias = clean_optional_str(data.get("alias"))
    port.oper_status = clean_optional_str(data.get("operStatus") or data.get("oper_status")) or "unknown"
    port.admin_status = clean_optional_str(data.get("adminStatus") or data.get("admin_status")) or "unknown"
    port.speed_mbps = float_or_none(data.get("speedMbps") or data.get("speed_mbps"))
    port.media = clean_optional_str(data.get("media"))
    port.port_role = clean_optional_str(data.get("portRole") or data.get("port_role"))
    port.vlan_summary = clean_optional_str(data.get("vlanSummary") or data.get("vlan_summary"))
    port.poe_status = clean_optional_str(data.get("poeStatus") or data.get("poe_status"))
    port.stale = bool(data.get("stale", False))
    return port


async def import_cable_link(
    session: AsyncSession,
    data: dict,
    old_device_to_new: dict[str, Device],
    old_port_to_new: dict[str, Port],
) -> None:
    endpoint_a = data.get("endpointA") or {}
    endpoint_b = data.get("endpointB") or {}
    port_a = await resolve_import_port(session, endpoint_a, old_device_to_new, old_port_to_new)
    port_b = await resolve_import_port(session, endpoint_b, old_device_to_new, old_port_to_new)
    if port_a is None or port_b is None or port_a.id == port_b.id:
        return
    endpoint_a_id, endpoint_b_id = sorted([port_a.id, port_b.id])
    existing = await session.execute(
        select(CableLink).where(CableLink.endpoint_a_port_id == endpoint_a_id, CableLink.endpoint_b_port_id == endpoint_b_id)
    )
    link = existing.scalar_one_or_none()
    if link is None:
        link = CableLink(endpoint_a_port_id=endpoint_a_id, endpoint_b_port_id=endpoint_b_id)
        session.add(link)
    link.label = clean_optional_str(data.get("label"))
    link.cable_no = clean_optional_str(data.get("cableNo") or data.get("cable_no"))
    link.color = clean_optional_str(data.get("color")) or "#4f8cff"
    link.notes = clean_optional_str(data.get("notes"))


async def resolve_import_port(
    session: AsyncSession,
    ref: dict,
    old_device_to_new: dict[str, Device],
    old_port_to_new: dict[str, Port],
) -> Port | None:
    old_port_id = str(ref.get("portId") or "")
    if old_port_id and old_port_id in old_port_to_new:
        return old_port_to_new[old_port_id]
    device = old_device_to_new.get(str(ref.get("deviceId") or ""))
    if device is None and ref.get("zabbixHostid"):
        result = await session.execute(select(Device).where(Device.zabbix_hostid == str(ref.get("zabbixHostid"))))
        device = result.scalar_one_or_none()
    if device is None and ref.get("deviceName"):
        result = await session.execute(select(Device).where(Device.display_name == str(ref.get("deviceName"))))
        device = result.scalar_one_or_none()
    if device is None:
        return None
    identity = clean_optional_str(ref.get("portIdentity"))
    if identity:
        result = await session.execute(select(Port).where(Port.device_id == device.id, Port.identity == identity))
        port = result.scalar_one_or_none()
        if port:
            return port
    port_name = clean_optional_str(ref.get("portName"))
    if port_name:
        result = await session.execute(select(Port).where(Port.device_id == device.id, Port.name == port_name))
        return result.scalar_one_or_none()
    return None


async def import_layout(session: AsyncSession, topology: Topology, data: dict, old_device_to_new: dict[str, Device]) -> None:
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    layout_key = layout_key_for_topology(topology.id)
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("nodeId") or "")
        match = node_id.removeprefix("device-")
        device = old_device_to_new.get(match)
        next_node_id = f"device-{device.id}" if device else node_id
        if not next_node_id:
            continue
        result = await session.execute(
            select(TopologyLayout).where(TopologyLayout.layout_key == layout_key, TopologyLayout.node_id == next_node_id)
        )
        layout = result.scalar_one_or_none()
        if layout is None:
            layout = TopologyLayout(layout_key=layout_key, node_id=next_node_id)
            session.add(layout)
        layout.x = float_or_none(node.get("x")) or 0
        layout.y = float_or_none(node.get("y")) or 0
        layout.width = float_or_none(node.get("width"))
        layout.height = float_or_none(node.get("height"))
        layout.group_name = clean_optional_str(node.get("groupName") or node.get("group_name"))
        layout.hidden = bool(node.get("hidden", False))


def clean_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    return text


def import_role(value: object) -> str:
    role = clean_optional_str(value) or "custom"
    return role if role in {"switch", "server", "custom"} else "custom"


def import_source(value: object, zabbix_hostid: str | None) -> str:
    source = clean_optional_str(value)
    if source in {"manual", "zabbix", "profile"}:
        return source
    return "zabbix" if zabbix_hostid else "manual"


def int_or_none(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def float_or_none(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


@router.post("/cable-links", response_model=CableLinkRead)
async def create_cable_link(payload: CableLinkCreate, session: AsyncSession = Depends(get_session)) -> CableLink:
    a = await get_port_or_404(session, payload.endpointAPortId)
    b = await get_port_or_404(session, payload.endpointBPortId)
    if a.id == b.id:
        raise HTTPException(status_code=400, detail="Cable endpoints must be different")
    endpoint_a, endpoint_b = sorted([a.id, b.id])
    existing = await session.execute(
        select(CableLink).where(
            or_(
                and_(CableLink.endpoint_a_port_id == endpoint_a, CableLink.endpoint_b_port_id == endpoint_b),
                and_(CableLink.endpoint_a_port_id == endpoint_b, CableLink.endpoint_b_port_id == endpoint_a),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Cable link already exists")
    link = CableLink(
        endpoint_a_port_id=endpoint_a,
        endpoint_b_port_id=endpoint_b,
        label=payload.label,
        cable_no=payload.cableNo,
        color=payload.color,
        notes=payload.notes,
        verified_at=payload.verifiedAt,
        created_by=payload.createdBy,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


@router.patch("/cable-links/{link_id}", response_model=CableLinkRead)
async def update_cable_link(link_id: int, payload: CableLinkUpdate, session: AsyncSession = Depends(get_session)) -> CableLink:
    link = await get_link_or_404(session, link_id)
    data = payload.model_dump(exclude_unset=True)
    field_map = {"cableNo": "cable_no", "verifiedAt": "verified_at", "createdBy": "created_by"}
    for key, value in data.items():
        setattr(link, field_map.get(key, key), value)
    await session.commit()
    await session.refresh(link)
    return link


@router.delete("/cable-links/{link_id}")
async def delete_cable_link(link_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    link = await get_link_or_404(session, link_id)
    await session.delete(link)
    await session.commit()
    return {"ok": True}


@router.get("/ports/{port_id}/series", response_model=PortSeries)
async def port_series(
    port_id: int,
    range_name: Literal["1h", "6h", "24h", "7d"] = Query("24h", alias="range"),
    session: AsyncSession = Depends(get_session),
    zabbix: ZabbixClient = Depends(zabbix_from_request),
) -> PortSeries:
    port = await get_port_or_404(session, port_id)
    if not port.traffic_in_itemid and not port.traffic_out_itemid:
        return PortSeries(portId=port_id, range=range_name, points=[])
    seconds = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}[range_name]
    now = int(time.time())
    itemids = [item for item in [port.traffic_in_itemid, port.traffic_out_itemid] if item]
    try:
        if range_name == "7d":
            raw = await zabbix.trends(itemids, time_from=now - seconds, time_till=now)
            points = merge_series(raw, port.traffic_in_itemid, port.traffic_out_itemid, trend=True)
        else:
            raw_float = await zabbix.history(itemids, history_type=0, time_from=now - seconds, time_till=now)
            raw_uint = await zabbix.history(itemids, history_type=3, time_from=now - seconds, time_till=now)
            raw = [*raw_float, *raw_uint]
            points = merge_series(raw, port.traffic_in_itemid, port.traffic_out_itemid, trend=False)
        return PortSeries(portId=port_id, range=range_name, points=points)
    except Exception as exc:
        return PortSeries(portId=port_id, range=range_name, points=[], error=str(exc))


@router.post("/sync/zabbix/run", response_model=SyncRunRead)
async def trigger_sync(
    request: Request,
    topologyId: int | None = Query(None, alias="topologyId"),
    session: AsyncSession = Depends(get_session),
    zabbix: ZabbixClient = Depends(zabbix_from_request),
    settings: Settings = Depends(get_settings),
) -> ZabbixSyncRun:
    if not settings.zabbix_configured():
        raise HTTPException(status_code=503, detail="Zabbix credentials are not configured")
    run = await run_zabbix_sync_serialized(request, session, zabbix, settings)
    if topologyId is None or run.status != "success":
        return run

    topology = await get_topology_by_id(session, topologyId)
    result = await session.execute(
        select(Device.id).where(
            Device.source == "zabbix",
            Device.enabled.is_(True),
            Device.stale.is_(False),
        ),
    )
    device_ids = list(result.scalars().all())
    if device_ids:
        await attach_devices_to_topology(session, topology, device_ids)
        await session.commit()
    return run


@router.get("/sync/status", response_model=SyncStatus)
async def sync_status(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SyncStatus:
    result = await session.execute(select(ZabbixSyncRun).order_by(ZabbixSyncRun.id.desc()).limit(1))
    latest = result.scalar_one_or_none()
    return SyncStatus(latest=SyncRunRead.model_validate(latest) if latest else None, zabbixConfigured=settings.zabbix_configured())


@router.get("/sync/runs", response_model=list[SyncRunRead])
async def sync_runs(
    limit: int = Query(8, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[ZabbixSyncRun]:
    result = await session.execute(select(ZabbixSyncRun).order_by(ZabbixSyncRun.id.desc()).limit(limit))
    return list(result.scalars().all())


async def get_device_or_404(session: AsyncSession, device_id: int) -> Device:
    result = await session.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


async def get_port_or_404(session: AsyncSession, port_id: int) -> Port:
    result = await session.execute(select(Port).where(Port.id == port_id))
    port = result.scalar_one_or_none()
    if port is None:
        raise HTTPException(status_code=404, detail="Port not found")
    return port


async def get_link_or_404(session: AsyncSession, link_id: int) -> CableLink:
    result = await session.execute(select(CableLink).where(CableLink.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Cable link not found")
    return link


def port_from_create(device_id: int, payload: PortCreate, *, name: str | None = None) -> Port:
    clean_name = clean_required_text(name or payload.name, "Port name is required")
    identity = manual_port_identity(clean_name)
    return Port(
        device_id=device_id,
        source="manual",
        identity=identity,
        if_index=payload.ifIndex,
        name=clean_name,
        alias=payload.alias,
        oper_status="unknown",
        admin_status="unknown",
        speed_mbps=payload.speedMbps,
        media=payload.media,
        port_role=payload.portRole,
        vlan_summary=payload.vlanSummary,
        poe_status=payload.poeStatus,
        stale=False,
    )


def manual_port_identity(name: str) -> str:
    return f"manual:{name.strip().lower()}"


def build_node(device: Device, index: int, layout: TopologyLayout | None) -> TopologyNode:
    if layout:
        position = {"x": layout.x, "y": layout.y}
    elif device.role == "switch":
        position = {"x": 80, "y": 80 + index * 260}
    else:
        position = {"x": 720 + (index % 3) * 300, "y": 80 + (index // 3) * 140}
    ports = sorted(device.ports, key=lambda port: port_sort_key(port.name))
    return TopologyNode(
        id=f"device-{device.id}",
        type="switchNode" if device.role == "switch" else "endpointNode",
        position=position,
        data={
            "device": DeviceRead.model_validate(device).model_dump(by_alias=False),
            "ports": [PortRead.model_validate(port).model_dump(by_alias=False) for port in ports],
        },
    )


def switch_panel(device: Device) -> dict:
    profile = profile_for_model(device.model)
    ports = sorted(device.ports, key=lambda port: port_sort_key(port.name))
    return {
        "deviceId": device.id,
        "modelKey": profile.key if profile else None,
        "displayName": device.display_name,
        "health": device.health,
        "ports": [PortRead.model_validate(port).model_dump(by_alias=False) for port in ports],
    }


def merge_series(raw: list[dict], in_itemid: str | None, out_itemid: str | None, *, trend: bool) -> list[SeriesPoint]:
    by_clock: dict[int, dict[str, float | None]] = {}
    for row in raw:
        clock = int(float(row.get("clock") or 0))
        if clock <= 0:
            continue
        value_key = "value_avg" if trend else "value"
        try:
            value = float(row.get(value_key) or 0)
        except (TypeError, ValueError):
            continue
        point = by_clock.setdefault(clock, {"inBps": None, "outBps": None})
        if str(row.get("itemid")) == str(in_itemid):
            point["inBps"] = value
        elif str(row.get("itemid")) == str(out_itemid):
            point["outBps"] = value
    return [SeriesPoint(ts=clock, inBps=data["inBps"], outBps=data["outBps"]) for clock, data in sorted(by_clock.items())]
