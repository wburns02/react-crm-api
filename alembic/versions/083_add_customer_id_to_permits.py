"""Add customer_id FK to septic_permits for permit-customer linking.

Revision ID: 083
Revises: 082
Create Date: 2026-03-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable FK: septic_permits.customer_id → customers.id
    op.add_column(
        "septic_permits",
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_septic_permits_customer_id", "septic_permits", ["customer_id"])


def downgrade() -> None:
    op.drop_index("idx_septic_permits_customer_id", table_name="septic_permits")
    op.drop_column("septic_permits", "customer_id")
