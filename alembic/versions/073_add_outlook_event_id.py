"""Add outlook_event_id to work_orders, microsoft fields to technicians

Revision ID: 073
Revises: 072
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'work_orders' AND column_name = 'outlook_event_id'
            ) THEN
                ALTER TABLE work_orders ADD COLUMN outlook_event_id VARCHAR(255);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'technicians' AND column_name = 'microsoft_user_id'
            ) THEN
                ALTER TABLE technicians ADD COLUMN microsoft_user_id VARCHAR(255);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'technicians' AND column_name = 'microsoft_email'
            ) THEN
                ALTER TABLE technicians ADD COLUMN microsoft_email VARCHAR(255);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("technicians", "microsoft_email")
    op.drop_column("technicians", "microsoft_user_id")
    op.drop_column("work_orders", "outlook_event_id")
