"""Add 2025-2026 Survey Engine Enhancements

Adds AI analysis, detractor queue, and action tracking features:
- New fields on Survey model (delivery_channel, A/B testing, conditional logic)
- New fields on SurveyResponse model (feedback_text, urgency_level, action tracking)
- New SurveyAnalysis table for AI analysis results
- New SurveyAction table for follow-up actions

Revision ID: 020_survey_engine_enhancements
Revises: 019_fix_dropped_columns
Create Date: 2026-01-08 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '020_survey_engine_enhancements'
down_revision = '019_fix_dropped_columns'
branch_labels = None
depends_on = None


def create_enum_if_not_exists(name, values):
    """Create enum type if it doesn't exist."""
    values_str = ", ".join([f"'{v}'" for v in values])
    op.execute(f"""
        DO $$ BEGIN
            CREATE TYPE {name} AS ENUM ({values_str});
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)


def upgrade() -> None:
    # ============ CREATE NEW ENUM TYPES ============
    create_enum_if_not_exists('cs_urgency_level_enum', ['critical', 'high', 'medium', 'low'])
    create_enum_if_not_exists('cs_analysis_status_enum', ['pending', 'processing', 'completed', 'failed'])
    create_enum_if_not_exists('cs_survey_action_type_enum', ['callback', 'task', 'ticket', 'offer', 'escalation', 'email', 'meeting'])
    create_enum_if_not_exists('cs_action_priority_enum', ['low', 'medium', 'high', 'critical'])
    create_enum_if_not_exists('cs_action_status_enum', ['pending', 'in_progress', 'completed', 'cancelled'])

    # ============ ADD NEW COLUMNS TO cs_surveys ============
    op.add_column('cs_surveys', sa.Column('delivery_channel', sa.String(50), nullable=True))
    op.add_column('cs_surveys', sa.Column('reminder_count', sa.Integer(), server_default='1', nullable=True))
    op.add_column('cs_surveys', sa.Column('last_reminder_sent', sa.DateTime(timezone=True), nullable=True))
    op.add_column('cs_surveys', sa.Column('response_rate', sa.Float(), nullable=True))
    op.add_column('cs_surveys', sa.Column('a_b_test_variant', sa.String(50), nullable=True))
    op.add_column('cs_surveys', sa.Column('conditional_logic', sa.JSON(), nullable=True))

    # ============ ADD NEW COLUMNS TO cs_survey_responses ============
    op.add_column('cs_survey_responses', sa.Column('feedback_text', sa.Text(), nullable=True))
    op.add_column('cs_survey_responses', sa.Column('topics_detected', sa.JSON(), nullable=True))
    op.add_column('cs_survey_responses', sa.Column(
        'urgency_level',
        postgresql.ENUM('critical', 'high', 'medium', 'low', name='cs_urgency_level_enum', create_type=False),
        nullable=True
    ))
    op.add_column('cs_survey_responses', sa.Column('action_taken', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('cs_survey_responses', sa.Column('action_type', sa.String(50), nullable=True))
    op.add_column('cs_survey_responses', sa.Column('action_taken_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('cs_survey_responses', sa.Column('action_taken_by', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True))
    op.add_column('cs_survey_responses', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # ============ CREATE cs_survey_analyses TABLE ============
    op.create_table(
        'cs_survey_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), sa.ForeignKey('cs_surveys.id'), nullable=False),
        sa.Column('response_id', sa.Integer(), sa.ForeignKey('cs_survey_responses.id'), nullable=True),  # null = survey-level

        # AI Analysis Results
        sa.Column('sentiment_breakdown', sa.JSON(), nullable=True),
        sa.Column('key_themes', sa.JSON(), nullable=True),
        sa.Column('urgent_issues', sa.JSON(), nullable=True),
        sa.Column('churn_risk_indicators', sa.JSON(), nullable=True),
        sa.Column('competitor_mentions', sa.JSON(), nullable=True),
        sa.Column('action_recommendations', sa.JSON(), nullable=True),

        # Scores
        sa.Column('overall_sentiment_score', sa.Float(), nullable=True),
        sa.Column('churn_risk_score', sa.Float(), nullable=True),
        sa.Column('urgency_score', sa.Float(), nullable=True),

        # Summary
        sa.Column('executive_summary', sa.Text(), nullable=True),

        # Metadata
        sa.Column('analyzed_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('analysis_version', sa.String(20), nullable=True),
        sa.Column('analysis_model', sa.String(100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),

        # Status
        sa.Column('status', postgresql.ENUM('pending', 'processing', 'completed', 'failed', name='cs_analysis_status_enum', create_type=False), server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_survey_analyses_id', 'cs_survey_analyses', ['id'])
    op.create_index('ix_cs_survey_analyses_survey_id', 'cs_survey_analyses', ['survey_id'])
    op.create_index('ix_cs_survey_analyses_response_id', 'cs_survey_analyses', ['response_id'])

    # ============ CREATE cs_survey_actions TABLE ============
    op.create_table(
        'cs_survey_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), sa.ForeignKey('cs_surveys.id'), nullable=False),
        sa.Column('response_id', sa.Integer(), sa.ForeignKey('cs_survey_responses.id'), nullable=True),
        sa.Column('analysis_id', sa.Integer(), sa.ForeignKey('cs_survey_analyses.id'), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),

        # Action details
        sa.Column('action_type', postgresql.ENUM('callback', 'task', 'ticket', 'offer', 'escalation', 'email', 'meeting', name='cs_survey_action_type_enum', create_type=False), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('priority', postgresql.ENUM('low', 'medium', 'high', 'critical', name='cs_action_priority_enum', create_type=False), server_default='medium'),

        # Source
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),

        # Assignment
        sa.Column('assigned_to_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),

        # Status
        sa.Column('status', postgresql.ENUM('pending', 'in_progress', 'completed', 'cancelled', name='cs_action_status_enum', create_type=False), server_default='pending'),

        # Dates
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=True),

        # Linked entity
        sa.Column('linked_entity_type', sa.String(50), nullable=True),
        sa.Column('linked_entity_id', sa.Integer(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),

        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_survey_actions_id', 'cs_survey_actions', ['id'])
    op.create_index('ix_cs_survey_actions_survey_id', 'cs_survey_actions', ['survey_id'])
    op.create_index('ix_cs_survey_actions_response_id', 'cs_survey_actions', ['response_id'])
    op.create_index('ix_cs_survey_actions_customer_id', 'cs_survey_actions', ['customer_id'])
    op.create_index('ix_cs_survey_actions_status', 'cs_survey_actions', ['status'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('cs_survey_actions')
    op.drop_table('cs_survey_analyses')

    # Remove columns from cs_survey_responses
    op.drop_column('cs_survey_responses', 'updated_at')
    op.drop_column('cs_survey_responses', 'action_taken_by')
    op.drop_column('cs_survey_responses', 'action_taken_at')
    op.drop_column('cs_survey_responses', 'action_type')
    op.drop_column('cs_survey_responses', 'action_taken')
    op.drop_column('cs_survey_responses', 'urgency_level')
    op.drop_column('cs_survey_responses', 'topics_detected')
    op.drop_column('cs_survey_responses', 'feedback_text')

    # Remove columns from cs_surveys
    op.drop_column('cs_surveys', 'conditional_logic')
    op.drop_column('cs_surveys', 'a_b_test_variant')
    op.drop_column('cs_surveys', 'response_rate')
    op.drop_column('cs_surveys', 'last_reminder_sent')
    op.drop_column('cs_surveys', 'reminder_count')
    op.drop_column('cs_surveys', 'delivery_channel')

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS cs_action_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_action_priority_enum")
    op.execute("DROP TYPE IF EXISTS cs_survey_action_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_analysis_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_urgency_level_enum")
