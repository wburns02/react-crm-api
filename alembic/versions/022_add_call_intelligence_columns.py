"""Add Call Intelligence AI analysis columns

Revision ID: 022_add_call_intelligence_columns
Revises: 021_add_smart_segments
Create Date: 2026-01-15

Adds columns for AI-powered call analysis:
- transcription: Full call transcript from Whisper
- sentiment: positive/negative/neutral classification
- quality_score: 0-100 call quality rating
- csat_prediction: 1-5 predicted customer satisfaction
- escalation_risk: low/medium/high/critical risk level
- professionalism_score, empathy_score, clarity_score, resolution_score
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
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )
    """), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade():
    """Add AI analysis columns to call_logs table."""
    conn = op.get_bind()

    # Transcription text
    if not column_exists(conn, 'call_logs', 'transcription'):
        op.add_column('call_logs', sa.Column('transcription', sa.Text, nullable=True))
        print("Added transcription column")

    # Sentiment classification (positive/negative/neutral)
    if not column_exists(conn, 'call_logs', 'sentiment'):
        op.add_column('call_logs', sa.Column('sentiment', sa.String(20), nullable=True))
        print("Added sentiment column")

    # Quality score (0-100)
    if not column_exists(conn, 'call_logs', 'quality_score'):
        op.add_column('call_logs', sa.Column('quality_score', sa.Float, nullable=True))
        print("Added quality_score column")

    # CSAT prediction (1-5)
    if not column_exists(conn, 'call_logs', 'csat_prediction'):
        op.add_column('call_logs', sa.Column('csat_prediction', sa.Float, nullable=True))
        print("Added csat_prediction column")

    # Escalation risk (low/medium/high/critical)
    if not column_exists(conn, 'call_logs', 'escalation_risk'):
        op.add_column('call_logs', sa.Column('escalation_risk', sa.String(20), nullable=True))
        print("Added escalation_risk column")

    # Quality breakdown scores (0-100 each)
    if not column_exists(conn, 'call_logs', 'professionalism_score'):
        op.add_column('call_logs', sa.Column('professionalism_score', sa.Float, nullable=True))
        print("Added professionalism_score column")

    if not column_exists(conn, 'call_logs', 'empathy_score'):
        op.add_column('call_logs', sa.Column('empathy_score', sa.Float, nullable=True))
        print("Added empathy_score column")

    if not column_exists(conn, 'call_logs', 'clarity_score'):
        op.add_column('call_logs', sa.Column('clarity_score', sa.Float, nullable=True))
        print("Added clarity_score column")

    if not column_exists(conn, 'call_logs', 'resolution_score'):
        op.add_column('call_logs', sa.Column('resolution_score', sa.Float, nullable=True))
        print("Added resolution_score column")

    # Topics discussed (JSON array)
    if not column_exists(conn, 'call_logs', 'topics'):
        op.add_column('call_logs', sa.Column('topics', sa.JSON, nullable=True))
        print("Added topics column")

    # Analysis timestamp
    if not column_exists(conn, 'call_logs', 'analyzed_at'):
        op.add_column('call_logs', sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=True))
        print("Added analyzed_at column")

    print("Call Intelligence columns added successfully")


def downgrade():
    """Remove AI analysis columns."""
    conn = op.get_bind()

    columns_to_drop = [
        'transcription', 'sentiment', 'quality_score', 'csat_prediction',
        'escalation_risk', 'professionalism_score', 'empathy_score',
        'clarity_score', 'resolution_score', 'topics', 'analyzed_at'
    ]

    for col in columns_to_drop:
        if column_exists(conn, 'call_logs', col):
            op.drop_column('call_logs', col)
            print(f"Dropped {col} column")
