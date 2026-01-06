"""Add Enterprise Customer Success Platform tables

Revision ID: 012_add_customer_success
Revises: 011_add_oauth_tables
Create Date: 2026-01-06

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision = '012_add_customer_success'
down_revision = '011_add_oauth_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Create ENUM types
    op.execute("""
        CREATE TYPE cs_health_status_enum AS ENUM ('healthy', 'at_risk', 'critical', 'churned');
        CREATE TYPE cs_score_trend_enum AS ENUM ('improving', 'stable', 'declining');
        CREATE TYPE cs_health_event_type_enum AS ENUM (
            'score_calculated', 'manual_override', 'component_change',
            'escalation_opened', 'escalation_closed', 'champion_change',
            'renewal_update', 'support_issue', 'engagement_change'
        );
        CREATE TYPE cs_segment_type_enum AS ENUM ('static', 'dynamic', 'ai_generated');
        CREATE TYPE cs_rule_mode_enum AS ENUM ('all_match', 'any_match');
        CREATE TYPE cs_journey_type_enum AS ENUM (
            'onboarding', 'adoption', 'renewal', 'expansion',
            'risk_mitigation', 'advocacy', 'win_back', 'custom'
        );
        CREATE TYPE cs_journey_trigger_enum AS ENUM (
            'manual', 'segment_entry', 'event', 'scheduled',
            'health_change', 'renewal_window'
        );
        CREATE TYPE cs_journey_step_type_enum AS ENUM (
            'email', 'in_app_message', 'task', 'wait', 'condition',
            'webhook', 'segment_update', 'health_check', 'human_touchpoint',
            'sms', 'slack_notification', 'custom'
        );
        CREATE TYPE cs_enrollment_status_enum AS ENUM (
            'active', 'paused', 'completed', 'exited', 'failed'
        );
        CREATE TYPE cs_exit_reason_enum AS ENUM (
            'completed', 'goal_achieved', 'manual_exit', 'segment_exit',
            'health_threshold', 'event_triggered', 'timeout', 'error'
        );
        CREATE TYPE cs_step_execution_status_enum AS ENUM (
            'pending', 'in_progress', 'completed', 'skipped', 'failed', 'waiting'
        );
        CREATE TYPE cs_playbook_category_enum AS ENUM (
            'onboarding', 'adoption', 'renewal', 'churn_risk',
            'expansion', 'escalation', 'qbr', 'executive_sponsor',
            'champion_change', 'implementation', 'training', 'custom'
        );
        CREATE TYPE cs_playbook_trigger_enum AS ENUM (
            'manual', 'health_threshold', 'segment_entry', 'event',
            'days_to_renewal', 'scheduled'
        );
        CREATE TYPE cs_playbook_priority_enum AS ENUM ('low', 'medium', 'high', 'critical');
        CREATE TYPE cs_playbook_step_type_enum AS ENUM (
            'call', 'email', 'meeting', 'internal_task', 'product_demo',
            'training', 'review', 'escalation', 'documentation',
            'approval', 'notification', 'custom'
        );
        CREATE TYPE cs_completion_type_enum AS ENUM (
            'manual', 'auto_email_sent', 'auto_meeting_scheduled', 'approval_received'
        );
        CREATE TYPE cs_playbook_exec_status_enum AS ENUM (
            'active', 'paused', 'completed', 'cancelled', 'failed'
        );
        CREATE TYPE cs_playbook_outcome_enum AS ENUM (
            'successful', 'unsuccessful', 'partial', 'cancelled'
        );
        CREATE TYPE cs_task_type_enum AS ENUM (
            'call', 'email', 'meeting', 'internal', 'review',
            'escalation', 'follow_up', 'documentation', 'training',
            'product_demo', 'qbr', 'renewal', 'custom'
        );
        CREATE TYPE cs_task_category_enum AS ENUM (
            'onboarding', 'adoption', 'retention', 'expansion',
            'support', 'relationship', 'administrative'
        );
        CREATE TYPE cs_task_priority_enum AS ENUM ('low', 'medium', 'high', 'critical');
        CREATE TYPE cs_task_status_enum AS ENUM (
            'pending', 'in_progress', 'completed', 'cancelled', 'blocked', 'snoozed'
        );
        CREATE TYPE cs_task_outcome_enum AS ENUM (
            'successful', 'unsuccessful', 'rescheduled', 'no_response',
            'voicemail', 'escalated', 'cancelled', 'not_applicable'
        );
        CREATE TYPE cs_touchpoint_type_enum AS ENUM (
            'email_sent', 'email_opened', 'email_clicked', 'email_replied',
            'call_outbound', 'call_inbound', 'call_missed', 'voicemail',
            'meeting_scheduled', 'meeting_held', 'meeting_cancelled', 'meeting_no_show',
            'sms_sent', 'sms_received', 'chat_session', 'video_call',
            'product_login', 'feature_usage', 'feature_adoption',
            'webinar_registered', 'webinar_attended', 'training_completed',
            'support_ticket_opened', 'support_ticket_resolved', 'support_escalation',
            'nps_response', 'csat_response', 'survey_response', 'review_posted',
            'qbr_held', 'renewal_discussion', 'expansion_discussion',
            'contract_signed', 'invoice_paid', 'payment_issue',
            'internal_note', 'health_alert', 'risk_flag',
            'in_app_message_sent', 'in_app_message_clicked',
            'document_shared', 'document_viewed', 'event_attended', 'referral_made', 'custom'
        );
        CREATE TYPE cs_touchpoint_direction_enum AS ENUM ('inbound', 'outbound', 'internal');
        CREATE TYPE cs_touchpoint_channel_enum AS ENUM (
            'email', 'phone', 'video', 'in_app', 'in_person',
            'chat', 'sms', 'social', 'webinar', 'event', 'other'
        );
        CREATE TYPE cs_sentiment_enum AS ENUM (
            'very_negative', 'negative', 'neutral', 'positive', 'very_positive'
        );
    """)

    # Health Scores table
    op.create_table(
        'cs_health_scores',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('overall_score', sa.Integer, nullable=False, server_default='50'),
        sa.Column('health_status', sa.Enum('healthy', 'at_risk', 'critical', 'churned', name='cs_health_status_enum', create_type=False)),
        sa.Column('product_adoption_score', sa.Integer, server_default='50'),
        sa.Column('engagement_score', sa.Integer, server_default='50'),
        sa.Column('relationship_score', sa.Integer, server_default='50'),
        sa.Column('financial_score', sa.Integer, server_default='50'),
        sa.Column('support_score', sa.Integer, server_default='50'),
        sa.Column('churn_probability', sa.Float, server_default='0.0'),
        sa.Column('expansion_probability', sa.Float, server_default='0.0'),
        sa.Column('nps_predicted', sa.Integer),
        sa.Column('days_since_last_login', sa.Integer, server_default='0'),
        sa.Column('days_to_renewal', sa.Integer),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('active_users_count', sa.Integer, server_default='0'),
        sa.Column('licensed_users_count', sa.Integer, server_default='0'),
        sa.Column('feature_adoption_pct', sa.Float, server_default='0.0'),
        sa.Column('score_trend', sa.Enum('improving', 'stable', 'declining', name='cs_score_trend_enum', create_type=False)),
        sa.Column('score_change_7d', sa.Integer, server_default='0'),
        sa.Column('score_change_30d', sa.Integer, server_default='0'),
        sa.Column('has_open_escalation', sa.Boolean, server_default='false'),
        sa.Column('champion_at_risk', sa.Boolean, server_default='false'),
        sa.Column('payment_issues', sa.Boolean, server_default='false'),
        sa.Column('calculated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('calculation_version', sa.String(20), server_default='1.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Health Score Events table
    op.create_table(
        'cs_health_score_events',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('health_score_id', sa.Integer, sa.ForeignKey('cs_health_scores.id'), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('previous_score', sa.Integer),
        sa.Column('new_score', sa.Integer),
        sa.Column('score_delta', sa.Integer),
        sa.Column('previous_status', sa.String(20)),
        sa.Column('new_status', sa.String(20)),
        sa.Column('event_type', sa.Enum(
            'score_calculated', 'manual_override', 'component_change',
            'escalation_opened', 'escalation_closed', 'champion_change',
            'renewal_update', 'support_issue', 'engagement_change',
            name='cs_health_event_type_enum', create_type=False
        ), nullable=False),
        sa.Column('event_source', sa.String(100)),
        sa.Column('affected_components', JSON),
        sa.Column('description', sa.Text),
        sa.Column('event_metadata', JSON),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Segments table
    op.create_table(
        'cs_segments',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('color', sa.String(7), server_default='#3B82F6'),
        sa.Column('segment_type', sa.Enum('static', 'dynamic', 'ai_generated', name='cs_segment_type_enum', create_type=False)),
        sa.Column('rules', JSON),
        sa.Column('rule_evaluation_mode', sa.Enum('all_match', 'any_match', name='cs_rule_mode_enum', create_type=False)),
        sa.Column('ai_confidence', sa.Float),
        sa.Column('ai_reasoning', sa.Text),
        sa.Column('ai_model_version', sa.String(50)),
        sa.Column('customer_count', sa.Integer, server_default='0'),
        sa.Column('total_arr', sa.Numeric(15, 2), server_default='0'),
        sa.Column('avg_health_score', sa.Float, server_default='0'),
        sa.Column('at_risk_count', sa.Integer, server_default='0'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('auto_refresh', sa.Boolean, server_default='true'),
        sa.Column('refresh_interval_hours', sa.Integer, server_default='1'),
        sa.Column('last_refreshed_at', sa.DateTime(timezone=True)),
        sa.Column('priority', sa.Integer, server_default='100'),
        sa.Column('created_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Customer Segments junction table
    op.create_table(
        'cs_customer_segments',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('segment_id', sa.Integer, sa.ForeignKey('cs_segments.id'), nullable=False, index=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('entered_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('exited_at', sa.DateTime(timezone=True)),
        sa.Column('entry_reason', sa.String(200)),
        sa.Column('exit_reason', sa.String(200)),
        sa.Column('ai_match_score', sa.Float),
        sa.Column('ai_match_reasons', JSON),
        sa.Column('added_by', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Journeys table
    op.create_table(
        'cs_journeys',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('journey_type', sa.Enum(
            'onboarding', 'adoption', 'renewal', 'expansion',
            'risk_mitigation', 'advocacy', 'win_back', 'custom',
            name='cs_journey_type_enum', create_type=False
        )),
        sa.Column('trigger_type', sa.Enum(
            'manual', 'segment_entry', 'event', 'scheduled',
            'health_change', 'renewal_window',
            name='cs_journey_trigger_enum', create_type=False
        )),
        sa.Column('trigger_config', JSON),
        sa.Column('trigger_segment_id', sa.Integer, sa.ForeignKey('cs_segments.id')),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('allow_re_enrollment', sa.Boolean, server_default='false'),
        sa.Column('re_enrollment_cooldown_days', sa.Integer, server_default='90'),
        sa.Column('max_concurrent_enrollments', sa.Integer),
        sa.Column('exit_on_segment_leave', sa.Boolean, server_default='true'),
        sa.Column('exit_on_health_threshold', sa.Integer),
        sa.Column('exit_on_event', sa.String(100)),
        sa.Column('goal_metric', sa.String(100)),
        sa.Column('goal_target', sa.Float),
        sa.Column('goal_timeframe_days', sa.Integer),
        sa.Column('total_enrolled', sa.Integer, server_default='0'),
        sa.Column('currently_active', sa.Integer, server_default='0'),
        sa.Column('total_completed', sa.Integer, server_default='0'),
        sa.Column('total_exited_early', sa.Integer, server_default='0'),
        sa.Column('avg_completion_days', sa.Float),
        sa.Column('success_rate', sa.Float),
        sa.Column('created_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('owned_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Journey Steps table
    op.create_table(
        'cs_journey_steps',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('journey_id', sa.Integer, sa.ForeignKey('cs_journeys.id'), nullable=False, index=True),
        sa.Column('step_order', sa.Integer, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('step_type', sa.Enum(
            'email', 'in_app_message', 'task', 'wait', 'condition',
            'webhook', 'segment_update', 'health_check', 'human_touchpoint',
            'sms', 'slack_notification', 'custom',
            name='cs_journey_step_type_enum', create_type=False
        ), nullable=False),
        sa.Column('config', JSON),
        sa.Column('wait_days', sa.Integer),
        sa.Column('wait_hours', sa.Integer),
        sa.Column('wait_until_event', sa.String(100)),
        sa.Column('wait_until_date_field', sa.String(100)),
        sa.Column('condition_rules', JSON),
        sa.Column('true_next_step_id', sa.Integer),
        sa.Column('false_next_step_id', sa.Integer),
        sa.Column('next_step_id', sa.Integer),
        sa.Column('is_terminal', sa.Boolean, server_default='false'),
        sa.Column('default_assignee_role', sa.String(50)),
        sa.Column('task_due_days', sa.Integer),
        sa.Column('task_priority', sa.String(20)),
        sa.Column('email_template_id', sa.Integer),
        sa.Column('in_app_message_config', JSON),
        sa.Column('times_executed', sa.Integer, server_default='0'),
        sa.Column('success_count', sa.Integer, server_default='0'),
        sa.Column('failure_count', sa.Integer, server_default='0'),
        sa.Column('avg_completion_time_hours', sa.Float),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('skip_if_condition', JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Playbooks table
    op.create_table(
        'cs_playbooks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.Enum(
            'onboarding', 'adoption', 'renewal', 'churn_risk',
            'expansion', 'escalation', 'qbr', 'executive_sponsor',
            'champion_change', 'implementation', 'training', 'custom',
            name='cs_playbook_category_enum', create_type=False
        )),
        sa.Column('trigger_type', sa.Enum(
            'manual', 'health_threshold', 'segment_entry', 'event',
            'days_to_renewal', 'scheduled',
            name='cs_playbook_trigger_enum', create_type=False
        )),
        sa.Column('trigger_health_threshold', sa.Integer),
        sa.Column('trigger_health_direction', sa.String(10)),
        sa.Column('trigger_days_to_renewal', sa.Integer),
        sa.Column('trigger_event', sa.String(100)),
        sa.Column('trigger_segment_id', sa.Integer, sa.ForeignKey('cs_segments.id')),
        sa.Column('trigger_config', JSON),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'critical', name='cs_playbook_priority_enum', create_type=False)),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('auto_assign', sa.Boolean, server_default='true'),
        sa.Column('default_assignee_role', sa.String(50)),
        sa.Column('escalation_assignee_role', sa.String(50)),
        sa.Column('estimated_hours', sa.Float),
        sa.Column('target_completion_days', sa.Integer),
        sa.Column('success_criteria', JSON),
        sa.Column('allow_parallel_execution', sa.Boolean, server_default='false'),
        sa.Column('max_active_per_customer', sa.Integer, server_default='1'),
        sa.Column('cooldown_days', sa.Integer),
        sa.Column('times_triggered', sa.Integer, server_default='0'),
        sa.Column('times_completed', sa.Integer, server_default='0'),
        sa.Column('times_successful', sa.Integer, server_default='0'),
        sa.Column('avg_completion_days', sa.Float),
        sa.Column('success_rate', sa.Float),
        sa.Column('created_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('owned_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Playbook Steps table
    op.create_table(
        'cs_playbook_steps',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('playbook_id', sa.Integer, sa.ForeignKey('cs_playbooks.id'), nullable=False, index=True),
        sa.Column('step_order', sa.Integer, nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('step_type', sa.Enum(
            'call', 'email', 'meeting', 'internal_task', 'product_demo',
            'training', 'review', 'escalation', 'documentation',
            'approval', 'notification', 'custom',
            name='cs_playbook_step_type_enum', create_type=False
        ), nullable=False),
        sa.Column('default_assignee_role', sa.String(50)),
        sa.Column('assignee_override_allowed', sa.Boolean, server_default='true'),
        sa.Column('days_from_start', sa.Integer, server_default='0'),
        sa.Column('due_days', sa.Integer),
        sa.Column('is_required', sa.Boolean, server_default='true'),
        sa.Column('depends_on_step_ids', JSON),
        sa.Column('blocks_step_ids', JSON),
        sa.Column('email_template_id', sa.Integer),
        sa.Column('email_subject', sa.String(255)),
        sa.Column('email_body_template', sa.Text),
        sa.Column('meeting_agenda_template', sa.Text),
        sa.Column('talk_track', sa.Text),
        sa.Column('instructions', sa.Text),
        sa.Column('required_artifacts', JSON),
        sa.Column('required_outcomes', JSON),
        sa.Column('completion_type', sa.Enum(
            'manual', 'auto_email_sent', 'auto_meeting_scheduled', 'approval_received',
            name='cs_completion_type_enum', create_type=False
        )),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('skip_if_condition', JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Playbook Executions table
    op.create_table(
        'cs_playbook_executions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('playbook_id', sa.Integer, sa.ForeignKey('cs_playbooks.id'), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('status', sa.Enum(
            'active', 'paused', 'completed', 'cancelled', 'failed',
            name='cs_playbook_exec_status_enum', create_type=False
        )),
        sa.Column('current_step_order', sa.Integer, server_default='1'),
        sa.Column('steps_completed', sa.Integer, server_default='0'),
        sa.Column('steps_total', sa.Integer),
        sa.Column('assigned_to_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('escalated_to_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('target_completion_date', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('cancelled_at', sa.DateTime(timezone=True)),
        sa.Column('triggered_by', sa.String(100)),
        sa.Column('trigger_reason', sa.Text),
        sa.Column('outcome', sa.Enum('successful', 'unsuccessful', 'partial', 'cancelled', name='cs_playbook_outcome_enum', create_type=False)),
        sa.Column('outcome_notes', sa.Text),
        sa.Column('success_criteria_met', JSON),
        sa.Column('health_score_at_start', sa.Integer),
        sa.Column('health_score_at_end', sa.Integer),
        sa.Column('total_time_spent_minutes', sa.Integer, server_default='0'),
        sa.Column('extra_data', JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Journey Enrollments table
    op.create_table(
        'cs_journey_enrollments',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('journey_id', sa.Integer, sa.ForeignKey('cs_journeys.id'), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('status', sa.Enum(
            'active', 'paused', 'completed', 'exited', 'failed',
            name='cs_enrollment_status_enum', create_type=False
        )),
        sa.Column('current_step_id', sa.Integer, sa.ForeignKey('cs_journey_steps.id')),
        sa.Column('current_step_started_at', sa.DateTime(timezone=True)),
        sa.Column('steps_completed', sa.Integer, server_default='0'),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('exited_at', sa.DateTime(timezone=True)),
        sa.Column('exit_reason', sa.Enum(
            'completed', 'goal_achieved', 'manual_exit', 'segment_exit',
            'health_threshold', 'event_triggered', 'timeout', 'error',
            name='cs_exit_reason_enum', create_type=False
        )),
        sa.Column('exit_notes', sa.Text),
        sa.Column('goal_achieved', sa.Boolean, server_default='false'),
        sa.Column('goal_value_at_start', sa.Float),
        sa.Column('goal_value_at_end', sa.Float),
        sa.Column('health_score_at_start', sa.Integer),
        sa.Column('health_score_at_end', sa.Integer),
        sa.Column('enrolled_by', sa.String(100)),
        sa.Column('enrollment_trigger', sa.String(100)),
        sa.Column('extra_data', JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Journey Step Executions table
    op.create_table(
        'cs_journey_step_executions',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('enrollment_id', sa.Integer, sa.ForeignKey('cs_journey_enrollments.id'), nullable=False, index=True),
        sa.Column('step_id', sa.Integer, sa.ForeignKey('cs_journey_steps.id'), nullable=False, index=True),
        sa.Column('status', sa.Enum(
            'pending', 'in_progress', 'completed', 'skipped', 'failed', 'waiting',
            name='cs_step_execution_status_enum', create_type=False
        )),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('scheduled_for', sa.DateTime(timezone=True)),
        sa.Column('outcome', sa.String(100)),
        sa.Column('outcome_details', JSON),
        sa.Column('condition_result', sa.Boolean),
        sa.Column('condition_evaluation', JSON),
        sa.Column('task_id', sa.Integer),  # FK added later
        sa.Column('error_message', sa.Text),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('max_retries', sa.Integer, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # CS Tasks table
    op.create_table(
        'cs_tasks',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('playbook_execution_id', sa.Integer, sa.ForeignKey('cs_playbook_executions.id'), index=True),
        sa.Column('playbook_step_id', sa.Integer, sa.ForeignKey('cs_playbook_steps.id')),
        sa.Column('journey_enrollment_id', sa.Integer, sa.ForeignKey('cs_journey_enrollments.id'), index=True),
        sa.Column('journey_step_id', sa.Integer, sa.ForeignKey('cs_journey_steps.id')),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('task_type', sa.Enum(
            'call', 'email', 'meeting', 'internal', 'review',
            'escalation', 'follow_up', 'documentation', 'training',
            'product_demo', 'qbr', 'renewal', 'custom',
            name='cs_task_type_enum', create_type=False
        )),
        sa.Column('category', sa.Enum(
            'onboarding', 'adoption', 'retention', 'expansion',
            'support', 'relationship', 'administrative',
            name='cs_task_category_enum', create_type=False
        )),
        sa.Column('assigned_to_user_id', sa.Integer, sa.ForeignKey('api_users.id'), index=True),
        sa.Column('assigned_to_role', sa.String(50)),
        sa.Column('assigned_by_user_id', sa.Integer, sa.ForeignKey('api_users.id')),
        sa.Column('assigned_at', sa.DateTime(timezone=True)),
        sa.Column('contact_name', sa.String(100)),
        sa.Column('contact_email', sa.String(255)),
        sa.Column('contact_phone', sa.String(50)),
        sa.Column('contact_role', sa.String(100)),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'critical', name='cs_task_priority_enum', create_type=False)),
        sa.Column('status', sa.Enum(
            'pending', 'in_progress', 'completed', 'cancelled', 'blocked', 'snoozed',
            name='cs_task_status_enum', create_type=False
        )),
        sa.Column('due_date', sa.Date),
        sa.Column('due_datetime', sa.DateTime(timezone=True)),
        sa.Column('reminder_at', sa.DateTime(timezone=True)),
        sa.Column('snoozed_until', sa.DateTime(timezone=True)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('cancelled_at', sa.DateTime(timezone=True)),
        sa.Column('outcome', sa.Enum(
            'successful', 'unsuccessful', 'rescheduled', 'no_response',
            'voicemail', 'escalated', 'cancelled', 'not_applicable',
            name='cs_task_outcome_enum', create_type=False
        )),
        sa.Column('outcome_notes', sa.Text),
        sa.Column('scheduled_datetime', sa.DateTime(timezone=True)),
        sa.Column('meeting_link', sa.String(500)),
        sa.Column('meeting_duration_minutes', sa.Integer),
        sa.Column('meeting_type', sa.String(50)),
        sa.Column('email_template_id', sa.Integer),
        sa.Column('email_sent_at', sa.DateTime(timezone=True)),
        sa.Column('email_opened_at', sa.DateTime(timezone=True)),
        sa.Column('email_clicked_at', sa.DateTime(timezone=True)),
        sa.Column('required_artifacts', JSON),
        sa.Column('completed_artifacts', JSON),
        sa.Column('time_spent_minutes', sa.Integer, server_default='0'),
        sa.Column('estimated_minutes', sa.Integer),
        sa.Column('depends_on_task_ids', JSON),
        sa.Column('blocks_task_ids', JSON),
        sa.Column('is_recurring', sa.Boolean, server_default='false'),
        sa.Column('recurrence_pattern', sa.String(50)),
        sa.Column('recurrence_end_date', sa.Date),
        sa.Column('parent_task_id', sa.Integer, sa.ForeignKey('cs_tasks.id')),
        sa.Column('instructions', sa.Text),
        sa.Column('talk_track', sa.Text),
        sa.Column('agenda', sa.Text),
        sa.Column('related_url', sa.String(500)),
        sa.Column('recording_url', sa.String(500)),
        sa.Column('document_url', sa.String(500)),
        sa.Column('source', sa.String(100)),
        sa.Column('tags', JSON),
        sa.Column('task_data', JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Add FK for task_id in journey_step_executions
    op.create_foreign_key(
        'fk_journey_step_exec_task',
        'cs_journey_step_executions', 'cs_tasks',
        ['task_id'], ['id']
    )

    # Touchpoints table
    op.create_table(
        'cs_touchpoints',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('touchpoint_type', sa.Enum(
            'email_sent', 'email_opened', 'email_clicked', 'email_replied',
            'call_outbound', 'call_inbound', 'call_missed', 'voicemail',
            'meeting_scheduled', 'meeting_held', 'meeting_cancelled', 'meeting_no_show',
            'sms_sent', 'sms_received', 'chat_session', 'video_call',
            'product_login', 'feature_usage', 'feature_adoption',
            'webinar_registered', 'webinar_attended', 'training_completed',
            'support_ticket_opened', 'support_ticket_resolved', 'support_escalation',
            'nps_response', 'csat_response', 'survey_response', 'review_posted',
            'qbr_held', 'renewal_discussion', 'expansion_discussion',
            'contract_signed', 'invoice_paid', 'payment_issue',
            'internal_note', 'health_alert', 'risk_flag',
            'in_app_message_sent', 'in_app_message_clicked',
            'document_shared', 'document_viewed', 'event_attended', 'referral_made', 'custom',
            name='cs_touchpoint_type_enum', create_type=False
        ), nullable=False),
        sa.Column('subject', sa.String(255)),
        sa.Column('summary', sa.Text),
        sa.Column('description', sa.Text),
        sa.Column('direction', sa.Enum('inbound', 'outbound', 'internal', name='cs_touchpoint_direction_enum', create_type=False)),
        sa.Column('channel', sa.Enum(
            'email', 'phone', 'video', 'in_app', 'in_person',
            'chat', 'sms', 'social', 'webinar', 'event', 'other',
            name='cs_touchpoint_channel_enum', create_type=False
        )),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('api_users.id'), index=True),
        sa.Column('user_role', sa.String(50)),
        sa.Column('contact_name', sa.String(100)),
        sa.Column('contact_email', sa.String(255)),
        sa.Column('contact_role', sa.String(100)),
        sa.Column('contact_is_champion', sa.Boolean, server_default='false'),
        sa.Column('contact_is_executive', sa.Boolean, server_default='false'),
        sa.Column('attendee_count', sa.Integer),
        sa.Column('sentiment_score', sa.Float),
        sa.Column('sentiment_label', sa.Enum(
            'very_negative', 'negative', 'neutral', 'positive', 'very_positive',
            name='cs_sentiment_enum', create_type=False
        )),
        sa.Column('sentiment_confidence', sa.Float),
        sa.Column('key_topics', JSON),
        sa.Column('action_items', JSON),
        sa.Column('risk_signals', JSON),
        sa.Column('expansion_signals', JSON),
        sa.Column('key_quotes', JSON),
        sa.Column('engagement_score', sa.Integer),
        sa.Column('was_positive', sa.Boolean),
        sa.Column('task_id', sa.Integer, sa.ForeignKey('cs_tasks.id')),
        sa.Column('journey_enrollment_id', sa.Integer, sa.ForeignKey('cs_journey_enrollments.id')),
        sa.Column('playbook_execution_id', sa.Integer, sa.ForeignKey('cs_playbook_executions.id')),
        sa.Column('support_ticket_id', sa.String(100)),
        sa.Column('duration_minutes', sa.Integer),
        sa.Column('scheduled_duration_minutes', sa.Integer),
        sa.Column('start_time', sa.DateTime(timezone=True)),
        sa.Column('end_time', sa.DateTime(timezone=True)),
        sa.Column('meeting_link', sa.String(500)),
        sa.Column('recording_url', sa.String(500)),
        sa.Column('transcript_url', sa.String(500)),
        sa.Column('email_message_id', sa.String(255)),
        sa.Column('email_thread_id', sa.String(255)),
        sa.Column('email_opened_count', sa.Integer),
        sa.Column('email_click_count', sa.Integer),
        sa.Column('email_reply_received', sa.Boolean),
        sa.Column('feature_name', sa.String(100)),
        sa.Column('usage_count', sa.Integer),
        sa.Column('usage_duration_minutes', sa.Integer),
        sa.Column('nps_score', sa.Integer),
        sa.Column('csat_score', sa.Integer),
        sa.Column('survey_responses', JSON),
        sa.Column('attachments', JSON),
        sa.Column('notes', sa.Text),
        sa.Column('source', sa.String(100)),
        sa.Column('external_id', sa.String(255)),
        sa.Column('source_url', sa.String(500)),
        sa.Column('is_internal', sa.Boolean, server_default='false'),
        sa.Column('is_confidential', sa.Boolean, server_default='false'),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create indexes for common queries
    op.create_index('ix_cs_health_scores_status', 'cs_health_scores', ['health_status'])
    op.create_index('ix_cs_health_scores_overall', 'cs_health_scores', ['overall_score'])
    op.create_index('ix_cs_tasks_due_date', 'cs_tasks', ['due_date'])
    op.create_index('ix_cs_tasks_status_priority', 'cs_tasks', ['status', 'priority'])
    op.create_index('ix_cs_touchpoints_type', 'cs_touchpoints', ['touchpoint_type'])


def downgrade():
    # Drop tables in reverse order
    op.drop_table('cs_touchpoints')
    op.drop_constraint('fk_journey_step_exec_task', 'cs_journey_step_executions', type_='foreignkey')
    op.drop_table('cs_tasks')
    op.drop_table('cs_journey_step_executions')
    op.drop_table('cs_journey_enrollments')
    op.drop_table('cs_playbook_executions')
    op.drop_table('cs_playbook_steps')
    op.drop_table('cs_playbooks')
    op.drop_table('cs_journey_steps')
    op.drop_table('cs_journeys')
    op.drop_table('cs_customer_segments')
    op.drop_table('cs_segments')
    op.drop_table('cs_health_score_events')
    op.drop_table('cs_health_scores')

    # Drop ENUM types
    op.execute("""
        DROP TYPE IF EXISTS cs_sentiment_enum;
        DROP TYPE IF EXISTS cs_touchpoint_channel_enum;
        DROP TYPE IF EXISTS cs_touchpoint_direction_enum;
        DROP TYPE IF EXISTS cs_touchpoint_type_enum;
        DROP TYPE IF EXISTS cs_task_outcome_enum;
        DROP TYPE IF EXISTS cs_task_status_enum;
        DROP TYPE IF EXISTS cs_task_priority_enum;
        DROP TYPE IF EXISTS cs_task_category_enum;
        DROP TYPE IF EXISTS cs_task_type_enum;
        DROP TYPE IF EXISTS cs_playbook_outcome_enum;
        DROP TYPE IF EXISTS cs_playbook_exec_status_enum;
        DROP TYPE IF EXISTS cs_completion_type_enum;
        DROP TYPE IF EXISTS cs_playbook_step_type_enum;
        DROP TYPE IF EXISTS cs_playbook_priority_enum;
        DROP TYPE IF EXISTS cs_playbook_trigger_enum;
        DROP TYPE IF EXISTS cs_playbook_category_enum;
        DROP TYPE IF EXISTS cs_step_execution_status_enum;
        DROP TYPE IF EXISTS cs_exit_reason_enum;
        DROP TYPE IF EXISTS cs_enrollment_status_enum;
        DROP TYPE IF EXISTS cs_journey_step_type_enum;
        DROP TYPE IF EXISTS cs_journey_trigger_enum;
        DROP TYPE IF EXISTS cs_journey_type_enum;
        DROP TYPE IF EXISTS cs_rule_mode_enum;
        DROP TYPE IF EXISTS cs_segment_type_enum;
        DROP TYPE IF EXISTS cs_health_event_type_enum;
        DROP TYPE IF EXISTS cs_score_trend_enum;
        DROP TYPE IF EXISTS cs_health_status_enum;
    """)
