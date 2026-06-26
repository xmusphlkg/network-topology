"""Add MAC address to ports."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_port_mac_address"
down_revision = "0004_manual_config_overrides"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("st_ports", sa.Column("mac_address", sa.String(length=17), nullable=True))
    op.create_index("idx_st_ports_mac_address", "st_ports", ["mac_address"])


def downgrade() -> None:
    op.drop_index("idx_st_ports_mac_address", table_name="st_ports")
    op.drop_column("st_ports", "mac_address")
