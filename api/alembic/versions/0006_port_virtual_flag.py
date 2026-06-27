"""Add virtual flag to ports."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_port_virtual_flag"
down_revision = "0005_port_mac_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("st_ports", sa.Column("is_virtual", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_st_ports_is_virtual", "st_ports", ["is_virtual"])
    op.execute(
        """
        UPDATE st_ports
        SET is_virtual = 1
        WHERE
            LOWER(name) LIKE 'vlan%'
            OR LOWER(name) LIKE 'vwan%'
            OR LOWER(name) LIKE 'vxlan%'
            OR LOWER(name) IN ('lo', 'loopback')
            OR LOWER(name) LIKE 'loopback%'
            OR LOWER(name) LIKE 'docker%'
            OR LOWER(name) LIKE 'veth%'
            OR LOWER(name) LIKE 'virbr%'
            OR LOWER(name) LIKE 'tun%'
            OR LOWER(name) LIKE 'tap%'
            OR LOWER(name) LIKE 'wg%'
            OR LOWER(name) LIKE 'br%'
            OR LOWER(name) LIKE 'bridge%'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_st_ports_is_virtual", table_name="st_ports")
    op.drop_column("st_ports", "is_virtual")
