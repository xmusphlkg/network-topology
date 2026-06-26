from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class Device(Base, TimestampMixin):
    __tablename__ = "st_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(24), default="manual", index=True)
    zabbix_hostid: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(24), default="custom", index=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    mgmt_ip: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name: Mapped[str] = mapped_column(String(160), index=True)
    status: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    health: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    config_overrides_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    topologies: Mapped[list[TopologyDevice]] = relationship(back_populates="device", cascade="all, delete-orphan")
    ports: Mapped[list[Port]] = relationship(back_populates="device", cascade="all, delete-orphan")


class Topology(Base, TimestampMixin):
    __tablename__ = "st_topologies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(240), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    devices: Mapped[list[TopologyDevice]] = relationship(back_populates="topology", cascade="all, delete-orphan")


class TopologyDevice(Base):
    __tablename__ = "st_topology_devices"
    __table_args__ = (
        UniqueConstraint("topology_id", "device_id", name="uniq_st_topology_device"),
        Index("idx_st_topology_devices_device", "device_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topology_id: Mapped[int] = mapped_column(ForeignKey("st_topologies.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("st_devices.id", ondelete="CASCADE"), index=True)

    topology: Mapped[Topology] = relationship(back_populates="devices")
    device: Mapped[Device] = relationship(back_populates="topologies")


class Port(Base, TimestampMixin):
    __tablename__ = "st_ports"
    __table_args__ = (
        UniqueConstraint("device_id", "identity", name="uniq_st_port_device_identity"),
        Index("idx_st_port_device_name", "device_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("st_devices.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(24), default="manual", index=True)
    identity: Mapped[str] = mapped_column(String(191))
    if_index: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    alias: Mapped[str | None] = mapped_column(String(240), nullable=True)
    oper_status: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    admin_status: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    speed_mbps: Mapped[float | None] = mapped_column(Float, nullable=True)
    media: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True, index=True)
    port_role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    vlan_summary: Mapped[str | None] = mapped_column(String(240), nullable=True)
    poe_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_traffic_in_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_traffic_out_bps: Mapped[float | None] = mapped_column(Float, nullable=True)
    rx_errors: Mapped[float | None] = mapped_column(Float, nullable=True)
    tx_errors: Mapped[float | None] = mapped_column(Float, nullable=True)
    traffic_in_itemid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    traffic_out_itemid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oper_itemid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    config_overrides_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    device: Mapped[Device] = relationship(back_populates="ports")
    cable_a: Mapped[list[CableLink]] = relationship(
        foreign_keys="CableLink.endpoint_a_port_id",
        back_populates="endpoint_a",
    )
    cable_b: Mapped[list[CableLink]] = relationship(
        foreign_keys="CableLink.endpoint_b_port_id",
        back_populates="endpoint_b",
    )


class CableLink(Base, TimestampMixin):
    __tablename__ = "st_cable_links"
    __table_args__ = (
        UniqueConstraint("endpoint_a_port_id", "endpoint_b_port_id", name="uniq_st_cable_pair"),
        Index("idx_st_cable_b", "endpoint_b_port_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_a_port_id: Mapped[int] = mapped_column(ForeignKey("st_ports.id", ondelete="CASCADE"), index=True)
    endpoint_b_port_id: Mapped[int] = mapped_column(ForeignKey("st_ports.id", ondelete="CASCADE"), index=True)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    cable_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)

    endpoint_a: Mapped[Port] = relationship(foreign_keys=[endpoint_a_port_id], back_populates="cable_a")
    endpoint_b: Mapped[Port] = relationship(foreign_keys=[endpoint_b_port_id], back_populates="cable_b")


class TopologyLayout(Base, TimestampMixin):
    __tablename__ = "st_topology_layouts"
    __table_args__ = (UniqueConstraint("layout_key", "node_id", name="uniq_st_layout_node"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    layout_key: Mapped[str] = mapped_column(String(80), default="default", index=True)
    node_id: Mapped[str] = mapped_column(String(120), index=True)
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    viewport_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ZabbixSyncRun(Base, TimestampMixin):
    __tablename__ = "st_zabbix_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    devices_seen: Mapped[int] = mapped_column(Integer, default=0)
    devices_upserted: Mapped[int] = mapped_column(Integer, default=0)
    ports_upserted: Mapped[int] = mapped_column(Integer, default=0)
    stale_devices: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
