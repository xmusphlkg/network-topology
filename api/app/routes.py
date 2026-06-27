from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .clients.zabbix import ZabbixClient
from .config import Settings, get_settings
from .database import get_session
from .db_models import AuditLog, CableLink, Device, Port, Topology, TopologyDevice, TopologyLayout, ZabbixSyncRun
from .schemas import (
    AuditLogRead,
    CableLinkCreate,
    CableLinkRead,
    CableLinkUpdate,
    DeviceCreate,
    DeviceRead,
    DeviceUpdate,
    LayoutUpdate,
    PortCreate,
    PortPage,
    PortRead,
    PortSeries,
    PortUpdate,
    QualityIssue,
    SeriesPoint,
    SyncRunRead,
    SyncStatus,
    TopologyCreate,
    TopologyDeviceIds,
    TopologyGraphRead,
    TopologyImportRequest,
    ImportDryRunRead,
    TopologyRead,
    ZabbixDeviceChange,
    DeviceProfileApplyRequest,
    IngestCable,
    IngestDevice,
    IngestEndpointRef,
    IngestPort,
    IngestRequest,
    IngestResult,
    IpAddrIngestRequest,
    TopologyUpdate,
    ZabbixDiscoveredDevice,
)
from .services.mapper import is_virtual_port_name, normalize_port_name
from .services.mac import normalize_mac_address
from .services.manual_overrides import mark_overrides, set_optional_unless_overridden, set_unless_overridden
from .services.ip_addr import parse_ip_addr_ports
from .services.profiles import PROFILES, get_profile, is_switch_profile, port_sort_key
from .services.topology_graph import build_topology_graph, layout_key_for_topology
from .services.sync import collect_zabbix_snapshots, run_zabbix_sync, run_zabbix_sync_from_snapshots, upsert_zabbix_snapshots

router = APIRouter(prefix="/api")

DEVICE_OVERRIDE_FIELDS = {
    "displayName": "display_name",
    "role": "role",
    "model": "model",
    "mgmtIp": "mgmt_ip",
    "enabled": "enabled",
}
PORT_OVERRIDE_FIELDS = {
    "name": "name",
    "alias": "alias",
    "speedMbps": "speed_mbps",
    "media": "media",
    "macAddress": "mac_address",
    "portRole": "port_role",
    "vlanSummary": "vlan_summary",
    "poeStatus": "poe_status",
}
PROTECTED_DEVICE_SOURCES = {"manual", "zabbix"}
PROTECTED_PORT_SOURCES = {"manual", "zabbix", "profile"}


def zabbix_from_request(request: Request) -> ZabbixClient:
    return request.app.state.zabbix


def sync_lock_from_request(request: Request) -> asyncio.Lock:
    lock = getattr(request.app.state, "sync_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.sync_lock = lock
    return lock


def require_write_permission(
    settings: Settings = Depends(get_settings),
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
) -> None:
    if not settings.read_only_mode:
        return
    if settings.admin_token and x_admin_token == settings.admin_token:
        return
    raise HTTPException(status_code=403, detail="Application is in read-only mode")


def actor_from_request(request: Request) -> str | None:
    return request.headers.get("X-Actor") or request.headers.get("X-User") or None


async def record_audit(
    session: AsyncSession,
    request: Request | None,
    action: str,
    resource_type: str,
    resource_id: object | None,
    details: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            actor=actor_from_request(request) if request else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details_json=json.dumps(details or {}, ensure_ascii=False, separators=(",", ":")),
        )
    )


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


