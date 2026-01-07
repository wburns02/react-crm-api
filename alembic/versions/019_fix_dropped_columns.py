"""Fix columns dropped by CASCADE in migration 018

Revision ID: 019_fix_dropped_columns
Revises: 018_cs_platform_tables
Create Date: 2026-01-07 13:00:00.000000

Migration 018 used DROP TYPE CASCADE which accidentally dropped columns 
that depended on shared enum types. This migration restores those columns.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '019_fix_dropped_columns'
down_revision = '018_cs_platform_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if cs_journey_enrollments.status column exists, add if missing
    # The original enum cs_enrollment_status_enum should still exist from migration 012
    # but if it was dropped, we need to handle that
    
    # First, ensure the enum exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cs_enrollment_status_enum') THEN
                CREATE TYPE cs_enrollment_status_enum AS ENUM (
                    'active', 'paused', 'completed', 'exited', 'failed'
                );
            END IF;
        END$$;
    """)
    
    # Add the status column back if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'cs_journey_enrollments' 
                AND column_name = 'status'
            ) THEN
                ALTER TABLE cs_journey_enrollments 
                ADD COLUMN status cs_enrollment_status_enum DEFAULT 'active';
            END IF;
        END$$;
    """)
    
    # Ensure cs_sentiment_enum exists for cs_touchpoints
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cs_sentiment_enum') THEN
                CREATE TYPE cs_sentiment_enum AS ENUM (
                    'very_negative', 'negative', 'neutral', 'positive', 'very_positive'
                );
            END IF;
        END$$;
    """)
    
    # Add sentiment_label column back if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'cs_touchpoints' 
                AND column_name = 'sentiment_label'
            ) THEN
                ALTER TABLE cs_touchpoints 
                ADD COLUMN sentiment_label cs_sentiment_enum;
            END IF;
        END$$;
    """)


def downgrade() -> None:
    # We don't want to drop these columns on downgrade
    pass
