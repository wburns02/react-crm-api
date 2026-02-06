"""Ensure call_logs table has all required columns

Revision ID: 053
Revises: 052
Create Date: 2026-02-06

Adds ALL columns that CallLog model expects.
This is a comprehensive fix for call_logs schema mismatch.
"""

from alembic import op

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add all columns the CallLog model expects (idempotent)
    op.execute("""
        DO $$ BEGIN
            -- Add caller_number if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'caller_number') THEN
                ALTER TABLE call_logs ADD COLUMN caller_number VARCHAR(50);
                CREATE INDEX IF NOT EXISTS ix_call_logs_caller_number ON call_logs(caller_number);
                -- Copy from from_number if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'from_number') THEN
                    UPDATE call_logs SET caller_number = from_number WHERE from_number IS NOT NULL;
                END IF;
            END IF;

            -- Add called_number if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'called_number') THEN
                ALTER TABLE call_logs ADD COLUMN called_number VARCHAR(50);
                CREATE INDEX IF NOT EXISTS ix_call_logs_called_number ON call_logs(called_number);
                -- Copy from to_number if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'to_number') THEN
                    UPDATE call_logs SET called_number = to_number WHERE to_number IS NOT NULL;
                END IF;
            END IF;

            -- Add customer_id if missing (UUID type)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'customer_id') THEN
                ALTER TABLE call_logs ADD COLUMN customer_id UUID;
                CREATE INDEX IF NOT EXISTS ix_call_logs_customer_id ON call_logs(customer_id);
            END IF;

            -- Add answered_by if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'answered_by') THEN
                ALTER TABLE call_logs ADD COLUMN answered_by VARCHAR(255);
                -- Copy from contact_name if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'contact_name') THEN
                    UPDATE call_logs SET answered_by = contact_name WHERE contact_name IS NOT NULL;
                END IF;
            END IF;

            -- Add assigned_to if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'assigned_to') THEN
                ALTER TABLE call_logs ADD COLUMN assigned_to VARCHAR(255);
            END IF;

            -- Add direction if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'direction') THEN
                ALTER TABLE call_logs ADD COLUMN direction VARCHAR(20);
            END IF;

            -- Add call_disposition if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'call_disposition') THEN
                ALTER TABLE call_logs ADD COLUMN call_disposition VARCHAR(100);
                -- Copy from status if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'status') THEN
                    UPDATE call_logs SET call_disposition = status WHERE status IS NOT NULL;
                END IF;
            END IF;

            -- Add call_date if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'call_date') THEN
                ALTER TABLE call_logs ADD COLUMN call_date DATE;
                -- Copy from start_time date part if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'start_time') THEN
                    UPDATE call_logs SET call_date = start_time::date WHERE start_time IS NOT NULL;
                END IF;
            END IF;

            -- Add call_time if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'call_time') THEN
                ALTER TABLE call_logs ADD COLUMN call_time TIME;
                -- Copy from start_time time part if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'start_time') THEN
                    UPDATE call_logs SET call_time = start_time::time WHERE start_time IS NOT NULL;
                END IF;
            END IF;

            -- Add duration_seconds if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'duration_seconds') THEN
                ALTER TABLE call_logs ADD COLUMN duration_seconds INTEGER;
                -- Copy from duration if exists
                IF EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'duration') THEN
                    UPDATE call_logs SET duration_seconds = duration WHERE duration IS NOT NULL;
                END IF;
            END IF;

            -- Add recording_url if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'recording_url') THEN
                ALTER TABLE call_logs ADD COLUMN recording_url VARCHAR(500);
            END IF;

            -- Add notes if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'notes') THEN
                ALTER TABLE call_logs ADD COLUMN notes TEXT;
            END IF;

            -- Add tags if missing (JSON type)
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'tags') THEN
                ALTER TABLE call_logs ADD COLUMN tags JSONB;
            END IF;

            -- Add external_system if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'external_system') THEN
                ALTER TABLE call_logs ADD COLUMN external_system VARCHAR(100) DEFAULT 'ringcentral';
            END IF;

            -- Add AI analysis columns if missing
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'transcription') THEN
                ALTER TABLE call_logs ADD COLUMN transcription TEXT;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'transcription_status') THEN
                ALTER TABLE call_logs ADD COLUMN transcription_status VARCHAR(20);
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'ai_summary') THEN
                ALTER TABLE call_logs ADD COLUMN ai_summary TEXT;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'sentiment') THEN
                ALTER TABLE call_logs ADD COLUMN sentiment VARCHAR(20);
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'sentiment_score') THEN
                ALTER TABLE call_logs ADD COLUMN sentiment_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'quality_score') THEN
                ALTER TABLE call_logs ADD COLUMN quality_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'csat_prediction') THEN
                ALTER TABLE call_logs ADD COLUMN csat_prediction REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'escalation_risk') THEN
                ALTER TABLE call_logs ADD COLUMN escalation_risk VARCHAR(20);
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'professionalism_score') THEN
                ALTER TABLE call_logs ADD COLUMN professionalism_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'empathy_score') THEN
                ALTER TABLE call_logs ADD COLUMN empathy_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'clarity_score') THEN
                ALTER TABLE call_logs ADD COLUMN clarity_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'resolution_score') THEN
                ALTER TABLE call_logs ADD COLUMN resolution_score REAL;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'topics') THEN
                ALTER TABLE call_logs ADD COLUMN topics JSONB;
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'analyzed_at') THEN
                ALTER TABLE call_logs ADD COLUMN analyzed_at TIMESTAMP WITH TIME ZONE;
            END IF;

            -- Ensure timestamps exist
            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'created_at') THEN
                ALTER TABLE call_logs ADD COLUMN created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
            END IF;

            IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'call_logs' AND column_name = 'updated_at') THEN
                ALTER TABLE call_logs ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Keep columns (safer than removing)
    pass
