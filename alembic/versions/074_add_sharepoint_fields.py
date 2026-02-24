"""Add sharepoint fields to work_orders and customers

Revision ID: 074
Revises: 073
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'work_orders' AND column_name = 'sharepoint_item_id'
            ) THEN
                ALTER TABLE work_orders ADD COLUMN sharepoint_item_id VARCHAR(255);
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'customers' AND column_name = 'sharepoint_folder_url'
            ) THEN
                ALTER TABLE customers ADD COLUMN sharepoint_folder_url VARCHAR(500);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("customers", "sharepoint_folder_url")
    op.drop_column("work_orders", "sharepoint_item_id")
