"""Fix call_logs columns to match CallLog model

Revision ID: 052
Revises: 051
Create Date: 2026-02-06

Fixes discrepancy between model (ringcentral_call_id) and DB (rc_call_id).
Adds missing columns that CallLog model expects.
"""

from alembic import op
import sqlalchemy as sa

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ringcentral_call_id if it doesn't exist (model expects this)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'call_logs' AND column_name = 'ringcentral_call_id'
            ) THEN
                ALTER TABLE call_logs ADD COLUMN ringcentral_call_id VARCHAR(100);
                CREATE INDEX IF NOT EXISTS ix_call_logs_ringcentral_call_id ON call_logs(ringcentral_call_id);

                -- Copy data from rc_call_id if it exists
                IF EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'call_logs' AND column_name = 'rc_call_id'
                ) THEN
                    UPDATE call_logs SET ringcentral_call_id = rc_call_id WHERE rc_call_id IS NOT NULL;
                END IF;
            END IF;
        END $$;
    """)

    # Add ringcentral_session_id if it doesn't exist (model expects this)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'call_logs' AND column_name = 'ringcentral_session_id'
            ) THEN
                ALTER TABLE call_logs ADD COLUMN ringcentral_session_id VARCHAR(100);

                -- Copy data from rc_session_id if it exists
                IF EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'call_logs' AND column_name = 'rc_session_id'
                ) THEN
                    UPDATE call_logs SET ringcentral_session_id = rc_session_id WHERE rc_session_id IS NOT NULL;
                END IF;
            END IF;
        END $$;
    """)

    # Add ring_duration if it doesn't exist (model expects this, not ring_duration_seconds)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = 'call_logs' AND column_name = 'ring_duration'
            ) THEN
                ALTER TABLE call_logs ADD COLUMN ring_duration INTEGER;

                -- Copy data from ring_duration_seconds if it exists
                IF EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'call_logs' AND column_name = 'ring_duration_seconds'
                ) THEN
                    UPDATE call_logs SET ring_duration = ring_duration_seconds WHERE ring_duration_seconds IS NOT NULL;
                END IF;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Keep the columns (safer to keep than remove)
    pass
