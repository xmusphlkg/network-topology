from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    deviceId: int = Field(validation_alias="device_id")
    source: str
    identity: str
    ifIndex: int | None = Field(default=None, validation_alias="if_index")
    name: str
    alias: str | None = None
    operStatus: str = Field(validation_alias="oper_status")
    adminStatus: str = Field(validation_alias="admin_status")
    speedMbps: float | None = Field(default=None, validation_alias="speed_mbps")
    media: str | None = None
    portRole: str | None = Field(default=None, validation_alias="port_role")
    vlanSummary: str | None = Field(default=None, validation_alias="vlan_summary")
    poeStatus: str | None = Field(default=None, validation_alias="poe_status")
    lastTrafficInBps: float | None = Field(default=None, validation_alias="last_traffic_in_bps")
    lastTrafficOutBps: float | None = Field(default=None, validation_alias="last_traffic_out_bps")
    rxErrors: float | None = Field(default=None, validation_alias="rx_errors")
    txErrors: float | None = Field(default=None, validation_alias="tx_errors")
    stale: bool
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


class PortCreate(BaseModel):
    name: str
    alias: str | None = None
    ifIndex: int | None = None
    speedMbps: float | None = None
    media: str | None = None
    portRole: str | None = None
    vlanSummary: str | None = None
    poeStatus: str | None = None


class PortUpdate(BaseModel):
    name: str | None = None
    alias: str | None = None
    operStatus: str | None = None
    adminStatus: str | None = None
    speedMbps: float | None = None
    media: str | None = None
    portRole: str | None = None
    vlanSummary: str | None = None
    poeStatus: str | None = None
    stale: bool | None = None


class DeviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    source: str
    zabbixHostid: str | None = Field(default=None, validation_alias="zabbix_hostid")
    role: str
    model: str | None = None
    mgmtIp: str | None = Field(default=None, validation_alias="mgmt_ip")
    displayName: str = Field(validation_alias="display_name")
    status: str
    health: str
    lastSeenAt: datetime | None = Field(default=None, validation_alias="last_seen_at")
    stale: bool
    enabled: bool
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


class DeviceCreate(BaseModel):
    displayName: str
    role: Literal["switch", "server", "custom"] = "custom"
    source: Literal["manual", "zabbix"] = "manual"
    zabbixHostid: str | None = None
    model: str | None = None
    mgmtIp: str | None = None
    topologyId: int | None = None
    enabled: bool = True
    ports: list[PortCreate] = Field(default_factory=list)


class DeviceUpdate(BaseModel):
    displayName: str | None = None
    role: Literal["switch", "server", "custom"] | None = None
    zabbixHostid: str | None = None
    model: str | None = None
    mgmtIp: str | None = None
    status: str | None = None
    health: str | None = None
    stale: bool | None = None
    enabled: bool | None = None


class CableLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    endpointAPortId: int = Field(validation_alias="endpoint_a_port_id")
    endpointBPortId: int = Field(validation_alias="endpoint_b_port_id")
    label: str | None = None
    cableNo: str | None = Field(default=None, validation_alias="cable_no")
    color: str | None = None
    notes: str | None = None
    verifiedAt: datetime | None = Field(default=None, validation_alias="verified_at")
    createdBy: str | None = Field(default=None, validation_alias="created_by")
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


class CableLinkCreate(BaseModel):
    endpointAPortId: int
    endpointBPortId: int
    label: str | None = None
    cableNo: str | None = None
    color: str | None = "#4f8cff"
    notes: str | None = None
    verifiedAt: datetime | None = None
    createdBy: str | None = None

    @field_validator("endpointBPortId")
    @classmethod
    def endpoints_differ(cls, value: int, info):
        if info.data.get("endpointAPortId") == value:
            raise ValueError("Cable endpoints must be different ports")
        return value


class CableLinkUpdate(BaseModel):
    label: str | None = None
    cableNo: str | None = None
    color: str | None = None
    notes: str | None = None
    verifiedAt: datetime | None = None
    createdBy: str | None = None


class TopologyNode(BaseModel):
    id: str
    type: str
    position: dict[str, float]
    data: dict


class TopologyEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str
    targetHandle: str
    label: str | None = None
    style: dict | None = None
    data: dict = Field(default_factory=dict)


class TopologyLayoutState(BaseModel):
    topologyId: int | None = Field(default=None, validation_alias="topologyId")
    layoutKey: str = Field(default="default")
    viewport: dict | None = None
    nodes: list[LayoutNodeUpdate] = Field(default_factory=list)


class TopologyGraphRead(BaseModel):
    generatedAt: datetime
    topologyId: int = Field(validation_alias="topology_id")
    topologyName: str = Field(validation_alias="topology_name")
    summary: TopologyRead
    layout: TopologyLayoutState
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    devices: list[DeviceRead]
    ports: list[PortRead]
    cableLinks: list[CableLinkRead]
    switchPanels: list[dict]


class TopologyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    description: str | None = None
    isDefault: bool = Field(validation_alias="is_default")
    deviceCount: int = Field(default=0, validation_alias="device_count")
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


class TopologyCreate(BaseModel):
    name: str
    description: str | None = None
    isDefault: bool = False


class TopologyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    isDefault: bool | None = None


class TopologyDeviceIds(BaseModel):
    deviceIds: list[int] = Field(default_factory=list)


class TopologyImportRequest(BaseModel):
    hostids: list[str] = Field(default_factory=list)


class ZabbixDiscoveredDevice(BaseModel):
    zabbixHostid: str
    displayName: str
    role: str
    model: str | None = None
    mgmtIp: str | None = None
    portCount: int
    synced: bool


class LayoutNodeUpdate(BaseModel):
    nodeId: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None
    groupName: str | None = None
    hidden: bool = False


class LayoutUpdate(BaseModel):
    layoutKey: str = "default"
    viewport: dict | None = None
    nodes: list[LayoutNodeUpdate] = Field(default_factory=list)


class SeriesPoint(BaseModel):
    ts: int
    inBps: float | None = None
    outBps: float | None = None


class PortSeries(BaseModel):
    portId: int
    range: str
    points: list[SeriesPoint]
    error: str | None = None


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    status: str
    startedAt: datetime = Field(validation_alias="started_at")
    finishedAt: datetime | None = Field(default=None, validation_alias="finished_at")
    durationMs: float | None = Field(default=None, validation_alias="duration_ms")
    devicesSeen: int = Field(validation_alias="devices_seen")
    devicesUpserted: int = Field(validation_alias="devices_upserted")
    portsUpserted: int = Field(validation_alias="ports_upserted")
    staleDevices: int = Field(validation_alias="stale_devices")
    errorMessage: str | None = Field(default=None, validation_alias="error_message")


class SyncStatus(BaseModel):
    latest: SyncRunRead | None = None
    zabbixConfigured: bool
