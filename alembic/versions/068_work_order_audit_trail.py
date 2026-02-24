"""Add work order audit trail columns and audit log table

Revision ID: 068
Revises: 067
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add audit columns to work_orders table
    op.add_column("work_orders", sa.Column("created_by", sa.String(100), nullable=True))
    op.add_column("work_orders", sa.Column("updated_by", sa.String(100), nullable=True))
    op.add_column("work_orders", sa.Column("source", sa.String(50), nullable=True, server_default="crm"))

    # 2. Fix timestamps to have proper server defaults
    op.alter_column(
        "work_orders", "created_at",
        type_=sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        existing_nullable=True,
    )
    op.alter_column(
        "work_orders", "updated_at",
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
    )

    # 3. Backfill created_at for rows that have NULL
    op.execute("UPDATE work_orders SET created_at = scheduled_date::timestamp WHERE created_at IS NULL AND scheduled_date IS NOT NULL")
    op.execute("UPDATE work_orders SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("UPDATE work_orders SET source = 'crm' WHERE source IS NULL")

    # 4. Create work_order_audit_log table
    op.create_table(
        "work_order_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("work_order_id", UUID(as_uuid=True), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("user_email", sa.String(100), nullable=True),
        sa.Column("user_name", sa.String(200), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("changes", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_wo_audit_work_order_id", "work_order_audit_log", ["work_order_id"])
    op.create_index("ix_wo_audit_action", "work_order_audit_log", ["action"])
    op.create_index("ix_wo_audit_created_at", "work_order_audit_log", ["created_at"])


def downgrade() -> None:
    op.drop_table("work_order_audit_log")
    op.drop_column("work_orders", "source")
    op.drop_column("work_orders", "updated_by")
    op.drop_column("work_orders", "created_by")
