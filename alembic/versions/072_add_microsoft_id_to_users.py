"""Add microsoft_id and microsoft_email to api_users

Revision ID: 072
Revises: 071
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'api_users' AND column_name = 'microsoft_id'
            ) THEN
                ALTER TABLE api_users ADD COLUMN microsoft_id VARCHAR(255) UNIQUE;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'api_users' AND column_name = 'microsoft_email'
            ) THEN
                ALTER TABLE api_users ADD COLUMN microsoft_email VARCHAR(255);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column("api_users", "microsoft_email")
    op.drop_column("api_users", "microsoft_id")
