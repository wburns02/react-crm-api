"""Fix call_logs table schema to match CallLog model

Revision ID: 006_fix_call_logs_schema
Revises: 005_add_all_phase_tables
Create Date: 2025-01-01

Fixes:
- Rename ringcentral_id to rc_call_id
- Add missing columns that the CallLog model expects
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '006_fix_call_logs_schema'
down_revision = '005_add_all_phase_tables'
branch_labels = None
depends_on = None


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade():
    """Add missing columns to call_logs table."""
    conn = op.get_bind()

    # Rename ringcentral_id to rc_call_id if it exists
    if column_exists(conn, 'call_logs', 'ringcentral_id'):
        op.alter_column('call_logs', 'ringcentral_id', new_column_name='rc_call_id')
        print("Renamed ringcentral_id to rc_call_id")

    # Add rc_session_id
    if not column_exists(conn, 'call_logs', 'rc_session_id'):
        op.add_column('call_logs', sa.Column('rc_session_id', sa.String(100), nullable=True))
        print("Added rc_session_id column")

    # Add from_name
    if not column_exists(conn, 'call_logs', 'from_name'):
        op.add_column('call_logs', sa.Column('from_name', sa.String(255), nullable=True))
        print("Added from_name column")

    # Add to_name
    if not column_exists(conn, 'call_logs', 'to_name'):
        op.add_column('call_logs', sa.Column('to_name', sa.String(255), nullable=True))
        print("Added to_name column")

    # Add user_id
    if not column_exists(conn, 'call_logs', 'user_id'):
        op.add_column('call_logs', sa.Column('user_id', sa.String(36), nullable=True))
        op.create_index('ix_call_logs_user_id', 'call_logs', ['user_id'])
        print("Added user_id column")

    # Add contact_name
    if not column_exists(conn, 'call_logs', 'contact_name'):
        op.add_column('call_logs', sa.Column('contact_name', sa.String(255), nullable=True))
        print("Added contact_name column")

    # Add call_type
    if not column_exists(conn, 'call_logs', 'call_type'):
        op.add_column('call_logs', sa.Column('call_type', sa.String(20), nullable=True, server_default='voice'))
        print("Added call_type column")

    # Add ring_duration_seconds
    if not column_exists(conn, 'call_logs', 'ring_duration_seconds'):
        op.add_column('call_logs', sa.Column('ring_duration_seconds', sa.Integer, nullable=True))
        print("Added ring_duration_seconds column")

    # Add recording_duration_seconds
    if not column_exists(conn, 'call_logs', 'recording_duration_seconds'):
        op.add_column('call_logs', sa.Column('recording_duration_seconds', sa.Integer, nullable=True))
        print("Added recording_duration_seconds column")

    # Add has_recording
    if not column_exists(conn, 'call_logs', 'has_recording'):
        op.add_column('call_logs', sa.Column('has_recording', sa.Boolean, nullable=True, server_default='false'))
        print("Added has_recording column")

    # Add transcription_status
    if not column_exists(conn, 'call_logs', 'transcription_status'):
        op.add_column('call_logs', sa.Column('transcription_status', sa.String(20), nullable=True))
        print("Added transcription_status column")

    # Add ai_summary
    if not column_exists(conn, 'call_logs', 'ai_summary'):
        op.add_column('call_logs', sa.Column('ai_summary', sa.Text, nullable=True))
        print("Added ai_summary column")

    # Add sentiment_score
    if not column_exists(conn, 'call_logs', 'sentiment_score'):
        op.add_column('call_logs', sa.Column('sentiment_score', sa.Float, nullable=True))
        print("Added sentiment_score column")

    # Add notes
    if not column_exists(conn, 'call_logs', 'notes'):
        op.add_column('call_logs', sa.Column('notes', sa.Text, nullable=True))
        print("Added notes column")

    # Add disposition
    if not column_exists(conn, 'call_logs', 'disposition'):
        op.add_column('call_logs', sa.Column('disposition', sa.String(50), nullable=True))
        print("Added disposition column")

    # Add activity_id
    if not column_exists(conn, 'call_logs', 'activity_id'):
        op.add_column('call_logs', sa.Column('activity_id', sa.String(36), nullable=True))
        print("Added activity_id column")

    # Add updated_at
    if not column_exists(conn, 'call_logs', 'updated_at'):
        op.add_column('call_logs', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        print("Added updated_at column")

    # Make from_number and to_number NOT NULL (add indexes if missing)
    # These should already exist but let's ensure indexes
    try:
        op.create_index('ix_call_logs_from_number', 'call_logs', ['from_number'])
    except Exception:
        pass  # Index might already exist

    try:
        op.create_index('ix_call_logs_to_number', 'call_logs', ['to_number'])
    except Exception:
        pass  # Index might already exist

    try:
        op.create_index('ix_call_logs_status', 'call_logs', ['status'])
    except Exception:
        pass  # Index might already exist

    print("call_logs table schema updated successfully")


def downgrade():
    """Remove added columns (keeping data intact is preferred)."""
    conn = op.get_bind()

    # Note: We don't rename rc_call_id back to ringcentral_id to avoid breaking things

    columns_to_drop = [
        'rc_session_id', 'from_name', 'to_name', 'user_id', 'contact_name',
        'call_type', 'ring_duration_seconds', 'recording_duration_seconds',
        'has_recording', 'transcription_status', 'ai_summary', 'sentiment_score',
        'notes', 'disposition', 'activity_id', 'updated_at'
    ]

    for col in columns_to_drop:
        if column_exists(conn, 'call_logs', col):
            op.drop_column('call_logs', col)
            print(f"Dropped {col} column")
