"""Add system_type to work_orders

Revision ID: 059
Revises: 058
Create Date: 2026-02-17
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Skip if column already exists
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'work_orders' AND column_name = 'system_type')"
    ))
    if result.scalar():
        return
    op.add_column(
        "work_orders",
        sa.Column("system_type", sa.String(50), nullable=True, server_default="conventional"),
    )


def downgrade() -> None:
    op.drop_column("work_orders", "system_type")
