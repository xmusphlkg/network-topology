"""Add audit logs and sync details."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_audit_and_sync_details"
down_revision = "0006_port_virtual_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("st_zabbix_sync_runs", sa.Column("details_json", sa.Text(), nullable=True))
    op.create_table(
        "st_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_st_audit_logs_action", "st_audit_logs", ["action"])
    op.create_index("ix_st_audit_logs_created_at", "st_audit_logs", ["created_at"])
    op.create_index("ix_st_audit_logs_resource_id", "st_audit_logs", ["resource_id"])
    op.create_index("ix_st_audit_logs_resource_type", "st_audit_logs", ["resource_type"])


def downgrade() -> None:
    op.drop_index("ix_st_audit_logs_resource_type", table_name="st_audit_logs")
    op.drop_index("ix_st_audit_logs_resource_id", table_name="st_audit_logs")
    op.drop_index("ix_st_audit_logs_created_at", table_name="st_audit_logs")
    op.drop_index("ix_st_audit_logs_action", table_name="st_audit_logs")
    op.drop_table("st_audit_logs")
    op.drop_column("st_zabbix_sync_runs", "details_json")
