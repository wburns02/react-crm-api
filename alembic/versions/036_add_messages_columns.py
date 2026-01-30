"""Add missing columns to messages table

Revision ID: 036_messages_columns
Revises: 035_add_notifications_table
Create Date: 2026-01-30

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '036_messages_columns'
down_revision = '035_add_notifications'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add type, direction, status columns to messages table if missing."""
    conn = op.get_bind()

    # Check if columns exist
    result = conn.execute(sa.text("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'messages'
    """))
    existing_columns = {row[0] for row in result}

    # Create enum types if they don't exist
    # MessageType
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE messagetype AS ENUM ('sms', 'email', 'call', 'note');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    # MessageDirection
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE messagedirection AS ENUM ('inbound', 'outbound');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    # MessageStatus
    conn.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE messagestatus AS ENUM ('pending', 'queued', 'sent', 'delivered', 'failed', 'received');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    # Add columns if missing
    if 'type' not in existing_columns:
        op.add_column('messages', sa.Column('type', postgresql.ENUM('sms', 'email', 'call', 'note', name='messagetype', create_type=False), nullable=True))
        # Set default for existing rows
        op.execute("UPDATE messages SET type = 'sms' WHERE type IS NULL")
        op.alter_column('messages', 'type', nullable=False)

    if 'direction' not in existing_columns:
        op.add_column('messages', sa.Column('direction', postgresql.ENUM('inbound', 'outbound', name='messagedirection', create_type=False), nullable=True))
        # Set default for existing rows
        op.execute("UPDATE messages SET direction = 'outbound' WHERE direction IS NULL")
        op.alter_column('messages', 'direction', nullable=False)

    if 'status' not in existing_columns:
        op.add_column('messages', sa.Column('status', postgresql.ENUM('pending', 'queued', 'sent', 'delivered', 'failed', 'received', name='messagestatus', create_type=False), nullable=True))
        # Set default for existing rows
        op.execute("UPDATE messages SET status = 'sent' WHERE status IS NULL")

    if 'subject' not in existing_columns:
        op.add_column('messages', sa.Column('subject', sa.String(255), nullable=True))

    if 'from_address' not in existing_columns:
        op.add_column('messages', sa.Column('from_address', sa.String(255), nullable=True))

    if 'source' not in existing_columns:
        op.add_column('messages', sa.Column('source', sa.String(20), nullable=True, server_default='react'))

    if 'sent_at' not in existing_columns:
        op.add_column('messages', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))

    if 'delivered_at' not in existing_columns:
        op.add_column('messages', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))

    if 'updated_at' not in existing_columns:
        op.add_column('messages', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Remove added columns."""
    # Note: We don't drop columns in downgrade to avoid data loss
    pass
