"""Add VLAN marker to cable links."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_cable_vlan"
down_revision = "0002_topologies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("st_cable_links", sa.Column("vlan_id", sa.Integer(), nullable=True))
    op.create_index("ix_st_cable_links_vlan_id", "st_cable_links", ["vlan_id"])


def downgrade() -> None:
    op.drop_index("ix_st_cable_links_vlan_id", table_name="st_cable_links")
    op.drop_column("st_cable_links", "vlan_id")