def zabbix_discovered_device_read(snapshot, existing: Device | None, synced: bool) -> ZabbixDiscoveredDevice:
    changes: list[ZabbixDeviceChange] = []
    if existing is not None:
        comparisons = [
            ("displayName", existing.display_name, snapshot.display_name),
            ("role", existing.role, snapshot.role),
            ("model", existing.model, snapshot.model),
            ("mgmtIp", existing.mgmt_ip, snapshot.mgmt_ip),
        ]
        for field, current, incoming in comparisons:
            if current != incoming and incoming is not None:
                changes.append(ZabbixDeviceChange(field=field, current=current, incoming=incoming))
    action: Literal["new", "update", "synced"] = "new"
    if existing is not None:
        action = "synced" if synced and not changes else "update"
    return ZabbixDiscoveredDevice(
        zabbixHostid=snapshot.zabbix_hostid,
        displayName=snapshot.display_name,
        role=snapshot.role,
        model=snapshot.model,
        mgmtIp=snapshot.mgmt_ip,
        portCount=len(snapshot.ports),
        synced=synced,
        action=action,
        existingDeviceId=existing.id if existing else None,
        changes=changes,
    )


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
    request: Request,
    _permission: None = Depends(require_write_permission),
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
    await record_audit(session, request, "topology.create", "topology", topology.id, {"name": topology.name})
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.patch("/topologies/{topology_id}", response_model=TopologyRead)
async def update_topology(
    topology_id: int,
    payload: TopologyUpdate,
    request: Request,
    _permission: None = Depends(require_write_permission),
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
    await record_audit(session, request, "topology.update", "topology", topology.id, data)
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.post("/topologies/{topology_id}/devices", response_model=TopologyRead)
async def link_devices_to_topology(
    topology_id: int,
    payload: TopologyDeviceIds,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    if payload.deviceIds:
        result = await session.execute(select(Device.id).where(Device.id.in_(payload.deviceIds)))
        existing_ids = [device_id for device_id in result.scalars().all()]
        if not existing_ids:
            raise HTTPException(status_code=400, detail="No valid device ids")
        created = await attach_devices_to_topology(session, topology, existing_ids)
        await record_audit(session, request, "topology.devices.add", "topology", topology.id, {"deviceIds": existing_ids, "created": created})
        await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.delete("/topologies/{topology_id}/devices/{device_id}", response_model=TopologyRead)
async def unlink_device_from_topology(
    topology_id: int,
    device_id: int,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    await get_device_or_404(session, device_id)
    await session.execute(
        delete(TopologyDevice).where(
            TopologyDevice.topology_id == topology.id,
            TopologyDevice.device_id == device_id,
        )
    )
    await session.execute(
        delete(TopologyLayout).where(
            TopologyLayout.layout_key == layout_key_for_topology(topology.id),
            TopologyLayout.node_id == f"device-{device_id}",
        )
    )
    await record_audit(session, request, "topology.devices.remove", "topology", topology.id, {"deviceId": device_id})
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
    hostids = [snapshot.zabbix_hostid for snapshot in snapshots]
    existing_devices_result = await session.execute(select(Device).where(Device.zabbix_hostid.in_(hostids))) if hostids else None
    existing_by_hostid = {device.zabbix_hostid: device for device in existing_devices_result.scalars().all()} if existing_devices_result is not None else {}
    return [
        zabbix_discovered_device_read(snapshot, existing_by_hostid.get(snapshot.zabbix_hostid), snapshot.zabbix_hostid in synced_hostids)
        for snapshot in snapshots
    ]


@router.post("/topologies/{topology_id}/sync-and-import", response_model=TopologyRead)
async def sync_and_import_topology(
    topology_id: int,
    payload: TopologyImportRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
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
    created = await attach_devices_to_topology(session, topology, device_ids)
    await record_audit(session, request, "topology.zabbix_import", "topology", topology.id, {"hostids": sorted(selected), "deviceIds": device_ids, "created": created})
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.post("/devices", response_model=DeviceRead)
async def create_device(
    payload: DeviceCreate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Device:
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
    await record_audit(session, request, "device.create", "device", device.id, {"displayName": device.display_name, "topologyId": topology.id})
    await session.commit()
    await session.refresh(device)
    return device


@router.patch("/devices/{device_id}", response_model=DeviceRead)
async def update_device(
    device_id: int,
    payload: DeviceUpdate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Device:
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
    mark_overrides(device, {DEVICE_OVERRIDE_FIELDS[key] for key in data if key in DEVICE_OVERRIDE_FIELDS})
    await record_audit(session, request, "device.update", "device", device.id, data)
    await session.commit()
    await session.refresh(device)
    return device


@router.post("/devices/{device_id}/apply-profile", response_model=DeviceRead)
async def apply_profile_ports(
    device_id: int,
    payload: DeviceProfileApplyRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Device:
    device = await get_device_or_404(session, device_id)
    profile = get_profile(payload.profileKey)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")

    existing_ports = (await session.execute(select(Port).where(Port.device_id == device.id))).scalars().all()
    if payload.replaceProfilePorts:
        profile_port_ids = [port.id for port in existing_ports if port.source == "profile"]
        if profile_port_ids:
            await session.execute(
                delete(CableLink).where(
                    or_(
                        CableLink.endpoint_a_port_id.in_(profile_port_ids),
                        CableLink.endpoint_b_port_id.in_(profile_port_ids),
                    )
                )
            )
            await session.execute(delete(Port).where(Port.id.in_(profile_port_ids)))
            existing_ports = [port for port in existing_ports if port.id not in profile_port_ids]

    occupied_normalized_names: dict[str, bool] = {}
    for port in existing_ports:
        normalized = normalize_port_name(port.name)
        if normalized:
            occupied_normalized_names[normalized] = True

    for profile_port in profile.ports:
        normalized = normalize_port_name(profile_port.name)
        if not normalized:
            continue
        if occupied_normalized_names.get(normalized, False):
            continue
        session.add(
            Port(
                device_id=device.id,
                source="profile",
                identity=f"profile:{normalized}",
                name=profile_port.name,
                virtual=False,
                oper_status="unknown",
                admin_status="unknown",
                speed_mbps=profile_port.speed_mbps,
                media=profile_port.media,
                port_role=profile_port.role,
                stale=False,
            )
        )
        occupied_normalized_names[normalized] = True

    if not device.model:
        device.model = profile.key
    if is_switch_profile(payload.profileKey) and device.role != "switch":
        device.role = "switch"
    elif device.role == "custom":
        # 如果是非交换机模板且设备仍为自定义类型，保留原角色，避免误改服务器类型。
        device.role = "custom"
    await record_audit(session, request, "device.apply_profile", "device", device.id, {"profileKey": payload.profileKey, "replaceProfilePorts": payload.replaceProfilePorts})
    await session.commit()
    await session.refresh(device)
    return device


@router.post("/sync/ingest", response_model=IngestResult)
async def ingest_from_agent(
    payload: IngestRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> IngestResult:
    return await _ingest_payload(session, payload, strict_physical_ports=payload.strictPhysicalPorts, request=request)


@router.post("/sync/push", response_model=IngestResult)
async def push_from_agent(
    payload: IngestRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> IngestResult:
    return await _ingest_payload(session, payload, strict_physical_ports=payload.strictPhysicalPorts, request=request)


@router.post("/sync/command-push", response_model=IngestResult)
async def push_from_command(
    payload: IngestRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> IngestResult:
    """Endpoint for server-side command runners / automation to submit discovered device inventory."""
    return await _ingest_payload(session, payload, strict_physical_ports=payload.strictPhysicalPorts, request=request)


@router.post("/sync/ip-addr", response_model=IngestResult)
async def push_from_ip_addr(
    payload: IpAddrIngestRequest,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> IngestResult:
    topology = await (get_default_topology(session) if payload.topologyId is None else get_topology_by_id(session, payload.topologyId))
    ports = parse_ip_addr_ports(payload.output)
    ingest_payload = IngestRequest(
        source=payload.source,
        topologyId=topology.id,
        strictPhysicalPorts=payload.strictPhysicalPorts,
        physicalPortNamePatterns=payload.physicalPortNamePatterns,
        devices=[
            IngestDevice(
                displayName=payload.displayName,
                role="server",
                mgmtIp=payload.mgmtIp,
                source=payload.source,
                ports=[IngestPort(**port) for port in ports],
                strictPhysicalPorts=payload.strictPhysicalPorts,
            )
        ],
        cables=[],
    )
    return await _ingest_payload(session, ingest_payload, strict_physical_ports=payload.strictPhysicalPorts, request=request)


async def _ingest_payload(
    session: AsyncSession,
    payload: IngestRequest,
    strict_physical_ports: bool,
    request: Request | None = None,
) -> IngestResult:
    topology = None
    if payload.topologyId is not None:
        topology = await get_topology_by_id(session, payload.topologyId)

    source_key = _normalize_ingest_source(payload.source)
    device_id_cache: dict[str, Device] = {}
    ports_by_device_key: dict[int, set[str]] = {}
    cable_count = 0
    seen_device_ids: set[int] = set()
    seen_ports = 0
    physical_name_patterns = _normalize_patterns(payload.physicalPortNamePatterns)

    for device_payload in payload.devices:
        accepted_physical_count = 0
        device_strict_physical_ports = strict_physical_ports or device_payload.strictPhysicalPorts
        device = await _find_or_create_device_for_ingest(session, source_key, device_payload)
        seen_device_ids.add(device.id)
        for key in _ingest_device_cache_keys(device_payload, device):
            device_id_cache[key] = device
            seen_device_ids.add(device.id)
        ports_by_device_key[device.id] = set[str]()
        await session.flush()
        if topology is not None:
            existing = await session.execute(
                select(TopologyDevice).where(TopologyDevice.topology_id == topology.id, TopologyDevice.device_id == device.id)
            )
            if not existing.scalar_one_or_none():
                session.add(TopologyDevice(topology_id=topology.id, device_id=device.id))
        for port_payload in device_payload.ports:
            is_physical = _is_physical_ingest_port(port_payload.name, device_strict_physical_ports, physical_name_patterns)
            if device_strict_physical_ports and not is_physical:
                continue
            if device_strict_physical_ports and payload.maxPhysicalPortsPerDevice is not None and is_physical and accepted_physical_count >= payload.maxPhysicalPortsPerDevice:
                continue
            port_identity, upserted = await _upsert_ingest_port(
                session,
                device.id,
                source_key,
                port_payload,
                strict_physical_ports=device_strict_physical_ports,
            )
            if upserted:
                seen_ports += 1
                if device_strict_physical_ports and is_physical:
                    accepted_physical_count += 1
            if port_identity:
                ports_by_device_key[device.id].add(port_identity)

    # Mark stale ports for this ingest source only, per device.
    if ports_by_device_key:
        for device_id, seen_identities in ports_by_device_key.items():
            all_ports = await session.execute(
                select(Port).where(Port.device_id == device_id, Port.source == source_key)
            )
            for port in all_ports.scalars().all():
                port.stale = _normalize_ingest_port_identity(port.name) not in seen_identities

            # keep devices with any ingest ports active
            device = await session.get(Device, device_id)
            if device is not None:
                device.stale = False

    if payload.cables:
        # Keep a point-in-time snapshot of devices for endpoint resolution
        all_device_ids = list(ports_by_device_key.keys())
        if all_device_ids:
            existing_ports = await session.execute(select(Port).where(Port.device_id.in_(all_device_ids)))
            ports_by_device: dict[int, list[Port]] = {}
            for port in existing_ports.scalars().all():
                ports_by_device.setdefault(port.device_id, []).append(port)
        else:
            ports_by_device = {}

        for cable in payload.cables:
            endpoint_a = await _resolve_ingest_endpoint(session, cable.endpointA, device_id_cache, ports_by_device)
            endpoint_b = await _resolve_ingest_endpoint(session, cable.endpointB, device_id_cache, ports_by_device)
            if endpoint_a is None or endpoint_b is None:
                continue
            if endpoint_a == endpoint_b:
                continue
            link = await _get_or_create_link(session, endpoint_a, endpoint_b)
            if cable.cableNo is not None:
                link.cable_no = cable.cableNo
            if cable.label is not None:
                link.label = cable.label
            if cable.vlanId is not None:
                link.vlan_id = cable.vlanId
            if cable.notes is not None:
                link.notes = cable.notes
            if cable.color is not None:
                link.color = cable.color
            if cable.verifiedAt is not None:
                link.verified_at = _parse_iso_datetime(cable.verifiedAt)
            else:
                link.verified_at = None
            cable_count += 1

    result = IngestResult(
        devices=len(seen_device_ids),
        ports=seen_ports,
        cables=cable_count,
    )
    await record_audit(session, request, "sync.ingest", "sync", None, {"source": source_key, "devices": result.devices, "ports": result.ports, "cables": result.cables})
    await session.commit()
    return result


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: int,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> dict:
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
    await record_audit(session, request, "device.delete", "device", device.id, {"displayName": device.display_name})
    await session.delete(device)
    await session.commit()
    return {"ok": True}


@router.get("/devices/{device_id}/ports", response_model=list[PortRead])
async def device_ports(
    device_id: int,
    include_virtual: bool = Query(False, alias="includeVirtual"),
    session: AsyncSession = Depends(get_session),
) -> list[Port]:
    await get_device_or_404(session, device_id)
    stmt = select(Port).where(Port.device_id == device_id)
    if not include_virtual:
        stmt = stmt.where(Port.virtual.is_(False))
    result = await session.execute(stmt)
    ports = list(result.scalars().all())
    return sorted(ports, key=lambda port: port_sort_key(port.name))


@router.post("/devices/{device_id}/ports", response_model=PortRead)
async def create_port(
    device_id: int,
    payload: PortCreate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Port:
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
    await session.flush()
    await record_audit(session, request, "port.create", "port", port.id, {"deviceId": device_id, "name": port.name})
    await session.commit()
    await session.refresh(port)
    return port


@router.delete("/ports/{port_id}")
async def delete_port(
    port_id: int,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> dict:
    port = await get_port_or_404(session, port_id)
    await session.execute(
        delete(CableLink).where(
            or_(
                CableLink.endpoint_a_port_id == port.id,
                CableLink.endpoint_b_port_id == port.id,
            )
        )
    )
    await record_audit(session, request, "port.delete", "port", port.id, {"deviceId": port.device_id, "name": port.name})
    await session.delete(port)
    await session.commit()
    return {"ok": True}


@router.get("/ports", response_model=list[PortRead])
async def ports(
    device_id: int | None = Query(None, alias="deviceId"),
    topology_id: int | None = Query(None, alias="topologyId"),
    status: str | None = Query(None),
    include_stale: bool = Query(True, alias="includeStale"),
    include_virtual: bool = Query(False, alias="includeVirtual"),
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
        stmt = stmt.where(or_(Port.name.like(like), Port.alias.like(like), Port.vlan_summary.like(like), Port.mac_address.like(like)))
    if not include_virtual:
        stmt = stmt.where(Port.virtual.is_(False))
    stmt = stmt.order_by(Port.device_id, Port.name)
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/ports/page", response_model=PortPage)
async def ports_page(
    topology_id: int | None = Query(None, alias="topologyId"),
    status: str | None = Query(None),
    include_stale: bool = Query(True, alias="includeStale"),
    include_virtual: bool = Query(False, alias="includeVirtual"),
    media: str | None = Query(None),
    speed_filter: Literal["slow", "1g", "10g"] | None = Query(None, alias="speed"),
    limit: int = Query(80, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> PortPage:
    stmt = select(Port).join(Device, Device.id == Port.device_id)
    if topology_id is not None:
        await get_topology_by_id(session, topology_id)
        stmt = stmt.join(TopologyDevice, TopologyDevice.device_id == Port.device_id).where(TopologyDevice.topology_id == topology_id)
    if status == "stale":
        stmt = stmt.where(Port.stale.is_(True))
    elif status:
        stmt = stmt.where(Port.oper_status == status)
    if not include_stale and status != "stale":
        stmt = stmt.where(Port.stale.is_(False))
    if not include_virtual:
        stmt = stmt.where(Port.virtual.is_(False))
    if media:
        stmt = stmt.where(Port.media == media)
    if speed_filter == "slow":
        stmt = stmt.where(or_(Port.speed_mbps.is_(None), Port.speed_mbps < 1000))
    elif speed_filter == "1g":
        stmt = stmt.where(Port.speed_mbps >= 1000)
    elif speed_filter == "10g":
        stmt = stmt.where(Port.speed_mbps >= 10000)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            or_(
                Port.name.like(like),
                Port.alias.like(like),
                Port.vlan_summary.like(like),
                Port.mac_address.like(like),
                Device.display_name.like(like),
                Device.mgmt_ip.like(like),
                Device.model.like(like),
            )
        )
    count_result = await session.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))
    total = count_result.scalar_one() or 0
    rows_result = await session.execute(stmt.order_by(Port.device_id, Port.name).offset(offset).limit(limit))
    return PortPage(
        items=[PortRead.model_validate(port) for port in rows_result.scalars().all()],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/ports/{port_id}", response_model=PortRead)
async def update_port(
    port_id: int,
    payload: PortUpdate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Port:
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
        "macAddress": "mac_address",
        "portRole": "port_role",
        "vlanSummary": "vlan_summary",
        "poeStatus": "poe_status",
    }
    for key, value in data.items():
        setattr(port, field_map.get(key, key), value)
    if "name" in data:
        port.virtual = is_virtual_port_name(port.name)
    mark_overrides(port, {PORT_OVERRIDE_FIELDS[key] for key in data if key in PORT_OVERRIDE_FIELDS})
    await record_audit(session, request, "port.update", "port", port.id, data)
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
    await hydrate_topology_counts(session, topology)
    return await build_topology_graph(session, topology)


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
    request: Request,
    payload: dict = Body(...),
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> Topology:
    topology = await get_topology_by_id(session, topology_id)
    await import_topology_payload(session, topology, payload)
    await record_audit(session, request, "topology.json_import", "topology", topology.id, import_topology_dry_run_summary(payload))
    await session.commit()
    return await hydrate_topology_counts(session, topology)


@router.post("/topologies/{topology_id}/json-import/dry-run", response_model=ImportDryRunRead)
async def import_topology_json_dry_run(
    topology_id: int,
    payload: dict = Body(...),
    session: AsyncSession = Depends(get_session),
) -> ImportDryRunRead:
    await get_topology_by_id(session, topology_id)
    return await analyze_import_topology_payload(session, payload)


@router.patch("/topology/layout")
async def save_layout(
    payload: LayoutUpdate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
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
    await record_audit(session, request, "topology.layout.save", "layout", payload.layoutKey, {"nodes": len(payload.nodes), "viewport": payload.viewport is not None})
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
        "macAddress": port.mac_address if port else None,
    }


def import_topology_dry_run_summary(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {"devices": 0, "ports": 0, "cableLinks": 0, "layouts": 0}
    devices = payload.get("devices")
    ports = payload.get("ports")
    cable_links = payload.get("cableLinks") or payload.get("cables")
    layout = payload.get("layout")
    layout_nodes = layout.get("nodes") if isinstance(layout, dict) else []
    nested_ports = 0
    if isinstance(devices, list):
        for device in devices:
            if isinstance(device, dict) and isinstance(device.get("ports"), list):
                nested_ports += len(device["ports"])
    return {
        "devices": len(devices) if isinstance(devices, list) else 0,
        "ports": nested_ports + (len(ports) if isinstance(ports, list) else 0),
        "cableLinks": len(cable_links) if isinstance(cable_links, list) else 0,
        "layouts": len(layout_nodes) if isinstance(layout_nodes, list) else 0,
    }


async def analyze_import_topology_payload(session: AsyncSession, payload: dict) -> ImportDryRunRead:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid topology JSON")
    devices_data = payload.get("devices")
    if not isinstance(devices_data, list):
        raise HTTPException(status_code=400, detail="Topology JSON must include devices")
    summary = import_topology_dry_run_summary(payload)
    warnings: list[str] = []
    existing_devices = 0
    seen_names: set[str] = set()
    seen_hostids: set[str] = set()
    for device_data in devices_data:
        if not isinstance(device_data, dict):
            warnings.append("跳过了一个非对象设备条目")
            continue
        display_name = clean_optional_str(device_data.get("displayName") or device_data.get("display_name"))
        zabbix_hostid = clean_optional_str(device_data.get("zabbixHostid") or device_data.get("zabbix_hostid"))
        role = import_role(device_data.get("role"))
        if display_name:
            key = f"{role}:{display_name}"
            if key in seen_names:
                warnings.append(f"导入文件中存在重复设备名称：{display_name}")
            seen_names.add(key)
        if zabbix_hostid:
            if zabbix_hostid in seen_hostids:
                warnings.append(f"导入文件中存在重复 Zabbix hostid：{zabbix_hostid}")
            seen_hostids.add(zabbix_hostid)
            exists = await session.execute(select(Device.id).where(Device.zabbix_hostid == zabbix_hostid))
            if exists.scalar_one_or_none() is not None:
                existing_devices += 1
                continue
        if display_name:
            exists = await session.execute(select(Device.id).where(Device.display_name == display_name, Device.role == role))
            if exists.scalar_one_or_none() is not None:
                existing_devices += 1
    if summary["devices"] == 0:
        warnings.append("导入文件没有设备")
    if summary["cableLinks"] and summary["ports"] == 0:
        warnings.append("导入文件包含线缆但没有端口，线缆可能无法解析")
    return ImportDryRunRead(
        valid=True,
        devices=summary["devices"],
        ports=summary["ports"],
        cableLinks=summary["cableLinks"],
        layouts=summary["layouts"],
        existingDevices=existing_devices,
        newDevices=max(summary["devices"] - existing_devices, 0),
        warnings=warnings,
    )


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
    mark_overrides(device, {"display_name", "role", "model", "mgmt_ip", "enabled"})
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
    port.virtual = is_virtual_port_name(name)
    port.alias = clean_optional_str(data.get("alias"))
    port.oper_status = clean_optional_str(data.get("operStatus") or data.get("oper_status")) or "unknown"
    port.admin_status = clean_optional_str(data.get("adminStatus") or data.get("admin_status")) or "unknown"
    port.speed_mbps = float_or_none(data.get("speedMbps") or data.get("speed_mbps"))
    port.media = clean_optional_str(data.get("media"))
    port.mac_address = normalize_mac_address(data.get("macAddress") or data.get("mac_address"))
    port.port_role = clean_optional_str(data.get("portRole") or data.get("port_role"))
    port.vlan_summary = clean_optional_str(data.get("vlanSummary") or data.get("vlan_summary"))
    port.poe_status = clean_optional_str(data.get("poeStatus") or data.get("poe_status"))
    port.stale = bool(data.get("stale", False))
    mark_overrides(port, {"name", "alias", "speed_mbps", "media", "mac_address", "port_role", "vlan_summary", "poe_status"})
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
    link.vlan_id = vlan_id_or_none(data.get("vlanId") or data.get("vlan_id"))
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


def vlan_id_or_none(value: object) -> int | None:
    vlan_id = int_or_none(value)
    if vlan_id is None:
        return None
    return vlan_id if 1 <= vlan_id <= 4094 else None


@router.post("/cable-links", response_model=CableLinkRead)
async def create_cable_link(
    payload: CableLinkCreate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> CableLink:
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
    existing_pair = existing.scalar_one_or_none()
    if existing_pair:
        if not payload.replaceExisting:
            raise HTTPException(status_code=409, detail="Cable link already exists")
        existing_pair.label = payload.label
        existing_pair.cable_no = payload.cableNo
        existing_pair.vlan_id = payload.vlanId
        existing_pair.color = payload.color
        existing_pair.notes = payload.notes
        existing_pair.verified_at = payload.verifiedAt
        existing_pair.created_by = payload.createdBy
        await record_audit(session, request, "cable.update", "cable", existing_pair.id, {"replaceExisting": True})
        await session.commit()
        await session.refresh(existing_pair)
        return existing_pair
    conflicts = await cable_conflicts_for_ports(session, [endpoint_a, endpoint_b])
    if conflicts and not payload.replaceExisting:
        raise HTTPException(status_code=409, detail="Cable endpoint is already connected")
    for conflict in conflicts:
        await session.delete(conflict)
    link = CableLink(
        endpoint_a_port_id=endpoint_a,
        endpoint_b_port_id=endpoint_b,
        label=payload.label,
        cable_no=payload.cableNo,
        vlan_id=payload.vlanId,
        color=payload.color,
        notes=payload.notes,
        verified_at=payload.verifiedAt,
        created_by=payload.createdBy,
    )
    session.add(link)
    await session.flush()
    await record_audit(
        session,
        request,
        "cable.create",
        "cable",
        link.id,
        {"endpointAPortId": endpoint_a, "endpointBPortId": endpoint_b, "replacedLinks": [item.id for item in conflicts]},
    )
    await session.commit()
    await session.refresh(link)
    return link


@router.patch("/cable-links/{link_id}", response_model=CableLinkRead)
async def update_cable_link(
    link_id: int,
    payload: CableLinkUpdate,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> CableLink:
    link = await get_link_or_404(session, link_id)
    data = payload.model_dump(exclude_unset=True)
    field_map = {"cableNo": "cable_no", "vlanId": "vlan_id", "verifiedAt": "verified_at", "createdBy": "created_by"}
    for key, value in data.items():
        setattr(link, field_map.get(key, key), value)
    await record_audit(session, request, "cable.update", "cable", link.id, data)
    await session.commit()
    await session.refresh(link)
    return link


@router.delete("/cable-links/{link_id}")
async def delete_cable_link(
    link_id: int,
    request: Request,
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    link = await get_link_or_404(session, link_id)
    await record_audit(session, request, "cable.delete", "cable", link.id, {"endpointAPortId": link.endpoint_a_port_id, "endpointBPortId": link.endpoint_b_port_id})
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
    _permission: None = Depends(require_write_permission),
    session: AsyncSession = Depends(get_session),
    zabbix: ZabbixClient = Depends(zabbix_from_request),
    settings: Settings = Depends(get_settings),
) -> ZabbixSyncRun:
    if not settings.zabbix_configured():
        raise HTTPException(status_code=503, detail="Zabbix credentials are not configured")
    run = await run_zabbix_sync_serialized(request, session, zabbix, settings)
    await record_audit(session, request, "sync.zabbix.run", "sync_run", run.id, {"status": run.status})
    await session.commit()
    await session.refresh(run)
    return run


@router.get("/sync/status", response_model=SyncStatus)
async def sync_status(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> SyncStatus:
    result = await session.execute(select(ZabbixSyncRun).order_by(ZabbixSyncRun.id.desc()).limit(1))
    latest = result.scalar_one_or_none()
    return SyncStatus(
        latest=SyncRunRead.model_validate(latest) if latest else None,
        zabbixConfigured=settings.zabbix_configured(),
        readOnly=settings.read_only_mode,
    )


@router.get("/sync/runs", response_model=list[SyncRunRead])
async def sync_runs(
    limit: int = Query(8, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[ZabbixSyncRun]:
    result = await session.execute(select(ZabbixSyncRun).order_by(ZabbixSyncRun.id.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/quality/issues", response_model=list[QualityIssue])
async def quality_issues(
    topology_id: int | None = Query(None, alias="topologyId"),
    session: AsyncSession = Depends(get_session),
) -> list[QualityIssue]:
    if topology_id is not None:
        await get_topology_by_id(session, topology_id)
    return await collect_quality_issues(session, topology_id)


@router.get("/audit-logs", response_model=list[AuditLogRead])
async def audit_logs(
    limit: int = Query(50, ge=1, le=200),
    resource_type: str | None = Query(None, alias="resourceType"),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    stmt = select(AuditLog)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    result = await session.execute(stmt.order_by(AuditLog.id.desc()).limit(limit))
    return list(result.scalars().all())


async def collect_quality_issues(session: AsyncSession, topology_id: int | None = None) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    scoped_device_ids: set[int] | None = None
    if topology_id is not None:
        scoped_device_ids = set(await get_topology_ids_for_graph(session, topology_id))

    device_stmt = select(Device)
    if scoped_device_ids is not None:
        if not scoped_device_ids:
            return []
        device_stmt = device_stmt.where(Device.id.in_(scoped_device_ids))
    devices = list((await session.execute(device_stmt)).scalars().all())
    device_by_id = {device.id: device for device in devices}
    for device in devices:
        if device.stale:
            issues.append(QualityIssue(id=f"device-stale-{device.id}", severity="warning", category="stale", title="设备已过期", message=f"{device.display_name} 最近未在同步结果中出现", deviceId=device.id, topologyId=topology_id))
        if not device.enabled:
            issues.append(QualityIssue(id=f"device-disabled-{device.id}", severity="info", category="disabled", title="设备已禁用", message=f"{device.display_name} 已禁用但仍保留在台账中", deviceId=device.id, topologyId=topology_id))

    port_stmt = select(Port)
    if scoped_device_ids is not None:
        port_stmt = port_stmt.where(Port.device_id.in_(scoped_device_ids))
    ports = list((await session.execute(port_stmt)).scalars().all())
    port_by_id = {port.id: port for port in ports}
    for port in ports:
        if port.stale:
            issues.append(QualityIssue(id=f"port-stale-{port.id}", severity="warning", category="stale", title="端口已过期", message=f"{device_by_id.get(port.device_id).display_name if device_by_id.get(port.device_id) else port.device_id} / {port.name} 最近未出现", deviceId=port.device_id, portId=port.id, topologyId=topology_id))

    issues.extend(await duplicate_device_value_issues(session, Device.mgmt_ip, "mgmtIp", "重复管理 IP", topology_id, scoped_device_ids))
    issues.extend(await duplicate_port_value_issues(session, Port.mac_address, "mac", "重复 MAC", topology_id, scoped_device_ids))

    links = list((await session.execute(select(CableLink))).scalars().all())
    port_ids_in_scope = set(port_by_id)
    endpoint_usage: dict[int, list[CableLink]] = {}
    for link in links:
        link_in_scope = topology_id is None or (link.endpoint_a_port_id in port_ids_in_scope or link.endpoint_b_port_id in port_ids_in_scope)
        if not link_in_scope:
            continue
        if topology_id is None or link.endpoint_a_port_id in port_ids_in_scope:
            endpoint_usage.setdefault(link.endpoint_a_port_id, []).append(link)
        if topology_id is None or link.endpoint_b_port_id in port_ids_in_scope:
            endpoint_usage.setdefault(link.endpoint_b_port_id, []).append(link)
        a = port_by_id.get(link.endpoint_a_port_id) or await session.get(Port, link.endpoint_a_port_id)
        b = port_by_id.get(link.endpoint_b_port_id) or await session.get(Port, link.endpoint_b_port_id)
        for endpoint in [a, b]:
            if endpoint and endpoint.oper_status in {"down", "shutdown", "lower-layer-down"}:
                issues.append(QualityIssue(id=f"linked-down-{link.id}-{endpoint.id}", severity="warning", category="link", title="已连接端口不可用", message=f"{endpoint.name} 已连接但状态为 {endpoint.oper_status}", deviceId=endpoint.device_id, portId=endpoint.id, linkId=link.id, topologyId=topology_id))
        if topology_id is not None and a and b:
            a_in = a.device_id in scoped_device_ids if scoped_device_ids is not None else True
            b_in = b.device_id in scoped_device_ids if scoped_device_ids is not None else True
            if a_in != b_in:
                issues.append(QualityIssue(id=f"cross-topology-{link.id}", severity="info", category="topology", title="线缆跨拓扑", message="线缆另一端设备不在当前拓扑中", linkId=link.id, topologyId=topology_id))

    for port_id, used_links in endpoint_usage.items():
        if len(used_links) > 1:
            port = port_by_id.get(port_id) or await session.get(Port, port_id)
            issues.append(QualityIssue(id=f"multi-cable-{port_id}", severity="critical", category="link", title="端口连接多根线缆", message=f"{port.name if port else port_id} 同时连接了 {len(used_links)} 根线缆", deviceId=port.device_id if port else None, portId=port_id, topologyId=topology_id))

    linked_port_ids = set(endpoint_usage)
    for port in ports:
        device = device_by_id.get(port.device_id)
        if device and device.role == "server" and port.oper_status == "up" and not port.virtual and port.id not in linked_port_ids:
            issues.append(QualityIssue(id=f"server-up-unlinked-{port.id}", severity="info", category="inventory", title="服务器 up 端口未接线", message=f"{device.display_name} / {port.name} 为 up 但没有线缆记录", deviceId=device.id, portId=port.id, topologyId=topology_id))

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(issues, key=lambda issue: (severity_order[issue.severity], issue.category, issue.id))


async def duplicate_device_value_issues(session: AsyncSession, column, category: str, title: str, topology_id: int | None, scoped_device_ids: set[int] | None) -> list[QualityIssue]:
    stmt = select(column, func.count(Device.id)).where(column.is_not(None), column != "").group_by(column).having(func.count(Device.id) > 1)
    if scoped_device_ids is not None:
        stmt = stmt.where(Device.id.in_(scoped_device_ids))
    rows = (await session.execute(stmt)).all()
    return [
        QualityIssue(id=f"duplicate-device-{category}-{value}", severity="warning", category=category, title=title, message=f"{value} 被 {count} 台设备使用", topologyId=topology_id)
        for value, count in rows
    ]


async def duplicate_port_value_issues(session: AsyncSession, column, category: str, title: str, topology_id: int | None, scoped_device_ids: set[int] | None) -> list[QualityIssue]:
    stmt = select(column, func.count(Port.id)).where(column.is_not(None), column != "").group_by(column).having(func.count(Port.id) > 1)
    if scoped_device_ids is not None:
        stmt = stmt.where(Port.device_id.in_(scoped_device_ids))
    rows = (await session.execute(stmt)).all()
    return [
        QualityIssue(id=f"duplicate-port-{category}-{value}", severity="warning", category=category, title=title, message=f"{value} 被 {count} 个端口使用", topologyId=topology_id)
        for value, count in rows
    ]


def _normalize_ingest_port_identity(name: str) -> str:
    return normalize_port_name(name)


def _normalize_ingest_source(source: str | None) -> str:
    return (normalize_port_name(source or "")[:60] or "agent")


def _source_port_identity(source: str, identity: str) -> str:
    return f"{source}:{identity}"


def _normalize_patterns(patterns: list[str]) -> list[str]:
    normalized: list[str] = []
    for pattern in patterns:
        text = pattern.strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _is_physical_ingest_port(name: str | None, strict_physical_ports: bool, patterns: list[str]) -> bool:
    if name is None:
        return False
    if not strict_physical_ports:
        return True
    if is_virtual_port_name(name):
        return False
    if not patterns:
        return True
    normalized = name.strip().lower()
    if not normalized:
        return False
    return any(pattern in normalized for pattern in patterns)


def _ingest_device_cache_keys(payload: IngestDevice, device: Device) -> list[str]:
    keys: list[str] = [f"name:{payload.displayName.strip().lower()}"]
    if payload.zabbixHostid:
        keys.append(f"host:{payload.zabbixHostid.strip()}")
    if payload.mgmtIp:
        keys.append(f"mgmt:{payload.mgmtIp.strip()}")
    keys.append(f"id:{device.id}")
    return keys


async def _find_or_create_device_for_ingest(session: AsyncSession, source: str, payload: IngestDevice) -> Device:
    display_name = clean_required_text(payload.displayName, "Device display name is required")
    zabbix_hostid = clean_optional_str(payload.zabbixHostid)
    mgmt_ip = clean_optional_str(payload.mgmtIp)
    role = payload.role
    seen_at = _parse_iso_datetime(payload.lastSeenAt)

    device: Device | None = None
    if zabbix_hostid:
        result = await session.execute(select(Device).where(Device.zabbix_hostid == zabbix_hostid))
        device = result.scalar_one_or_none()
    if device is None and mgmt_ip:
        result = await session.execute(select(Device).where(Device.mgmt_ip == mgmt_ip))
        device = result.scalar_one_or_none()
    if device is None:
        result = await session.execute(select(Device).where(Device.display_name == display_name, Device.role == role))
        device = result.scalar_one_or_none()
    if device is None:
        device = Device(
            source=source,
            display_name=display_name,
            role=role,
            model=clean_optional_str(payload.model),
            mgmt_ip=mgmt_ip,
            zabbix_hostid=zabbix_hostid,
            status=payload.status or "online",
            health=payload.health or "unknown",
            enabled=True,
            stale=False,
        )
        if seen_at is not None:
            device.last_seen_at = seen_at
        session.add(device)
        await session.flush()
        return device

    if device.source == source or device.source not in PROTECTED_DEVICE_SOURCES:
        device.source = source
    set_unless_overridden(device, "role", role)
    set_unless_overridden(device, "display_name", display_name)
    set_optional_unless_overridden(device, "model", clean_optional_str(payload.model))
    set_optional_unless_overridden(device, "mgmt_ip", mgmt_ip)
    if zabbix_hostid:
        device.zabbix_hostid = zabbix_hostid
    if payload.status:
        device.status = payload.status
    if payload.health:
        device.health = payload.health
    if payload.enabled is not None:
        set_unless_overridden(device, "enabled", payload.enabled)
    if seen_at is not None:
        device.last_seen_at = seen_at
    device.stale = False
    if not device.status:
        device.status = "online"
    return device


async def _upsert_ingest_port(
    session: AsyncSession,
    device_id: int,
    source: str,
    payload: IngestPort,
    *,
    strict_physical_ports: bool = False,
) -> tuple[str | None, bool]:
    name = clean_required_text(payload.name, "Port name is required")
    if strict_physical_ports and is_virtual_port_name(name):
        return None, False

    identity = _normalize_ingest_port_identity(name)
    if not identity:
        return None, False
    source_key = _normalize_ingest_source(source)
    port_identity = _source_port_identity(source_key, identity)
    legacy_manual_identity = _source_port_identity("manual", identity)
    existing_port = await _find_existing_ingest_port(
        session,
        device_id=device_id,
        source=source_key,
        identity=port_identity,
        legacy_manual_identity=legacy_manual_identity,
        name=name,
        if_index=payload.ifIndex,
    )

    if existing_port is None:
        existing_port = Port(
            device_id=device_id,
            source=source_key,
            identity=port_identity,
            name=name,
        )
        session.add(existing_port)

    if existing_port.source == source_key or existing_port.source not in PROTECTED_PORT_SOURCES:
        existing_port.source = source_key
        existing_port.identity = port_identity
    existing_port.if_index = payload.ifIndex if payload.ifIndex is not None else existing_port.if_index
    set_unless_overridden(existing_port, "name", name)
    existing_port.virtual = is_virtual_port_name(existing_port.name)
    set_optional_unless_overridden(existing_port, "alias", clean_optional_str(payload.alias))
    existing_port.oper_status = clean_optional_str(payload.operStatus) or existing_port.oper_status or "unknown"
    existing_port.admin_status = clean_optional_str(payload.adminStatus) or existing_port.admin_status or "unknown"
    if payload.speedMbps is not None:
        set_unless_overridden(existing_port, "speed_mbps", payload.speedMbps)
    set_optional_unless_overridden(existing_port, "media", clean_optional_str(payload.media))
    set_optional_unless_overridden(existing_port, "mac_address", normalize_mac_address(payload.macAddress))
    set_optional_unless_overridden(existing_port, "port_role", clean_optional_str(payload.portRole))
    set_optional_unless_overridden(existing_port, "vlan_summary", clean_optional_str(payload.vlanSummary))
    set_optional_unless_overridden(existing_port, "poe_status", clean_optional_str(payload.poeStatus))
    existing_port.last_traffic_in_bps = payload.lastTrafficInBps if payload.lastTrafficInBps is not None else existing_port.last_traffic_in_bps
    existing_port.last_traffic_out_bps = payload.lastTrafficOutBps if payload.lastTrafficOutBps is not None else existing_port.last_traffic_out_bps
    existing_port.rx_errors = payload.rxErrors if payload.rxErrors is not None else existing_port.rx_errors
    existing_port.tx_errors = payload.txErrors if payload.txErrors is not None else existing_port.tx_errors
    existing_port.stale = False
    return _normalize_ingest_port_identity(name), True


async def _find_existing_ingest_port(
    session: AsyncSession,
    *,
    device_id: int,
    source: str,
    identity: str,
    legacy_manual_identity: str,
    name: str,
    if_index: int | None,
) -> Port | None:
    result = await session.execute(select(Port).where(Port.device_id == device_id, Port.identity == identity))
    port = result.scalar_one_or_none()
    if port is not None:
        return port

    result = await session.execute(
        select(Port).where(
            Port.device_id == device_id,
            Port.identity == legacy_manual_identity,
            Port.source == source,
        )
    )
    port = result.scalar_one_or_none()
    if port is not None:
        return port

    if if_index is not None:
        result = await session.execute(select(Port).where(Port.device_id == device_id, Port.if_index == if_index))
        candidates = list(result.scalars().all())
        port = _best_ingest_port_candidate(candidates, source, identity, legacy_manual_identity)
        if port is not None:
            return port

    result = await session.execute(select(Port).where(Port.device_id == device_id, Port.name == name))
    candidates = list(result.scalars().all())
    return _best_ingest_port_candidate(candidates, source, identity, legacy_manual_identity)


def _best_ingest_port_candidate(
    candidates: list[Port],
    source: str,
    identity: str,
    legacy_manual_identity: str,
) -> Port | None:
    if not candidates:
        return None
    for port in candidates:
        if port.identity == identity:
            return port
    for port in candidates:
        if port.source == source and port.identity == legacy_manual_identity:
            return port
    for port in candidates:
        if port.source in PROTECTED_PORT_SOURCES:
            return port
    return candidates[0]


async def _resolve_ingest_endpoint(
    session: AsyncSession,
    endpoint: IngestEndpointRef,
    device_cache: dict[str, Device],
    ports_by_device: dict[int, list[Port]],
) -> Port | None:
    device: Device | None = None
    target_mac = normalize_mac_address(endpoint.macAddress)
    if endpoint.deviceId is not None:
        for candidate in device_cache.values():
            if candidate.id == endpoint.deviceId:
                device = candidate
                break
        if device is None:
            device = await session.get(Device, endpoint.deviceId)
    if device is None and endpoint.zabbixHostid:
        device = device_cache.get(f"host:{endpoint.zabbixHostid}") or next(
            (item for item in device_cache.values() if item.zabbix_hostid == endpoint.zabbixHostid),
            None,
        )
        if device is None:
            result = await session.execute(select(Device).where(Device.zabbix_hostid == endpoint.zabbixHostid))
            device = result.scalar_one_or_none()
    if device is None and endpoint.displayName:
        key = f"name:{endpoint.displayName.strip().lower()}"
        device = device_cache.get(key)
        if device is None:
            result = await session.execute(select(Device).where(Device.display_name == endpoint.displayName))
            device = result.scalar_one_or_none()
    if device is None and endpoint.mgmtIp:
        result = await session.execute(select(Device).where(Device.mgmt_ip == endpoint.mgmtIp))
        device = result.scalar_one_or_none()

    if device is None:
        if target_mac:
            return await _resolve_unique_port_by_mac(session, target_mac)
        return None

    candidate_ports = ports_by_device.get(device.id, [])
    if not candidate_ports:
        result = await session.execute(select(Port).where(Port.device_id == device.id))
        candidate_ports = list(result.scalars().all())
    if target_mac:
        matches = [port for port in candidate_ports if port.mac_address == target_mac and not port.stale]
        return matches[0] if len(matches) == 1 else None
    if endpoint.ifIndex is not None:
        for port in candidate_ports:
            if port.if_index == endpoint.ifIndex:
                return port

    target_name = clean_optional_str(endpoint.portName)
    if target_name:
        candidate_key = _normalize_ingest_port_identity(target_name)
        for port in candidate_ports:
            if _normalize_ingest_port_identity(port.name) == candidate_key:
                return port

    return None


async def _resolve_unique_port_by_mac(session: AsyncSession, mac_address: str) -> Port | None:
    result = await session.execute(select(Port).where(Port.mac_address == mac_address, Port.stale.is_(False)))
    matches = list(result.scalars().all())
    return matches[0] if len(matches) == 1 else None


async def _get_or_create_link(session: AsyncSession, endpoint_a: Port, endpoint_b: Port) -> CableLink:
    endpoint_a_id, endpoint_b_id = sorted([endpoint_a.id, endpoint_b.id])
    result = await session.execute(
        select(CableLink).where(
            CableLink.endpoint_a_port_id == endpoint_a_id,
            CableLink.endpoint_b_port_id == endpoint_b_id,
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        conflicts = await cable_conflicts_for_ports(session, [endpoint_a_id, endpoint_b_id])
        for conflict in conflicts:
            if {conflict.endpoint_a_port_id, conflict.endpoint_b_port_id} != {endpoint_a_id, endpoint_b_id}:
                await session.delete(conflict)
        link = CableLink(endpoint_a_port_id=endpoint_a_id, endpoint_b_port_id=endpoint_b_id)
        session.add(link)
    return link


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail=f"Invalid datetime: {value}")


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


async def cable_conflicts_for_ports(session: AsyncSession, port_ids: list[int]) -> list[CableLink]:
    if not port_ids:
        return []
    result = await session.execute(
        select(CableLink).where(
            or_(
                CableLink.endpoint_a_port_id.in_(port_ids),
                CableLink.endpoint_b_port_id.in_(port_ids),
            )
        )
    )
    return list(result.scalars().all())


def port_from_create(device_id: int, payload: PortCreate, *, name: str | None = None) -> Port:
    clean_name = clean_required_text(name or payload.name, "Port name is required")
    identity = manual_port_identity(clean_name)
    return Port(
        device_id=device_id,
        source="manual",
        identity=identity,
        if_index=payload.ifIndex,
        name=clean_name,
        virtual=is_virtual_port_name(clean_name),
        alias=payload.alias,
        oper_status="unknown",
        admin_status="unknown",
        speed_mbps=payload.speedMbps,
        media=payload.media,
        mac_address=normalize_mac_address(payload.macAddress),
        port_role=payload.portRole,
        vlan_summary=payload.vlanSummary,
        poe_status=payload.poeStatus,
        stale=False,
    )


def manual_port_identity(name: str) -> str:
    return f"manual:{name.strip().lower()}"


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
