"""Initial switch topology schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "st_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("zabbix_hostid", sa.String(length=64), nullable=True),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("mgmt_ip", sa.String(length=80), nullable=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("health", sa.String(length=24), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("zabbix_hostid"),
    )
    op.create_index("ix_st_devices_display_name", "st_devices", ["display_name"])
    op.create_index("ix_st_devices_enabled", "st_devices", ["enabled"])
    op.create_index("ix_st_devices_health", "st_devices", ["health"])
    op.create_index("ix_st_devices_role", "st_devices", ["role"])
    op.create_index("ix_st_devices_source", "st_devices", ["source"])
    op.create_index("ix_st_devices_stale", "st_devices", ["stale"])
    op.create_index("ix_st_devices_status", "st_devices", ["status"])

    op.create_table(
        "st_ports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("identity", sa.String(length=191), nullable=False),
        sa.Column("if_index", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("alias", sa.String(length=240), nullable=True),
        sa.Column("oper_status", sa.String(length=24), nullable=False),
        sa.Column("admin_status", sa.String(length=24), nullable=False),
        sa.Column("speed_mbps", sa.Float(), nullable=True),
        sa.Column("media", sa.String(length=80), nullable=True),
        sa.Column("port_role", sa.String(length=60), nullable=True),
        sa.Column("vlan_summary", sa.String(length=240), nullable=True),
        sa.Column("poe_status", sa.String(length=80), nullable=True),
        sa.Column("last_traffic_in_bps", sa.Float(), nullable=True),
        sa.Column("last_traffic_out_bps", sa.Float(), nullable=True),
        sa.Column("rx_errors", sa.Float(), nullable=True),
        sa.Column("tx_errors", sa.Float(), nullable=True),
        sa.Column("traffic_in_itemid", sa.String(length=64), nullable=True),
        sa.Column("traffic_out_itemid", sa.String(length=64), nullable=True),
        sa.Column("oper_itemid", sa.String(length=64), nullable=True),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["st_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "identity", name="uniq_st_port_device_identity"),
    )
    op.create_index("idx_st_port_device_name", "st_ports", ["device_id", "name"])
    op.create_index("ix_st_ports_device_id", "st_ports", ["device_id"])
    op.create_index("ix_st_ports_if_index", "st_ports", ["if_index"])
    op.create_index("ix_st_ports_oper_status", "st_ports", ["oper_status"])
    op.create_index("ix_st_ports_source", "st_ports", ["source"])
    op.create_index("ix_st_ports_stale", "st_ports", ["stale"])

    op.create_table(
        "st_cable_links",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("endpoint_a_port_id", sa.Integer(), nullable=False),
        sa.Column("endpoint_b_port_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("cable_no", sa.String(length=120), nullable=True),
        sa.Column("color", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["endpoint_a_port_id"], ["st_ports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["endpoint_b_port_id"], ["st_ports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint_a_port_id", "endpoint_b_port_id", name="uniq_st_cable_pair"),
    )
    op.create_index("idx_st_cable_b", "st_cable_links", ["endpoint_b_port_id"])
    op.create_index("ix_st_cable_links_endpoint_a_port_id", "st_cable_links", ["endpoint_a_port_id"])

    op.create_table(
        "st_topology_layouts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("layout_key", sa.String(length=80), nullable=False),
        sa.Column("node_id", sa.String(length=120), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=True),
        sa.Column("height", sa.Float(), nullable=True),
        sa.Column("group_name", sa.String(length=120), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("viewport_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("layout_key", "node_id", name="uniq_st_layout_node"),
    )
    op.create_index("ix_st_topology_layouts_layout_key", "st_topology_layouts", ["layout_key"])
    op.create_index("ix_st_topology_layouts_node_id", "st_topology_layouts", ["node_id"])

    op.create_table(
        "st_zabbix_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("devices_seen", sa.Integer(), nullable=False),
        sa.Column("devices_upserted", sa.Integer(), nullable=False),
        sa.Column("ports_upserted", sa.Integer(), nullable=False),
        sa.Column("stale_devices", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_st_zabbix_sync_runs_status", "st_zabbix_sync_runs", ["status"])


def downgrade() -> None:
    op.drop_table("st_zabbix_sync_runs")
    op.drop_table("st_topology_layouts")
    op.drop_table("st_cable_links")
    op.drop_table("st_ports")
    op.drop_table("st_devices")

