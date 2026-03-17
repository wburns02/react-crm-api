"""Add billing_customer_id to work_orders

Revision ID: 093
Revises: 092
Create Date: 2026-03-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "work_orders",
        sa.Column("billing_customer_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_work_orders_billing_customer_id",
        "work_orders",
        "customers",
        ["billing_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_work_orders_billing_customer_id",
        "work_orders",
        ["billing_customer_id"],
    )


def downgrade():
    op.drop_index("ix_work_orders_billing_customer_id", table_name="work_orders")
    op.drop_constraint("fk_work_orders_billing_customer_id", "work_orders", type_="foreignkey")
    op.drop_column("work_orders", "billing_customer_id")
