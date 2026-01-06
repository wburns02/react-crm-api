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
    # Create the status enum type if it doesn't exist
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE cs_journey_status_enum AS ENUM ('draft', 'active', 'paused', 'archived');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Add new columns to cs_journeys table
    op.add_column('cs_journeys', sa.Column('status', sa.Enum(
        'draft', 'active', 'paused', 'archived',
        name='cs_journey_status_enum', create_type=False
    ), server_default='draft'))

    op.add_column('cs_journeys', sa.Column('active_enrolled', sa.Integer, server_default='0'))
    op.add_column('cs_journeys', sa.Column('completed_count', sa.Integer, server_default='0'))
    op.add_column('cs_journeys', sa.Column('goal_achieved_count', sa.Integer, server_default='0'))
    op.add_column('cs_journeys', sa.Column('conversion_rate', sa.Float))
    op.add_column('cs_journeys', sa.Column('priority', sa.Integer, server_default='0'))

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
        SET active_enrolled = COALESCE(currently_active, 0);
    """)

    # Sync total_completed to completed_count
    op.execute("""
        UPDATE cs_journeys
        SET completed_count = COALESCE(total_completed, 0);
    """)

    # Add columns to cs_journey_enrollments table
    op.add_column('cs_journey_enrollments', sa.Column('current_step_order', sa.Integer, server_default='0'))
    op.add_column('cs_journey_enrollments', sa.Column('steps_total', sa.Integer, server_default='0'))
    op.add_column('cs_journey_enrollments', sa.Column('started_at', sa.DateTime(timezone=True)))
    op.add_column('cs_journey_enrollments', sa.Column('paused_at', sa.DateTime(timezone=True)))
    op.add_column('cs_journey_enrollments', sa.Column('enrollment_reason', sa.Text))


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
