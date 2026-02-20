"""Fix payments.invoice_id column type from INTEGER to UUID.

The SQLAlchemy model already declares invoice_id as UUID but the actual
DB column was INTEGER from legacy Flask. This migration drops and re-adds
the column as UUID. invoice_id is always NULL in production (all insert
paths omit it), so no data is lost.

Revision ID: 065
Revises: 064
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("payments", "invoice_id")
    op.add_column(
        "payments",
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "invoice_id")
    op.add_column(
        "payments",
        sa.Column("invoice_id", sa.Integer(), nullable=True),
    )
