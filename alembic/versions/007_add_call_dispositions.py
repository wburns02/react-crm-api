"""Add call_dispositions table

Revision ID: 007_add_call_dispositions
Revises: 006_fix_call_logs_schema
Create Date: 2026-01-03

Adds:
- call_dispositions table for categorizing call outcomes
- Default disposition entries
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '007_add_call_dispositions'
down_revision = '006_fix_call_logs_schema'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = :table_name
        )
    """), {"table_name": table_name})
    return result.scalar()


def upgrade():
    """Create call_dispositions table."""
    conn = op.get_bind()

    if not table_exists(conn, 'call_dispositions'):
        op.create_table(
            'call_dispositions',
            sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('color', sa.String(7), nullable=True, server_default='#6B7280'),
            sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
            sa.Column('is_default', sa.Boolean, nullable=False, server_default='false'),
            sa.Column('display_order', sa.Integer, nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index('ix_call_dispositions_name', 'call_dispositions', ['name'])
        op.create_index('ix_call_dispositions_is_active', 'call_dispositions', ['is_active'])
        print("Created call_dispositions table")

        # Insert default dispositions
        conn.execute(text("""
            INSERT INTO call_dispositions (name, description, color, display_order, is_default) VALUES
            ('answered', 'Call was answered and completed', '#10B981', 1, true),
            ('voicemail', 'Left a voicemail message', '#3B82F6', 2, false),
            ('no_answer', 'No answer after ringing', '#F59E0B', 3, false),
            ('busy', 'Line was busy', '#EF4444', 4, false),
            ('callback_requested', 'Customer requested a callback', '#8B5CF6', 5, false),
            ('appointment_set', 'Appointment was scheduled', '#22C55E', 6, false),
            ('quote_given', 'Quote was provided', '#06B6D4', 7, false),
            ('not_interested', 'Customer not interested', '#6B7280', 8, false),
            ('wrong_number', 'Wrong number or disconnected', '#DC2626', 9, false)
        """))
        print("Inserted default call dispositions")
    else:
        print("call_dispositions table already exists")


def downgrade():
    """Drop call_dispositions table."""
    op.drop_table('call_dispositions')
    print("Dropped call_dispositions table")
