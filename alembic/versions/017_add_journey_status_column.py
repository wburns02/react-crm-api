"""Add status column to cs_journeys table

Revision ID: 017_add_journey_status_column
Revises: 016_add_role_views_tables
Create Date: 2026-01-07
"""
from alembic import op
import sqlalchemy as sa

revision = '017_add_journey_status_column'
down_revision = '016_add_role_views_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Create the enum type first (if it doesn't exist)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cs_journey_status_enum') THEN
                CREATE TYPE cs_journey_status_enum AS ENUM ('draft', 'active', 'paused', 'archived');
            END IF;
        END
        $$;
    """)

    # Add status column to cs_journeys table
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'cs_journeys' AND column_name = 'status'
            ) THEN
                ALTER TABLE cs_journeys ADD COLUMN status cs_journey_status_enum DEFAULT 'draft';
            END IF;
        END
        $$;
    """)

    # Update existing journeys: set status based on is_active
    op.execute("""
        UPDATE cs_journeys
        SET status = CASE
            WHEN is_active = true THEN 'draft'::cs_journey_status_enum
            ELSE 'paused'::cs_journey_status_enum
        END
        WHERE status IS NULL;
    """)


def downgrade():
    op.execute("""
        ALTER TABLE cs_journeys DROP COLUMN IF EXISTS status;
    """)
    op.execute("""
        DROP TYPE IF EXISTS cs_journey_status_enum;
    """)
