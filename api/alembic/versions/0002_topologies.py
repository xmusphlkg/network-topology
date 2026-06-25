"""Add topology graph entities."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_topologies"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "st_topologies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=240), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_st_topologies_created_at", "st_topologies", ["created_at"])
    op.create_index("ix_st_topologies_is_default", "st_topologies", ["is_default"])

    op.create_table(
        "st_topology_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topology_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["topology_id"], ["st_topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["st_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topology_id", "device_id", name="uniq_st_topology_device"),
    )
    op.create_index("idx_st_topology_devices_device", "st_topology_devices", ["device_id"])
    op.create_index("idx_st_topology_devices_topology", "st_topology_devices", ["topology_id"])


def downgrade() -> None:
    op.drop_table("st_topology_devices")
    op.drop_table("st_topologies")
