"""Create inbound_emails table

Revision ID: 075
Revises: 074
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS inbound_emails (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id VARCHAR(500) UNIQUE NOT NULL,
            sender_email VARCHAR(255) NOT NULL,
            sender_name VARCHAR(255),
            subject VARCHAR(500),
            body_preview TEXT,
            received_at TIMESTAMP WITH TIME ZONE NOT NULL,
            customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
            action_taken VARCHAR(50) DEFAULT 'none',
            entity_id UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_emails_sender ON inbound_emails(sender_email);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbound_emails_received ON inbound_emails(received_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inbound_emails;")
