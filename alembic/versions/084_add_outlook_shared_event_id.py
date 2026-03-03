"""Add outlook_shared_event_id to work_orders for shared mailbox calendar sync.

Revision ID: 084
Revises: 083
Create Date: 2026-03-03
"""
from alembic import op
import sqlalchemy as sa

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: only add if not already present (runtime ensure_ms365_columns may have added it)
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'work_orders' AND column_name = 'outlook_shared_event_id')"
        )
    )
    if not result.scalar():
        op.add_column("work_orders", sa.Column("outlook_shared_event_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("work_orders", "outlook_shared_event_id")
