from __future__ import annotations

from app.services.ip_addr import parse_ip_addr_ports


def test_parse_ip_addr_supports_full_and_brief_outputs():
    output = """
2: enp3s0f0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    link/ether 52:54:00:aa:bb:cc brd ff:ff:ff:ff:ff:ff
    inet 10.10.10.11/24 brd 10.10.10.255 scope global enp3s0f0
3: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 state DOWN
    inet 172.17.0.1/16 scope global docker0
4: iDRAC: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    inet 192.168.99.10/24 scope global iDRAC
enx001122334455 UP 52-54-00-dd-ee-ff 192.168.50.10/24 fe80::1/64
BMC0 DOWN -
vethabc DOWN -
eth0@if12 UP 172.20.0.2/16
bond0 UP 10.0.0.10/24
enp3s0f0.100@enp3s0f0 UP 10.100.0.2/24
"""

    ports = parse_ip_addr_ports(output)

    assert {port["name"] for port in ports} == {"enp3s0f0", "enx001122334455", "iDRAC", "BMC0"}
    assert next(port for port in ports if port["name"] == "enp3s0f0")["operStatus"] == "up"
    assert next(port for port in ports if port["name"] == "enp3s0f0")["macAddress"] == "52:54:00:aa:bb:cc"
    assert next(port for port in ports if port["name"] == "enx001122334455")["alias"] == "192.168.50.10/24, fe80::1/64"
    assert next(port for port in ports if port["name"] == "enx001122334455")["macAddress"] == "52:54:00:dd:ee:ff"
    assert next(port for port in ports if port["name"] == "iDRAC")["portRole"] == "management"
    assert next(port for port in ports if port["name"] == "BMC0")["portRole"] == "management"
    assert "eth0" not in {port["name"] for port in ports}
    assert "bond0" not in {port["name"] for port in ports}
    assert "enp3s0f0.100" not in {port["name"] for port in ports}


def test_parse_ip_details_drops_virtual_link_kinds():
    output = """
2: ens18: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    link/ether 52:54:00:11:22:33 brd ff:ff:ff:ff:ff:ff
3: vlan10: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    vlan protocol 802.1Q id 10 <REORDER_HDR>
    link/ether 52:54:00:11:22:44 brd ff:ff:ff:ff:ff:ff
4: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP
    bridge forward_delay 1500 hello_time 200 max_age 2000 ageing_time 30000
    link/ether 52:54:00:11:22:55 brd ff:ff:ff:ff:ff:ff
"""

    ports = parse_ip_addr_ports(output)

    assert {port["name"] for port in ports} == {"ens18"}
    assert ports[0]["macAddress"] == "52:54:00:11:22:33"
