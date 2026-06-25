# Device Support

Switch Topology reads monitoring data from Zabbix. It does not talk to switches directly and does not require SNMP write access.

## Supported by Generic SNMP Mapping

The mapper recognizes common interface names from IF-MIB style Zabbix items:

- Ruijie: `GE0/1`, `XGE0/1`, `QXGE0/49`
- Cisco: `GigabitEthernet1/0/1`, `TenGigabitEthernet1/1/1`, `Ethernet1/1`, `Port-channel1`
- Huawei/H3C: `GigabitEthernet1/0/1`, `XGigabitEthernet1/0/1`, `Eth-Trunk1`
- Juniper: `ge-0/0/0`, `xe-0/0/0`, `et-0/0/0`
- Arista/Dell/SONiC: `Ethernet1`, `Ethernet1/1`
- Linux/servers: `ens1f0`, `eno1`, `eth0`, and other Zabbix-discovered interface names

## Physical Panel Profiles

Profiles add a complete physical port grid even before every port has active Zabbix items.

Current built-in profiles:

- `S6220-48XS6QXS-H`: 48 x 10G + 6 x high-speed uplink ports.
- `S5750-48GT4XS-HP-H`: 48 x copper PoE + 4 x SFP+ uplink ports.
- Alias: `S5750-48T4XS-HP-H` maps to the S5750 profile.

## Recommended Zabbix Template Data

For best results, make sure Zabbix exposes these item families:

- Interface name or description: `ifName`, `ifDescr`
- Status: `ifOperStatus`, `ifAdminStatus`
- Speed: `ifHighSpeed` or `ifSpeed`
- Traffic: `ifHCInOctets`, `ifHCOutOctets`
- Errors: `ifInErrors`, `ifOutErrors`
- Optional: VLAN, PoE, LLDP neighbor, port alias

