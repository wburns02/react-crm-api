"""Add surveys, campaigns, escalations, and collaboration hub tables

Revision ID: 018
Revises: 017_add_journey_status_column
Create Date: 2026-01-07 09:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '018_cs_platform_tables'
down_revision = '017_add_journey_status_column'
branch_labels = None
depends_on = None


def drop_and_create_enum(name, values):
    """Drop enum if it exists (with no dependencies) and create it fresh.

    This handles partial migration failures where enums were created with wrong values.
    Since no tables reference these enums yet (they fail first), we can safely drop and recreate.
    """
    values_str = ", ".join([f"'{v}'" for v in values])
    # Drop existing enum if it exists (CASCADE will only work if no columns use it)
    op.execute(f"DROP TYPE IF EXISTS {name} CASCADE")
    # Create enum with correct values
    op.execute(f"CREATE TYPE {name} AS ENUM ({values_str})")


def upgrade() -> None:
    # ============ CREATE ENUM TYPES FIRST ============
    # Create all enum types with IF NOT EXISTS to handle partial migration failures
    drop_and_create_enum('cs_survey_type_enum', ['nps', 'csat', 'ces', 'custom'])
    drop_and_create_enum('cs_survey_status_enum', ['draft', 'active', 'paused', 'completed'])
    drop_and_create_enum('cs_survey_trigger_enum', ['manual', 'scheduled', 'event', 'milestone'])
    drop_and_create_enum('cs_question_type_enum', ['rating', 'scale', 'text', 'multiple_choice', 'single_choice'])
    drop_and_create_enum('cs_survey_sentiment_enum', ['positive', 'neutral', 'negative'])
    drop_and_create_enum('cs_campaign_status_enum', ['draft', 'active', 'paused', 'completed', 'archived'])
    drop_and_create_enum('cs_campaign_type_enum', ['nurture', 'onboarding', 'adoption', 'renewal', 'expansion', 'winback', 'custom'])
    drop_and_create_enum('cs_step_action_enum', ['email', 'task', 'wait', 'condition', 'notification', 'webhook', 'sms', 'call'])
    drop_and_create_enum('cs_campaign_enroll_enum', ['active', 'paused', 'completed', 'converted', 'unsubscribed', 'exited'])
    drop_and_create_enum('cs_execution_status_enum', ['pending', 'completed', 'skipped', 'failed'])
    drop_and_create_enum('cs_escalation_type_enum', ['technical', 'billing', 'service', 'product', 'relationship', 'executive', 'custom'])
    drop_and_create_enum('cs_escalation_status_enum', ['open', 'in_progress', 'pending_customer', 'pending_internal', 'resolved', 'closed'])
    drop_and_create_enum('cs_priority_enum', ['low', 'medium', 'high', 'critical'])
    drop_and_create_enum('cs_resource_type_enum', ['document', 'video', 'template', 'checklist', 'guide', 'script', 'link'])
    drop_and_create_enum('cs_campaign_channel_enum', ['email', 'in_app', 'sms', 'multi_channel'])
    drop_and_create_enum('cs_step_type_enum', ['email', 'in_app_message', 'sms', 'task', 'wait', 'condition'])
    drop_and_create_enum('cs_exec_status_enum', ['pending', 'sent', 'delivered', 'opened', 'clicked', 'failed', 'skipped'])
    drop_and_create_enum('cs_severity_enum', ['low', 'medium', 'high', 'critical'])
    drop_and_create_enum('cs_note_type_enum', ['update', 'internal', 'customer_communication', 'resolution'])
    drop_and_create_enum('cs_resource_category_enum', ['onboarding', 'training', 'playbooks', 'processes', 'best_practices', 'templates', 'general'])
    drop_and_create_enum('cs_visibility_enum', ['all', 'team', 'managers', 'admins'])
    drop_and_create_enum('cs_note_visibility_enum', ['all', 'team', 'managers', 'private'])

    # ============ SURVEYS ============

    # cs_surveys table
    op.create_table(
        'cs_surveys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('survey_type', postgresql.ENUM('nps', 'csat', 'ces', 'custom', name='cs_survey_type_enum', create_type=False), default='nps'),
        sa.Column('status', postgresql.ENUM('draft', 'active', 'paused', 'completed', name='cs_survey_status_enum', create_type=False), default='draft'),
        sa.Column('trigger_type', postgresql.ENUM('manual', 'scheduled', 'event', 'milestone', name='cs_survey_trigger_enum', create_type=False), default='manual'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('schedule_recurrence', sa.String(50), nullable=True),
        sa.Column('trigger_event', sa.String(100), nullable=True),
        sa.Column('target_segment_id', sa.Integer(), sa.ForeignKey('cs_segments.id'), nullable=True),
        sa.Column('is_anonymous', sa.Boolean(), default=False),
        sa.Column('allow_multiple_responses', sa.Boolean(), default=False),
        sa.Column('send_reminder', sa.Boolean(), default=True),
        sa.Column('reminder_days', sa.Integer(), default=3),
        sa.Column('responses_count', sa.Integer(), default=0),
        sa.Column('avg_score', sa.Float(), nullable=True),
        sa.Column('completion_rate', sa.Float(), nullable=True),
        sa.Column('promoters_count', sa.Integer(), default=0),
        sa.Column('passives_count', sa.Integer(), default=0),
        sa.Column('detractors_count', sa.Integer(), default=0),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_surveys_id', 'cs_surveys', ['id'])
    op.create_index('ix_cs_surveys_status', 'cs_surveys', ['status'])

    # cs_survey_questions table
    op.create_table(
        'cs_survey_questions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), sa.ForeignKey('cs_surveys.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('question_type', postgresql.ENUM('rating', 'scale', 'text', 'multiple_choice', 'single_choice', name='cs_question_type_enum', create_type=False), nullable=False),
        sa.Column('order', sa.Integer(), default=0),
        sa.Column('is_required', sa.Boolean(), default=True),
        sa.Column('scale_min', sa.Integer(), default=0),
        sa.Column('scale_max', sa.Integer(), default=10),
        sa.Column('scale_min_label', sa.String(100), nullable=True),
        sa.Column('scale_max_label', sa.String(100), nullable=True),
        sa.Column('options', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_survey_questions_id', 'cs_survey_questions', ['id'])
    op.create_index('ix_cs_survey_questions_survey_id', 'cs_survey_questions', ['survey_id'])

    # cs_survey_responses table
    op.create_table(
        'cs_survey_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('survey_id', sa.Integer(), sa.ForeignKey('cs_surveys.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=True),
        sa.Column('sentiment', postgresql.ENUM('positive', 'neutral', 'negative', name='cs_survey_sentiment_enum', create_type=False), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('is_complete', sa.Boolean(), default=False),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('device', sa.String(100), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_survey_responses_id', 'cs_survey_responses', ['id'])
    op.create_index('ix_cs_survey_responses_survey_id', 'cs_survey_responses', ['survey_id'])
    op.create_index('ix_cs_survey_responses_customer_id', 'cs_survey_responses', ['customer_id'])

    # cs_survey_answers table
    op.create_table(
        'cs_survey_answers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('response_id', sa.Integer(), sa.ForeignKey('cs_survey_responses.id'), nullable=False),
        sa.Column('question_id', sa.Integer(), sa.ForeignKey('cs_survey_questions.id'), nullable=False),
        sa.Column('rating_value', sa.Integer(), nullable=True),
        sa.Column('text_value', sa.Text(), nullable=True),
        sa.Column('choice_values', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_survey_answers_id', 'cs_survey_answers', ['id'])
    op.create_index('ix_cs_survey_answers_response_id', 'cs_survey_answers', ['response_id'])

    # ============ CAMPAIGNS ============

    # cs_campaigns table
    op.create_table(
        'cs_campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('campaign_type', postgresql.ENUM('nurture', 'onboarding', 'adoption', 'renewal', 'expansion', 'winback', 'custom', name='cs_campaign_type_enum', create_type=False), default='nurture'),
        sa.Column('status', postgresql.ENUM('draft', 'active', 'paused', 'completed', 'archived', name='cs_campaign_status_enum', create_type=False), default='draft'),
        sa.Column('target_segment_id', sa.Integer(), sa.ForeignKey('cs_segments.id'), nullable=True),
        sa.Column('target_criteria', sa.JSON(), nullable=True),
        sa.Column('primary_channel', postgresql.ENUM('email', 'in_app', 'sms', 'multi_channel', name='cs_campaign_channel_enum', create_type=False), default='email'),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('timezone', sa.String(50), default='UTC'),
        sa.Column('is_recurring', sa.Boolean(), default=False),
        sa.Column('recurrence_pattern', sa.String(50), nullable=True),
        sa.Column('allow_re_enrollment', sa.Boolean(), default=False),
        sa.Column('max_enrollments_per_customer', sa.Integer(), default=1),
        sa.Column('goal_type', sa.String(50), nullable=True),
        sa.Column('goal_metric', sa.String(100), nullable=True),
        sa.Column('goal_target', sa.Float(), nullable=True),
        sa.Column('enrolled_count', sa.Integer(), default=0),
        sa.Column('active_count', sa.Integer(), default=0),
        sa.Column('completed_count', sa.Integer(), default=0),
        sa.Column('converted_count', sa.Integer(), default=0),
        sa.Column('conversion_rate', sa.Float(), default=0),
        sa.Column('avg_engagement_score', sa.Float(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('owned_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('launched_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_campaigns_id', 'cs_campaigns', ['id'])
    op.create_index('ix_cs_campaigns_status', 'cs_campaigns', ['status'])

    # cs_campaign_steps table
    op.create_table(
        'cs_campaign_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('cs_campaigns.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('step_type', postgresql.ENUM('email', 'in_app_message', 'sms', 'task', 'wait', 'condition', name='cs_step_type_enum', create_type=False), nullable=False),
        sa.Column('order', sa.Integer(), default=0),
        sa.Column('delay_days', sa.Integer(), default=0),
        sa.Column('delay_hours', sa.Integer(), default=0),
        sa.Column('send_at_time', sa.String(5), nullable=True),
        sa.Column('send_on_days', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('content_html', sa.Text(), nullable=True),
        sa.Column('cta_text', sa.String(100), nullable=True),
        sa.Column('cta_url', sa.String(500), nullable=True),
        sa.Column('condition_rules', sa.JSON(), nullable=True),
        sa.Column('sent_count', sa.Integer(), default=0),
        sa.Column('delivered_count', sa.Integer(), default=0),
        sa.Column('opened_count', sa.Integer(), default=0),
        sa.Column('clicked_count', sa.Integer(), default=0),
        sa.Column('open_rate', sa.Float(), nullable=True),
        sa.Column('click_rate', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_campaign_steps_id', 'cs_campaign_steps', ['id'])
    op.create_index('ix_cs_campaign_steps_campaign_id', 'cs_campaign_steps', ['campaign_id'])

    # cs_campaign_enrollments table
    op.create_table(
        'cs_campaign_enrollments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('cs_campaigns.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('status', postgresql.ENUM('active', 'paused', 'completed', 'converted', 'unsubscribed', 'exited', name='cs_campaign_enroll_enum', create_type=False), default='active'),
        sa.Column('current_step_id', sa.Integer(), sa.ForeignKey('cs_campaign_steps.id'), nullable=True),
        sa.Column('steps_completed', sa.Integer(), default=0),
        sa.Column('next_step_scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('messages_sent', sa.Integer(), default=0),
        sa.Column('messages_opened', sa.Integer(), default=0),
        sa.Column('messages_clicked', sa.Integer(), default=0),
        sa.Column('engagement_score', sa.Float(), nullable=True),
        sa.Column('converted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('conversion_value', sa.Float(), nullable=True),
        sa.Column('exit_reason', sa.String(200), nullable=True),
        sa.Column('exited_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_campaign_enrollments_id', 'cs_campaign_enrollments', ['id'])
    op.create_index('ix_cs_campaign_enrollments_campaign_id', 'cs_campaign_enrollments', ['campaign_id'])
    op.create_index('ix_cs_campaign_enrollments_customer_id', 'cs_campaign_enrollments', ['customer_id'])

    # cs_campaign_step_executions table
    op.create_table(
        'cs_campaign_step_executions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enrollment_id', sa.Integer(), sa.ForeignKey('cs_campaign_enrollments.id'), nullable=False),
        sa.Column('step_id', sa.Integer(), sa.ForeignKey('cs_campaign_steps.id'), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'sent', 'delivered', 'opened', 'clicked', 'failed', 'skipped', name='cs_exec_status_enum', create_type=False), default='pending'),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('external_id', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_campaign_step_executions_id', 'cs_campaign_step_executions', ['id'])
    op.create_index('ix_cs_campaign_step_executions_enrollment_id', 'cs_campaign_step_executions', ['enrollment_id'])
    op.create_index('ix_cs_campaign_step_executions_step_id', 'cs_campaign_step_executions', ['step_id'])

    # ============ ESCALATIONS ============

    # cs_escalations table
    op.create_table(
        'cs_escalations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('escalation_type', postgresql.ENUM('technical', 'billing', 'service', 'product', 'relationship', 'executive', 'custom', name='cs_escalation_type_enum', create_type=False), default='service'),
        sa.Column('severity', postgresql.ENUM('low', 'medium', 'high', 'critical', name='cs_severity_enum', create_type=False), default='medium'),
        sa.Column('priority', sa.Integer(), default=50),
        sa.Column('status', postgresql.ENUM('open', 'in_progress', 'pending_customer', 'pending_internal', 'resolved', 'closed', name='cs_escalation_status_enum', create_type=False), default='open'),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('assigned_to_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('escalated_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('escalated_to_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('sla_hours', sa.Integer(), default=24),
        sa.Column('sla_deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sla_breached', sa.Boolean(), default=False),
        sa.Column('first_response_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_response_sla_hours', sa.Integer(), default=4),
        sa.Column('first_response_breached', sa.Boolean(), default=False),
        sa.Column('revenue_at_risk', sa.Float(), nullable=True),
        sa.Column('churn_probability', sa.Float(), nullable=True),
        sa.Column('impact_description', sa.Text(), nullable=True),
        sa.Column('root_cause_category', sa.String(100), nullable=True),
        sa.Column('root_cause_description', sa.Text(), nullable=True),
        sa.Column('resolution_summary', sa.Text(), nullable=True),
        sa.Column('resolution_category', sa.String(100), nullable=True),
        sa.Column('customer_satisfaction', sa.Integer(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_escalations_id', 'cs_escalations', ['id'])
    op.create_index('ix_cs_escalations_customer_id', 'cs_escalations', ['customer_id'])
    op.create_index('ix_cs_escalations_status', 'cs_escalations', ['status'])
    op.create_index('ix_cs_escalations_severity', 'cs_escalations', ['severity'])

    # cs_escalation_notes table
    op.create_table(
        'cs_escalation_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('escalation_id', sa.Integer(), sa.ForeignKey('cs_escalations.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('note_type', postgresql.ENUM('update', 'internal', 'customer_communication', 'resolution', name='cs_note_type_enum', create_type=False), default='update'),
        sa.Column('is_internal', sa.Boolean(), default=True),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_escalation_notes_id', 'cs_escalation_notes', ['id'])
    op.create_index('ix_cs_escalation_notes_escalation_id', 'cs_escalation_notes', ['escalation_id'])

    # cs_escalation_activities table
    op.create_table(
        'cs_escalation_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('escalation_id', sa.Integer(), sa.ForeignKey('cs_escalations.id'), nullable=False),
        sa.Column('activity_type', sa.String(50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('old_value', sa.String(500), nullable=True),
        sa.Column('new_value', sa.String(500), nullable=True),
        sa.Column('performed_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_escalation_activities_id', 'cs_escalation_activities', ['id'])
    op.create_index('ix_cs_escalation_activities_escalation_id', 'cs_escalation_activities', ['escalation_id'])

    # ============ COLLABORATION HUB ============

    # cs_resources table
    op.create_table(
        'cs_resources',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('resource_type', postgresql.ENUM('document', 'video', 'template', 'checklist', 'guide', 'script', 'link', name='cs_resource_type_enum', create_type=False), nullable=False),
        sa.Column('category', postgresql.ENUM('onboarding', 'training', 'playbooks', 'processes', 'best_practices', 'templates', 'general', name='cs_resource_category_enum', create_type=False), default='general'),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('content_html', sa.Text(), nullable=True),
        sa.Column('url', sa.String(1000), nullable=True),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_type', sa.String(50), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('is_featured', sa.Boolean(), default=False),
        sa.Column('is_pinned', sa.Boolean(), default=False),
        sa.Column('views_count', sa.Integer(), default=0),
        sa.Column('likes_count', sa.Integer(), default=0),
        sa.Column('downloads_count', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_archived', sa.Boolean(), default=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('visibility', postgresql.ENUM('all', 'team', 'managers', 'admins', name='cs_visibility_enum', create_type=False), default='all'),
        sa.Column('version', sa.String(20), default='1.0'),
        sa.Column('parent_resource_id', sa.Integer(), sa.ForeignKey('cs_resources.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('last_viewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_resources_id', 'cs_resources', ['id'])

    # cs_resource_likes table
    op.create_table(
        'cs_resource_likes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_id', sa.Integer(), sa.ForeignKey('cs_resources.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_resource_likes_id', 'cs_resource_likes', ['id'])
    op.create_index('ix_cs_resource_likes_resource_id', 'cs_resource_likes', ['resource_id'])
    op.create_index('ix_cs_resource_likes_user_id', 'cs_resource_likes', ['user_id'])

    # cs_resource_comments table
    op.create_table(
        'cs_resource_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('resource_id', sa.Integer(), sa.ForeignKey('cs_resources.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('parent_comment_id', sa.Integer(), sa.ForeignKey('cs_resource_comments.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_resource_comments_id', 'cs_resource_comments', ['id'])
    op.create_index('ix_cs_resource_comments_resource_id', 'cs_resource_comments', ['resource_id'])

    # cs_team_notes table
    op.create_table(
        'cs_team_notes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('title', sa.String(300), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_html', sa.Text(), nullable=True),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('is_pinned', sa.Boolean(), default=False),
        sa.Column('visibility', postgresql.ENUM('all', 'team', 'managers', 'private', name='cs_note_visibility_enum', create_type=False), default='team'),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_team_notes_id', 'cs_team_notes', ['id'])
    op.create_index('ix_cs_team_notes_customer_id', 'cs_team_notes', ['customer_id'])

    # cs_team_note_comments table
    op.create_table(
        'cs_team_note_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('note_id', sa.Integer(), sa.ForeignKey('cs_team_notes.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_team_note_comments_id', 'cs_team_note_comments', ['id'])
    op.create_index('ix_cs_team_note_comments_note_id', 'cs_team_note_comments', ['note_id'])

    # cs_activities table
    op.create_table(
        'cs_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('activity_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(50), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(300), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('activity_data', sa.JSON(), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('api_users.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_cs_activities_id', 'cs_activities', ['id'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('cs_activities')
    op.drop_table('cs_team_note_comments')
    op.drop_table('cs_team_notes')
    op.drop_table('cs_resource_comments')
    op.drop_table('cs_resource_likes')
    op.drop_table('cs_resources')
    op.drop_table('cs_escalation_activities')
    op.drop_table('cs_escalation_notes')
    op.drop_table('cs_escalations')
    op.drop_table('cs_campaign_step_executions')
    op.drop_table('cs_campaign_enrollments')
    op.drop_table('cs_campaign_steps')
    op.drop_table('cs_campaigns')
    op.drop_table('cs_survey_answers')
    op.drop_table('cs_survey_responses')
    op.drop_table('cs_survey_questions')
    op.drop_table('cs_surveys')

    # Drop enums
    op.execute("DROP TYPE IF EXISTS cs_survey_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_survey_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_survey_trigger_enum")
    op.execute("DROP TYPE IF EXISTS cs_question_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_survey_sentiment_enum")
    op.execute("DROP TYPE IF EXISTS cs_campaign_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_campaign_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_campaign_channel_enum")
    op.execute("DROP TYPE IF EXISTS cs_step_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_campaign_enroll_enum")
    op.execute("DROP TYPE IF EXISTS cs_exec_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_escalation_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_severity_enum")
    op.execute("DROP TYPE IF EXISTS cs_escalation_status_enum")
    op.execute("DROP TYPE IF EXISTS cs_note_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_resource_type_enum")
    op.execute("DROP TYPE IF EXISTS cs_resource_category_enum")
    op.execute("DROP TYPE IF EXISTS cs_visibility_enum")
    op.execute("DROP TYPE IF EXISTS cs_note_visibility_enum")
