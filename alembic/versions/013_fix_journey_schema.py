"""Fix Journey schema to match Pydantic models

Revision ID: 013_fix_journey_schema
Revises: 012_add_customer_success
Create Date: 2026-01-06

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '013_fix_journey_schema'
down_revision = '012_add_customer_success'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL to add columns if they don't exist (idempotent)
    op.execute("""
        DO $$ BEGIN
            -- Create the status enum type if it doesn't exist
            CREATE TYPE cs_journey_status_enum AS ENUM ('draft', 'active', 'paused', 'archived');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Add columns to cs_journeys if they don't exist
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN status cs_journey_status_enum DEFAULT 'draft';
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN active_enrolled INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN completed_count INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN goal_achieved_count INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN conversion_rate FLOAT;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journeys ADD COLUMN priority INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    # Sync is_active with status
    op.execute("""
        UPDATE cs_journeys
        SET status = CASE
            WHEN is_active = true THEN 'active'::cs_journey_status_enum
            ELSE 'paused'::cs_journey_status_enum
        END
        WHERE status IS NULL;
    """)

    # Sync currently_active to active_enrolled
    op.execute("""
        UPDATE cs_journeys
        SET active_enrolled = COALESCE(currently_active, 0)
        WHERE active_enrolled IS NULL OR active_enrolled = 0;
    """)

    # Sync total_completed to completed_count
    op.execute("""
        UPDATE cs_journeys
        SET completed_count = COALESCE(total_completed, 0)
        WHERE completed_count IS NULL OR completed_count = 0;
    """)

    # Add columns to cs_journey_enrollments table if they don't exist
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journey_enrollments ADD COLUMN current_step_order INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journey_enrollments ADD COLUMN steps_total INTEGER DEFAULT 0;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journey_enrollments ADD COLUMN started_at TIMESTAMP WITH TIME ZONE;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journey_enrollments ADD COLUMN paused_at TIMESTAMP WITH TIME ZONE;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            ALTER TABLE cs_journey_enrollments ADD COLUMN enrollment_reason TEXT;
        EXCEPTION
            WHEN duplicate_column THEN null;
        END $$;
    """)


def downgrade():
    # Drop enrollment columns
    op.drop_column('cs_journey_enrollments', 'enrollment_reason')
    op.drop_column('cs_journey_enrollments', 'paused_at')
    op.drop_column('cs_journey_enrollments', 'started_at')
    op.drop_column('cs_journey_enrollments', 'steps_total')
    op.drop_column('cs_journey_enrollments', 'current_step_order')

    # Drop journey columns
    op.drop_column('cs_journeys', 'priority')
    op.drop_column('cs_journeys', 'conversion_rate')
    op.drop_column('cs_journeys', 'goal_achieved_count')
    op.drop_column('cs_journeys', 'completed_count')
    op.drop_column('cs_journeys', 'active_enrolled')
    op.drop_column('cs_journeys', 'status')

    op.execute("DROP TYPE IF EXISTS cs_journey_status_enum;")
