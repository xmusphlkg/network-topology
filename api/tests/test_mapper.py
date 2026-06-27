from __future__ import annotations

from app.config import Settings
from app.services.mapper import is_virtual_port_name, map_zabbix_inventory, normalize_speed_mbps


def test_ruijie_s6220_ports_are_discovered_from_zabbix_items():
    settings = Settings(environment="test", switch_group_terms="exchange,switch,交换机", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "101",
            "host": "core-1",
            "name": "核心交换机 E1",
            "groups": [{"name": "exchange"}],
            "interfaces": [{"ip": "192.168.10.10"}],
            "inventory": {"model": "RG-S6220-48XS6QXS-H"},
        }
    ]
    items = [
        item("101", "1", "Interface XGE0/1 name", "net.if.name[ifName.1]", "XGE0/1"),
        item("101", "2", "Interface XGE0/1 operational status", "net.if.status[ifOperStatus.1]", "1"),
        item("101", "3", "Interface XGE0/1 speed", "net.if.speed[ifHighSpeed.1]", "10000"),
        item("101", "4", "Interface XGE0/1 incoming", "net.if.in[ifHCInOctets.1]", "870280"),
        item("101", "5", "Interface XGE0/1 outgoing", "net.if.out[ifHCOutOctets.1]", "925130"),
        item("101", "6", "Interface XGE0/2 name", "net.if.name[ifName.2]", "XGE0/2"),
        item("101", "7", "Interface XGE0/2 operational status", "net.if.status[ifOperStatus.2]", "2"),
        item("101", "8", "Interface XGE0/2 speed", "net.if.speed[ifHighSpeed.2]", "1000"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert len(snapshots) == 1
    assert snapshots[0].role == "switch"
    assert snapshots[0].model == "RG-S6220-48XS6QXS-H"
    first = snapshots[0].ports[0]
    second = snapshots[0].ports[1]
    assert first.name == "XGE0/1"
    assert first.oper_status == "up"
    assert first.speed_mbps == 10000
    assert first.last_traffic_in_bps == 870280
    assert second.oper_status == "down"
    assert second.speed_mbps == 1000


def test_speed_normalization_handles_bps_and_highspeed_mbps_values():
    assert normalize_speed_mbps(10_000, "", "net.if.speed[ifHighSpeed.1] Interface speed") == 10_000
    assert normalize_speed_mbps(400_000, "", "net.if.speed[ifHighSpeed.1] Interface speed") == 400_000
    assert normalize_speed_mbps(10_000_000_000, "", "net.if.speed[ifHighSpeed.1] Interface speed") == 10_000
    assert normalize_speed_mbps(100_000_000, "bps", "net.if.speed[ifSpeed.1] Interface speed") == 100


def test_vlan_items_are_attached_to_matching_interface():
    settings = Settings(environment="test", switch_group_terms="switch", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "101",
            "host": "switch-1",
            "name": "Switch 1",
            "groups": [{"name": "switch"}],
            "interfaces": [{"ip": "192.168.10.10"}],
            "inventory": {"model": "Cisco Nexus"},
        }
    ]
    items = [
        item("101", "1", "Interface Ethernet1/1 name", "net.if.name[ifName.11]", "Ethernet1/1"),
        item("101", "2", "Interface Ethernet1/1 PVID", "dot1qPvid[ifName.11]", "10"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert snapshots[0].ports[0].name == "Ethernet1/1"
    assert snapshots[0].ports[0].vlan_summary == "10"


def test_negev_server_interfaces_keep_linux_ifname():
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "201",
            "host": "negev-01",
            "name": "Negev-01",
            "groups": [{"name": "Negev"}],
            "interfaces": [{"ip": "192.168.20.11"}],
            "inventory": {"model": "PowerEdge"},
        }
    ]
    items = [
        item("201", "11", "Interface ens1f0 name", "net.if.name[ifName.7]", "ens1f0"),
        item("201", "12", "Interface ens1f0 operational status", "net.if.status[ifOperStatus.7]", "1"),
        item("201", "13", "Interface ens1f0 incoming", "net.if.in[ifHCInOctets.7]", "1234"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert snapshots[0].role == "server"
    assert snapshots[0].ports[0].name == "ens1f0"
    assert snapshots[0].ports[0].oper_status == "up"


def test_hosts_without_ports_are_skipped():
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "401",
            "host": "pdu-01",
            "name": "PDU_UPS_1",
            "groups": [{"name": "Power"}],
            "interfaces": [{"ip": "192.168.3.21"}],
            "inventory": {"model": "NULL"},
        }
    ]

    snapshots = map_zabbix_inventory(hosts, [], settings)

    assert snapshots == []


def test_unknown_hosts_with_ports_are_imported_as_custom_devices():
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "401",
            "host": "pdu-01",
            "name": "PDU_UPS_1",
            "groups": [{"name": "Power"}],
            "interfaces": [{"ip": "192.168.3.21"}],
            "inventory": {"model": "NULL"},
        }
    ]
    items = [
        item("401", "30", "Interface eth0 name", "net.if.name[ifName.1]", "eth0"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert len(snapshots) == 1
    assert snapshots[0].role == "custom"
    assert snapshots[0].model is None
    assert snapshots[0].mgmt_ip == "192.168.3.21"


def test_linux_sysdescr_marks_unknown_host_as_server():
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "402",
            "host": "sys-s4",
            "name": "sys_s4",
            "groups": [{"name": "Other"}],
            "interfaces": [{"ip": "192.168.3.44"}],
            "inventory": {},
        }
    ]
    items = [
        item("402", "31", "System description", "system.sysDescr.0", "Linux server04 6.8.12 x86_64"),
        item("402", "32", "Interface ens1f0 name", "net.if.name[ifName.7]", "ens1f0"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert snapshots[0].role == "server"
    assert snapshots[0].model == "Linux server04 6.8.12 x86_64"


def test_server_multiple_linux_interfaces_are_discovered():
    settings = Settings(environment="test", switch_group_terms="exchange", server_group_terms="server,linux")
    hosts = [
        {
            "hostid": "501",
            "host": "compute-01",
            "name": "compute-01",
            "groups": [{"name": "linux"}],
            "interfaces": [{"ip": "192.168.20.21"}],
            "inventory": {"model": "PowerEdge"},
        }
    ]
    items = [
        item("501", "21", "Interface ens1f0 name", "net.if.name[ifName.7]", "ens1f0"),
        item("501", "22", "Interface ens1f0 operational status", "net.if.status[ifOperStatus.7]", "1"),
        item("501", "23", "Interface ens1f1 name", "net.if.name[ifName.8]", "ens1f1"),
        item("501", "24", "Interface ens1f1 operational status", "net.if.status[ifOperStatus.8]", "2"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert snapshots[0].role == "server"
    assert {port.name for port in snapshots[0].ports} == {"ens1f0", "ens1f1"}


def test_virtual_interfaces_are_not_imported_as_physical_ports():
    settings = Settings(environment="test", switch_group_terms="switch", server_group_terms="server")
    hosts = [
        {
            "hostid": "601",
            "host": "ikuai",
            "name": "iKuai",
            "groups": [{"name": "switch"}],
            "interfaces": [{"ip": "192.168.10.1"}],
            "inventory": {"model": "iKuai"},
        }
    ]
    items = [
        item("601", "1", "Interface vwan1 name", "net.if.name[ifName.1]", "vwan1"),
        item("601", "2", "Interface vlan1.1 name", "net.if.name[ifName.2]", "vlan1.1"),
        item("601", "3", "Interface eth0 name", "net.if.name[ifName.3]", "eth0"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert {port.name for port in snapshots[0].ports} == {"eth0"}


def test_ikuai_vwan_variants_are_virtual_interfaces():
    assert is_virtual_port_name("vWAN2001")
    assert is_virtual_port_name("Interface vWAN2001")
    assert is_virtual_port_name("vwan2001-wan")
    assert not is_virtual_port_name("wan1")
    assert not is_virtual_port_name("lan2")


def test_generic_vendor_interface_names_are_supported():
    values = [
        ("Cisco Ethernet", "ifName.1", "Ethernet1/1", "Ethernet1/1"),
        ("Huawei trunk", "ifName.2", "Eth-Trunk1", "Eth-Trunk1"),
        ("Juniper uplink", "ifName.3", "xe-0/0/0", "xe-0/0/0"),
        ("Port channel", "ifName.4", "Port-channel10", "Po10"),
    ]
    settings = Settings(environment="test", switch_group_terms="switch", server_group_terms="Negev")
    hosts = [
        {
            "hostid": "301",
            "host": "generic-sw",
            "name": "Generic Switch",
            "groups": [{"name": "switch"}],
            "interfaces": [{"ip": "192.168.30.1"}],
            "inventory": {"model": "Cisco Nexus"},
        }
    ]
    items = [item("301", str(index), name, f"net.if.name[{key}]", value) for index, (name, key, value, _) in enumerate(values, start=1)]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert {port.name for port in snapshots[0].ports} == {expected for *_, expected in values}


def test_current_zabbix_agent_net_if_items_can_use_port_name_in_key():
    settings = Settings(environment="test", switch_group_terms="switch", server_group_terms="server")
    hosts = [
        {
            "hostid": "701",
            "host": "linux-01",
            "name": "linux-01",
            "hostgroups": [{"name": "server"}],
            "interfaces": [{"ip": "192.168.20.71"}],
            "inventory": {"model": "Ubuntu 24.04"},
        }
    ]
    items = [
        item("701", "1", "Interface ens1f0: Status", 'net.if.operstatus["ens1f0"]', "1"),
        item("701", "2", "Interface ens1f0: Speed", 'net.if.speed["ens1f0"]', "10000000000"),
        item("701", "3", "Interface ens1f0: Bits received", 'net.if.in["ens1f0"]', "1234"),
        item("701", "4", "Interface ens1f0: Bits sent", 'net.if.out["ens1f0"]', "5678"),
    ]

    snapshots = map_zabbix_inventory(hosts, items, settings)

    assert snapshots[0].role == "server"
    assert snapshots[0].ports[0].name == "ens1f0"
    assert snapshots[0].ports[0].oper_status == "up"
    assert snapshots[0].ports[0].speed_mbps == 10000
    assert snapshots[0].ports[0].last_traffic_in_bps == 1234
    assert snapshots[0].ports[0].last_traffic_out_bps == 5678


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
