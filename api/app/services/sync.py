from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..clients.zabbix import ZabbixClient
from ..config import Settings
from ..db_models import Device, Port, ZabbixSyncRun
from .mapper import DeviceSnapshot, PortSnapshot, map_zabbix_inventory, normalize_port_name
from .profiles import profile_for_model


async def run_zabbix_sync(session: AsyncSession, zabbix: ZabbixClient, settings: Settings) -> ZabbixSyncRun:
    snapshots = await collect_zabbix_snapshots(zabbix, settings)
    return await run_zabbix_sync_from_snapshots(session, settings, snapshots)


async def run_zabbix_sync_from_snapshots(
    session: AsyncSession,
    settings: Settings,
    snapshots: list[DeviceSnapshot],
) -> ZabbixSyncRun:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    run = ZabbixSyncRun(status="running", started_at=started_at)
    session.add(run)
    await session.flush()
    try:
        upserted_devices, upserted_ports = await upsert_zabbix_snapshots(session, snapshots)
        seen_hostids = {snapshot.zabbix_hostid for snapshot in snapshots}

        upserted_devices_count = len(upserted_devices)

        stale_devices = await mark_missing_devices_stale(session, seen_hostids)
        run.status = "success"
        run.finished_at = datetime.now(timezone.utc)
        run.duration_ms = (time.perf_counter() - started) * 1000
        run.devices_seen = len(snapshots)
        run.devices_upserted = upserted_devices_count
        run.ports_upserted = upserted_ports
        run.stale_devices = stale_devices
        await session.commit()
        await session.refresh(run)
        return run
    except Exception as exc:
        await session.rollback()
        run = ZabbixSyncRun(
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            duration_ms=(time.perf_counter() - started) * 1000,
            error_message=str(exc),
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run


async def collect_zabbix_snapshots(zabbix: ZabbixClient, settings: Settings) -> list[DeviceSnapshot]:
    hosts = await zabbix.hosts()
    if not hosts:
        return []
    hostids = [str(host.get("hostid")) for host in hosts if host.get("hostid")]
    if not hostids:
        return []
    items = await zabbix.items_for_hosts(hostids)
    return map_zabbix_inventory(hosts, items, settings)


async def upsert_zabbix_snapshots(
    session: AsyncSession,
    snapshots: list[DeviceSnapshot],
) -> tuple[list[Device], int]:
    upserted_devices: list[Device] = []
    upserted_ports = 0
    for snapshot in snapshots:
        device = await upsert_device(session, snapshot)
        upserted_devices.append(device)
        seen_port_identities = set()
        for port_snapshot in snapshot.ports:
            await upsert_port(session, device, port_snapshot)
            seen_port_identities.add(port_snapshot.identity)
            upserted_ports += 1
        upserted_ports += await ensure_profile_ports(session, device)
        await mark_missing_ports_stale(session, device, seen_port_identities)
    return upserted_devices, upserted_ports


async def upsert_device(session: AsyncSession, snapshot: DeviceSnapshot) -> Device:
    result = await session.execute(select(Device).where(Device.zabbix_hostid == snapshot.zabbix_hostid))
    device = result.scalar_one_or_none()
    if device is None:
        device = Device(source="zabbix", zabbix_hostid=snapshot.zabbix_hostid, display_name=snapshot.display_name)
        session.add(device)
        await session.flush()
    device.source = "zabbix"
    device.role = snapshot.role
    device.display_name = snapshot.display_name
    device.model = snapshot.model
    device.mgmt_ip = snapshot.mgmt_ip
    device.status = snapshot.status
    device.health = snapshot.health
    device.last_seen_at = snapshot.last_seen_at
    device.stale = False
    return device


async def upsert_port(session: AsyncSession, device: Device, snapshot: PortSnapshot) -> Port:
    result = await session.execute(select(Port).where(Port.device_id == device.id, Port.identity == snapshot.identity))
    port = result.scalar_one_or_none()
    if port is None:
        port = await find_profile_port_by_name(session, device.id, snapshot.name)
    if port is None:
        port = Port(device_id=device.id, source="zabbix", identity=snapshot.identity, name=snapshot.name)
        session.add(port)
        await session.flush()
    port.source = "zabbix"
    port.identity = snapshot.identity
    port.if_index = snapshot.if_index
    port.name = snapshot.name
    port.alias = snapshot.alias
    port.oper_status = snapshot.oper_status
    port.admin_status = snapshot.admin_status
    port.speed_mbps = snapshot.speed_mbps
    port.media = snapshot.media
    port.port_role = snapshot.port_role
    port.vlan_summary = snapshot.vlan_summary
    port.poe_status = snapshot.poe_status
    port.last_traffic_in_bps = snapshot.last_traffic_in_bps
    port.last_traffic_out_bps = snapshot.last_traffic_out_bps
    port.rx_errors = snapshot.rx_errors
    port.tx_errors = snapshot.tx_errors
    port.traffic_in_itemid = snapshot.traffic_in_itemid
    port.traffic_out_itemid = snapshot.traffic_out_itemid
    port.oper_itemid = snapshot.oper_itemid
    port.stale = False
    return port


async def find_profile_port_by_name(session: AsyncSession, device_id: int, name: str) -> Port | None:
    normalized = normalize_port_name(name)
    result = await session.execute(select(Port).where(Port.device_id == device_id))
    for port in result.scalars().all():
        if port.source == "profile" and normalize_port_name(port.name) == normalized:
            return port
    return None


async def ensure_profile_ports(session: AsyncSession, device: Device) -> int:
    if device.role != "switch":
        return 0
    profile = profile_for_model(device.model)
    if profile is None:
        return 0
    result = await session.execute(select(Port).where(Port.device_id == device.id))
    existing = result.scalars().all()
    existing_names = {normalize_port_name(port.name) for port in existing}
    created = 0
    for profile_port in profile.ports:
        if normalize_port_name(profile_port.name) in existing_names:
            continue
        session.add(
            Port(
                device_id=device.id,
                source="profile",
                identity=f"profile:{normalize_port_name(profile_port.name)}",
                name=profile_port.name,
                oper_status="unknown",
                admin_status="unknown",
                speed_mbps=profile_port.speed_mbps,
                media=profile_port.media,
                port_role=profile_port.role,
                stale=False,
            )
        )
        created += 1
    return created


async def mark_missing_ports_stale(session: AsyncSession, device: Device, seen_identities: set[str]) -> None:
    result = await session.execute(select(Port).where(Port.device_id == device.id, Port.source == "zabbix"))
    for port in result.scalars().all():
        if port.identity not in seen_identities:
            port.stale = True


async def mark_missing_devices_stale(session: AsyncSession, seen_hostids: set[str]) -> int:
    result = await session.execute(select(Device).where(Device.source == "zabbix"))
    manual_ports = await session.execute(select(Port.device_id).where(Port.source == "manual", Port.stale.is_(False)))
    devices_with_manual_ports = set(manual_ports.scalars().all())
    stale = 0
    for device in result.scalars().all():
        if device.zabbix_hostid and device.zabbix_hostid not in seen_hostids:
            if device.id in devices_with_manual_ports:
                device.stale = False
                if device.health == "stale":
                    device.health = "unknown"
                continue
            device.stale = True
            device.health = "stale"
            stale += 1
    return stale
