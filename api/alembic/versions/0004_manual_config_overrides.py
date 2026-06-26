"""Track manual device and port config overrides."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_manual_config_overrides"
down_revision = "0003_cable_vlan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("st_devices", sa.Column("config_overrides_json", sa.Text(), nullable=True))
    op.add_column("st_ports", sa.Column("config_overrides_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("st_ports", "config_overrides_json")
    op.drop_column("st_devices", "config_overrides_json")
