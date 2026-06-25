from __future__ import annotations

from sqlalchemy import select

from app.config import Settings
from app.db_models import CableLink, Device, Port
from app.services.sync import run_zabbix_sync


class FakeZabbix:
    def __init__(self, hosts, items):
        self._hosts = hosts
        self._items = items

    async def hosts(self):
        return self._hosts

    async def items_for_hosts(self, hostids):
        return [item for item in self._items if item["hostid"] in hostids]


async def test_sync_adds_profile_ports_and_preserves_manual_cables(session):
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "101",
            "host": "core-1",
            "name": "核心交换机 E1",
            "groups": [{"name": "exchange"}],
            "interfaces": [{"ip": "192.168.10.10"}],
            "inventory": {"model": "RG-S6220-48XS6QXS-H"},
        },
        {
            "hostid": "201",
            "host": "negev-01",
            "name": "Negev-01",
            "groups": [{"name": "Negev"}],
            "interfaces": [{"ip": "192.168.20.11"}],
            "inventory": {"model": "PowerEdge"},
        },
    ]
    items = [
        item("101", "1", "Interface XGE0/1 name", "net.if.name[ifName.1]", "XGE0/1"),
        item("101", "2", "Interface XGE0/1 operational status", "net.if.status[ifOperStatus.1]", "1"),
        item("201", "3", "Interface ens1f0 name", "net.if.name[ifName.7]", "ens1f0"),
        item("201", "4", "Interface ens1f0 operational status", "net.if.status[ifOperStatus.7]", "1"),
    ]

    run = await run_zabbix_sync(session, FakeZabbix(hosts, items), settings)
    assert run.status == "success"

    devices = (await session.execute(select(Device))).scalars().all()
    assert {device.role for device in devices} == {"switch", "server"}
    switch = next(device for device in devices if device.role == "switch")
    server = next(device for device in devices if device.role == "server")

    switch_ports = (await session.execute(select(Port).where(Port.device_id == switch.id))).scalars().all()
    assert len(switch_ports) == 54
    xge1 = next(port for port in switch_ports if port.name == "XGE0/1")
    server_port = (await session.execute(select(Port).where(Port.device_id == server.id))).scalar_one()
    link = CableLink(endpoint_a_port_id=xge1.id, endpoint_b_port_id=server_port.id, label="A-01")
    session.add(link)
    await session.commit()

    run2 = await run_zabbix_sync(session, FakeZabbix(hosts, items), settings)
    assert run2.status == "success"
    assert (await session.execute(select(CableLink))).scalar_one().label == "A-01"


async def test_missing_zabbix_device_is_marked_stale(session):
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    host = {
        "hostid": "101",
        "host": "core-1",
        "name": "核心交换机 E1",
        "groups": [{"name": "exchange"}],
        "interfaces": [{"ip": "192.168.10.10"}],
        "inventory": {"model": "RG-S6220-48XS6QXS-H"},
    }
    await run_zabbix_sync(session, FakeZabbix([host], [item("101", "1", "Interface XGE0/1 name", "net.if.name[ifName.1]", "XGE0/1")]), settings)
    await run_zabbix_sync(session, FakeZabbix([], []), settings)

    device = (await session.execute(select(Device))).scalar_one()
    assert device.stale is True
    assert device.health == "stale"


async def test_manual_ports_keep_zabbix_device_visible_when_interfaces_are_missing(session):
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    host = {
        "hostid": "201",
        "host": "negev-01",
        "name": "Negev-01",
        "groups": [{"name": "Negev"}],
        "interfaces": [{"ip": "192.168.20.11"}],
        "inventory": {"model": "PowerEdge"},
    }
    await run_zabbix_sync(session, FakeZabbix([host], [item("201", "1", "Interface ens1f0 name", "net.if.name[ifName.7]", "ens1f0")]), settings)
    device = (await session.execute(select(Device))).scalar_one()
    session.add(
        Port(
            device_id=device.id,
            source="manual",
            identity="manual:idrac",
            name="iDRAC",
            oper_status="unknown",
            admin_status="unknown",
            port_role="management",
            vlan_summary="PVID 99",
            stale=False,
        )
    )
    await session.commit()

    run = await run_zabbix_sync(session, FakeZabbix([host], []), settings)
    assert run.status == "success"

    refreshed = (await session.execute(select(Device))).scalar_one()
    assert refreshed.stale is False
    assert refreshed.health != "stale"


def item(hostid: str, itemid: str, name: str, key: str, value: str) -> dict:
    return {
        "hostid": hostid,
        "itemid": itemid,
        "name": name,
        "key_": key,
        "lastvalue": value,
        "lastclock": "1710000000",
        "units": "",
        "value_type": "0",
        "status": "0",
        "state": "0",
    }
