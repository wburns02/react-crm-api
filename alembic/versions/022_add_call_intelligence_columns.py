"""Add Call Intelligence AI analysis columns

Revision ID: 022_add_call_intelligence_columns
Revises: 021_add_smart_segments
Create Date: 2026-01-15

Adds columns for AI-powered call analysis:
- sentiment: positive/negative/neutral classification
- quality_score: 0-100 call quality rating
- csat_prediction: 1-5 predicted customer satisfaction
- escalation_risk: low/medium/high/critical risk level
- professionalism_score, empathy_score, clarity_score, resolution_score
- topics: JSON array of discussed topics
- analyzed_at: timestamp of AI analysis

NOTE: transcription, transcription_status, ai_summary, sentiment_score
already exist from migration 006_fix_call_logs_schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '022_add_call_intelligence_columns'
down_revision = '021_add_smart_segments'
branch_labels = None
depends_on = None


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    try:
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.columns
                WHERE table_name = :table_name AND column_name = :column_name
            )
        """), {"table_name": table_name, "column_name": column_name})
        return result.scalar()
    except Exception as e:
        print(f"Warning: Could not check if column {column_name} exists: {e}")
        return True  # Assume exists to avoid duplicate column error


def safe_add_column(table_name, column):
    """Safely add a column, catching errors if it already exists."""
    try:
        op.add_column(table_name, column)
        print(f"Added {column.name} column")
        return True
    except Exception as e:
        print(f"Column {column.name} may already exist or error: {e}")
        return False


def upgrade():
    """Add AI analysis columns to call_logs table."""
    conn = op.get_bind()

    # List of columns to add (excluding ones from migration 006)
    columns_to_add = [
        ('sentiment', sa.String(20)),
        ('quality_score', sa.Float),
        ('csat_prediction', sa.Float),
        ('escalation_risk', sa.String(20)),
        ('professionalism_score', sa.Float),
        ('empathy_score', sa.Float),
        ('clarity_score', sa.Float),
        ('resolution_score', sa.Float),
        ('topics', sa.JSON),
        ('analyzed_at', sa.DateTime(timezone=True)),
    ]

    for col_name, col_type in columns_to_add:
        if not column_exists(conn, 'call_logs', col_name):
            safe_add_column('call_logs', sa.Column(col_name, col_type, nullable=True))

    print("Call Intelligence columns migration completed")


def downgrade():
    """Remove AI analysis columns added by this migration."""
    conn = op.get_bind()

    # Only drop columns added by THIS migration (not ones from 006)
    columns_to_drop = [
        'sentiment', 'quality_score', 'csat_prediction',
        'escalation_risk', 'professionalism_score', 'empathy_score',
        'clarity_score', 'resolution_score', 'topics', 'analyzed_at'
    ]

    for col in columns_to_drop:
        try:
            if column_exists(conn, 'call_logs', col):
                op.drop_column('call_logs', col)
                print(f"Dropped {col} column")
        except Exception as e:
            print(f"Could not drop {col}: {e}")
