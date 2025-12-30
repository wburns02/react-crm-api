"""Add all phase tables (AI, Signatures, Pricing, Agents, Predictions, Marketing, Payroll)

Revision ID: 005_add_all_phase_tables
Revises: 004_add_tickets_equipment_inventory
Create Date: 2024-12-30

Note: Using IF NOT EXISTS pattern to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '005_add_all_phase_tables'
down_revision = '004_add_tickets_equipment_inventory'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"
    ), {"table_name": table_name})
    return result.scalar()


def upgrade():
    """Create all phase tables."""
    conn = op.get_bind()

    # ============ Phase 1: AI Infrastructure ============

    # AI Embeddings table
    if not table_exists(conn, 'ai_embeddings'):
        op.create_table(
            'ai_embeddings',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('entity_type', sa.String(50), nullable=False, index=True),
            sa.Column('entity_id', sa.String(36), nullable=False, index=True),
            sa.Column('content_hash', sa.String(64), nullable=True),
            sa.Column('embedding', sa.Text, nullable=True),  # JSON array of floats
            sa.Column('model_name', sa.String(100), default='bge-large-en-v1.5'),
            sa.Column('dimensions', sa.Integer, default=1024),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        op.create_index('ix_ai_embeddings_entity', 'ai_embeddings', ['entity_type', 'entity_id'], unique=True)
        print("Created ai_embeddings table")

    # AI Conversations table
    if not table_exists(conn, 'ai_conversations'):
        op.create_table(
            'ai_conversations',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('user_id', sa.Integer, nullable=True, index=True),
            sa.Column('title', sa.String(255), nullable=True),
            sa.Column('context_type', sa.String(50), nullable=True),
            sa.Column('context_id', sa.String(36), nullable=True),
            sa.Column('model_name', sa.String(100), default='llama-3.1-70b'),
            sa.Column('total_tokens', sa.Integer, default=0),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created ai_conversations table")

    # AI Messages table
    if not table_exists(conn, 'ai_messages'):
        op.create_table(
            'ai_messages',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('conversation_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('content', sa.Text, nullable=False),
            sa.Column('tokens', sa.Integer, default=0),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created ai_messages table")

    # ============ Phase 2: RingCentral Call Logs ============

    if not table_exists(conn, 'call_logs'):
        op.create_table(
            'call_logs',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('ringcentral_id', sa.String(100), unique=True, nullable=True, index=True),
            sa.Column('customer_id', sa.Integer, nullable=True, index=True),
            sa.Column('technician_id', sa.String(36), nullable=True),
            sa.Column('direction', sa.String(20), nullable=False),
            sa.Column('from_number', sa.String(20), nullable=True),
            sa.Column('to_number', sa.String(20), nullable=True),
            sa.Column('start_time', sa.DateTime(timezone=True), nullable=True),
            sa.Column('end_time', sa.DateTime(timezone=True), nullable=True),
            sa.Column('duration_seconds', sa.Integer, default=0),
            sa.Column('status', sa.String(30), nullable=True),
            sa.Column('result', sa.String(50), nullable=True),
            sa.Column('recording_url', sa.String(500), nullable=True),
            sa.Column('transcription', sa.Text, nullable=True),
            sa.Column('summary', sa.Text, nullable=True),
            sa.Column('sentiment', sa.String(20), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created call_logs table")

    # ============ Phase 3: E-Signatures ============

    if not table_exists(conn, 'signature_requests'):
        op.create_table(
            'signature_requests',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('quote_id', sa.String(36), nullable=True, index=True),
            sa.Column('work_order_id', sa.String(36), nullable=True),
            sa.Column('customer_id', sa.Integer, nullable=True, index=True),
            sa.Column('document_type', sa.String(50), nullable=False),
            sa.Column('document_title', sa.String(255), nullable=False),
            sa.Column('document_content', sa.Text, nullable=True),
            sa.Column('document_hash', sa.String(64), nullable=True),
            sa.Column('signer_name', sa.String(255), nullable=False),
            sa.Column('signer_email', sa.String(255), nullable=True),
            sa.Column('signer_phone', sa.String(20), nullable=True),
            sa.Column('signing_token', sa.String(100), unique=True, nullable=False),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('status', sa.String(30), default='pending', index=True),
            sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('viewed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('signed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('declined_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('declined_reason', sa.Text, nullable=True),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created signature_requests table")

    if not table_exists(conn, 'signatures'):
        op.create_table(
            'signatures',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('request_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('signature_data', sa.Text, nullable=False),
            sa.Column('signature_type', sa.String(20), default='draw'),
            sa.Column('ip_address', sa.String(45), nullable=True),
            sa.Column('user_agent', sa.String(500), nullable=True),
            sa.Column('latitude', sa.Float, nullable=True),
            sa.Column('longitude', sa.Float, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created signatures table")

    if not table_exists(conn, 'signed_documents'):
        op.create_table(
            'signed_documents',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('request_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('signature_id', UUID(as_uuid=True), nullable=False),
            sa.Column('pdf_url', sa.String(500), nullable=True),
            sa.Column('pdf_hash', sa.String(64), nullable=True),
            sa.Column('audit_trail', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created signed_documents table")

    # ============ Phase 4: Pricing Engine ============

    if not table_exists(conn, 'service_catalog'):
        op.create_table(
            'service_catalog',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('code', sa.String(50), unique=True, nullable=False, index=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('category', sa.String(100), nullable=True, index=True),
            sa.Column('base_price', sa.Float, nullable=False),
            sa.Column('unit', sa.String(20), default='each'),
            sa.Column('min_price', sa.Float, nullable=True),
            sa.Column('max_price', sa.Float, nullable=True),
            sa.Column('cost', sa.Float, nullable=True),
            sa.Column('target_margin', sa.Float, nullable=True),
            sa.Column('is_taxable', sa.Boolean, default=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('estimated_duration_hours', sa.Float, nullable=True),
            sa.Column('requires_equipment', sa.Boolean, default=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created service_catalog table")

    if not table_exists(conn, 'pricing_zones'):
        op.create_table(
            'pricing_zones',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('zip_codes', sa.Text, nullable=True),
            sa.Column('multiplier', sa.Float, default=1.0),
            sa.Column('min_service_fee', sa.Float, nullable=True),
            sa.Column('travel_fee', sa.Float, default=0.0),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created pricing_zones table")

    if not table_exists(conn, 'pricing_rules'):
        op.create_table(
            'pricing_rules',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('rule_type', sa.String(50), nullable=False, index=True),
            sa.Column('conditions', sa.Text, nullable=True),
            sa.Column('adjustment_type', sa.String(20), default='percent'),
            sa.Column('adjustment_value', sa.Float, nullable=False),
            sa.Column('priority', sa.Integer, default=0),
            sa.Column('start_date', sa.Date, nullable=True),
            sa.Column('end_date', sa.Date, nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created pricing_rules table")

    if not table_exists(conn, 'customer_pricing_tiers'):
        op.create_table(
            'customer_pricing_tiers',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, nullable=False, index=True),
            sa.Column('tier_name', sa.String(50), nullable=False),
            sa.Column('discount_percent', sa.Float, default=0.0),
            sa.Column('effective_date', sa.Date, nullable=False),
            sa.Column('end_date', sa.Date, nullable=True),
            sa.Column('reason', sa.Text, nullable=True),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created customer_pricing_tiers table")

    # ============ Phase 5: AI Agents ============

    if not table_exists(conn, 'ai_agents'):
        op.create_table(
            'ai_agents',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('agent_type', sa.String(50), nullable=False, index=True),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('system_prompt', sa.Text, nullable=True),
            sa.Column('tools', sa.Text, nullable=True),
            sa.Column('config', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('total_conversations', sa.Integer, default=0),
            sa.Column('total_tasks_completed', sa.Integer, default=0),
            sa.Column('avg_satisfaction', sa.Float, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created ai_agents table")

    if not table_exists(conn, 'agent_conversations'):
        op.create_table(
            'agent_conversations',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('agent_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('customer_id', sa.Integer, nullable=True, index=True),
            sa.Column('channel', sa.String(20), default='sms'),
            sa.Column('status', sa.String(30), default='active', index=True),
            sa.Column('escalated', sa.Boolean, default=False),
            sa.Column('escalated_to', sa.String(100), nullable=True),
            sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('satisfaction_rating', sa.Integer, nullable=True),
            sa.Column('context', sa.Text, nullable=True),
            sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("Created agent_conversations table")

    if not table_exists(conn, 'agent_messages'):
        op.create_table(
            'agent_messages',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('conversation_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('role', sa.String(20), nullable=False),
            sa.Column('content', sa.Text, nullable=False),
            sa.Column('tool_calls', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created agent_messages table")

    if not table_exists(conn, 'agent_tasks'):
        op.create_table(
            'agent_tasks',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('agent_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('conversation_id', UUID(as_uuid=True), nullable=True),
            sa.Column('task_type', sa.String(50), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('input_data', sa.Text, nullable=True),
            sa.Column('output_data', sa.Text, nullable=True),
            sa.Column('status', sa.String(30), default='pending', index=True),
            sa.Column('error_message', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("Created agent_tasks table")

    # ============ Phase 6: Predictive Analytics ============

    if not table_exists(conn, 'lead_scores'):
        op.create_table(
            'lead_scores',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, nullable=False, index=True),
            sa.Column('score', sa.Float, nullable=False),
            sa.Column('score_breakdown', sa.Text, nullable=True),
            sa.Column('model_version', sa.String(50), nullable=True),
            sa.Column('features_used', sa.Text, nullable=True),
            sa.Column('predicted_value', sa.Float, nullable=True),
            sa.Column('predicted_close_date', sa.Date, nullable=True),
            sa.Column('confidence', sa.Float, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index('ix_lead_scores_customer_created', 'lead_scores', ['customer_id', 'created_at'])
        print("Created lead_scores table")

    if not table_exists(conn, 'churn_predictions'):
        op.create_table(
            'churn_predictions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('customer_id', sa.Integer, nullable=False, index=True),
            sa.Column('churn_probability', sa.Float, nullable=False),
            sa.Column('risk_level', sa.String(20), nullable=False),
            sa.Column('risk_factors', sa.Text, nullable=True),
            sa.Column('recommended_actions', sa.Text, nullable=True),
            sa.Column('model_version', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created churn_predictions table")

    if not table_exists(conn, 'revenue_forecasts'):
        op.create_table(
            'revenue_forecasts',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('forecast_date', sa.Date, nullable=False, index=True),
            sa.Column('period_type', sa.String(20), nullable=False),
            sa.Column('predicted_revenue', sa.Float, nullable=False),
            sa.Column('confidence_low', sa.Float, nullable=True),
            sa.Column('confidence_high', sa.Float, nullable=True),
            sa.Column('actual_revenue', sa.Float, nullable=True),
            sa.Column('factors', sa.Text, nullable=True),
            sa.Column('model_version', sa.String(50), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created revenue_forecasts table")

    if not table_exists(conn, 'deal_health'):
        op.create_table(
            'deal_health',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('quote_id', sa.String(36), nullable=False, index=True),
            sa.Column('customer_id', sa.Integer, nullable=True),
            sa.Column('health_score', sa.Float, nullable=False),
            sa.Column('status', sa.String(30), default='healthy'),
            sa.Column('days_since_activity', sa.Integer, nullable=True),
            sa.Column('engagement_score', sa.Float, nullable=True),
            sa.Column('risk_factors', sa.Text, nullable=True),
            sa.Column('recommendations', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created deal_health table")

    if not table_exists(conn, 'prediction_models'):
        op.create_table(
            'prediction_models',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('model_type', sa.String(50), nullable=False, index=True),
            sa.Column('version', sa.String(50), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('metrics', sa.Text, nullable=True),
            sa.Column('parameters', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, default=False),
            sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('training_samples', sa.Integer, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created prediction_models table")

    # ============ Phase 7: Marketing Automation ============

    if not table_exists(conn, 'marketing_campaigns'):
        op.create_table(
            'marketing_campaigns',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('campaign_type', sa.String(50), nullable=False, index=True),
            sa.Column('status', sa.String(30), default='draft', index=True),
            sa.Column('target_segment', sa.Text, nullable=True),
            sa.Column('start_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('end_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('budget', sa.Float, nullable=True),
            sa.Column('total_sent', sa.Integer, default=0),
            sa.Column('total_opened', sa.Integer, default=0),
            sa.Column('total_clicked', sa.Integer, default=0),
            sa.Column('total_converted', sa.Integer, default=0),
            sa.Column('total_revenue', sa.Float, default=0.0),
            sa.Column('created_by', sa.String(100), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created marketing_campaigns table")

    if not table_exists(conn, 'marketing_workflows'):
        op.create_table(
            'marketing_workflows',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('campaign_id', UUID(as_uuid=True), nullable=True, index=True),
            sa.Column('trigger_type', sa.String(50), nullable=False),
            sa.Column('trigger_config', sa.Text, nullable=True),
            sa.Column('steps', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, default=False),
            sa.Column('total_enrolled', sa.Integer, default=0),
            sa.Column('total_completed', sa.Integer, default=0),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created marketing_workflows table")

    if not table_exists(conn, 'workflow_enrollments'):
        op.create_table(
            'workflow_enrollments',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('workflow_id', UUID(as_uuid=True), nullable=False, index=True),
            sa.Column('customer_id', sa.Integer, nullable=False, index=True),
            sa.Column('status', sa.String(30), default='active', index=True),
            sa.Column('current_step', sa.Integer, default=0),
            sa.Column('step_history', sa.Text, nullable=True),
            sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('paused_at', sa.DateTime(timezone=True), nullable=True),
        )
        print("Created workflow_enrollments table")

    if not table_exists(conn, 'email_templates'):
        op.create_table(
            'email_templates',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('subject', sa.String(500), nullable=False),
            sa.Column('body_html', sa.Text, nullable=False),
            sa.Column('body_text', sa.Text, nullable=True),
            sa.Column('category', sa.String(100), nullable=True, index=True),
            sa.Column('variables', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created email_templates table")

    if not table_exists(conn, 'sms_templates'):
        op.create_table(
            'sms_templates',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('body', sa.String(160), nullable=False),
            sa.Column('category', sa.String(100), nullable=True, index=True),
            sa.Column('variables', sa.Text, nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created sms_templates table")

    # ============ Phase 10: Payroll ============

    if not table_exists(conn, 'payroll_periods'):
        op.create_table(
            'payroll_periods',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('start_date', sa.Date, nullable=False, index=True),
            sa.Column('end_date', sa.Date, nullable=False),
            sa.Column('period_type', sa.String(20), default='biweekly'),
            sa.Column('status', sa.String(20), default='open', index=True),
            sa.Column('total_regular_hours', sa.Float, default=0.0),
            sa.Column('total_overtime_hours', sa.Float, default=0.0),
            sa.Column('total_gross_pay', sa.Float, default=0.0),
            sa.Column('total_commissions', sa.Float, default=0.0),
            sa.Column('technician_count', sa.Integer, default=0),
            sa.Column('approved_by', sa.String(100), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('export_file_url', sa.String(500), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )
        print("Created payroll_periods table")

    if not table_exists(conn, 'time_entries'):
        op.create_table(
            'time_entries',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('technician_id', sa.String(36), nullable=False, index=True),
            sa.Column('work_order_id', sa.String(36), nullable=True, index=True),
            sa.Column('payroll_period_id', UUID(as_uuid=True), nullable=True, index=True),
            sa.Column('entry_date', sa.Date, nullable=False, index=True),
            sa.Column('clock_in', sa.DateTime(timezone=True), nullable=False),
            sa.Column('clock_out', sa.DateTime(timezone=True), nullable=True),
            sa.Column('regular_hours', sa.Float, default=0.0),
            sa.Column('overtime_hours', sa.Float, default=0.0),
            sa.Column('break_minutes', sa.Integer, default=0),
            sa.Column('clock_in_lat', sa.Float, nullable=True),
            sa.Column('clock_in_lon', sa.Float, nullable=True),
            sa.Column('clock_out_lat', sa.Float, nullable=True),
            sa.Column('clock_out_lon', sa.Float, nullable=True),
            sa.Column('entry_type', sa.String(20), default='work'),
            sa.Column('status', sa.String(20), default='pending'),
            sa.Column('approved_by', sa.String(100), nullable=True),
            sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created time_entries table")

    if not table_exists(conn, 'commissions'):
        op.create_table(
            'commissions',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('technician_id', sa.String(36), nullable=False, index=True),
            sa.Column('work_order_id', sa.String(36), nullable=True),
            sa.Column('invoice_id', sa.String(36), nullable=True),
            sa.Column('payroll_period_id', UUID(as_uuid=True), nullable=True, index=True),
            sa.Column('commission_type', sa.String(50), nullable=False),
            sa.Column('base_amount', sa.Float, nullable=False),
            sa.Column('rate', sa.Float, nullable=False),
            sa.Column('rate_type', sa.String(20), default='percent'),
            sa.Column('commission_amount', sa.Float, nullable=False),
            sa.Column('status', sa.String(20), default='pending'),
            sa.Column('description', sa.Text, nullable=True),
            sa.Column('earned_date', sa.Date, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created commissions table")

    if not table_exists(conn, 'technician_pay_rates'):
        op.create_table(
            'technician_pay_rates',
            sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('technician_id', sa.String(36), unique=True, nullable=False, index=True),
            sa.Column('hourly_rate', sa.Float, nullable=False),
            sa.Column('overtime_multiplier', sa.Float, default=1.5),
            sa.Column('job_commission_rate', sa.Float, default=0.0),
            sa.Column('upsell_commission_rate', sa.Float, default=0.0),
            sa.Column('weekly_overtime_threshold', sa.Float, default=40.0),
            sa.Column('effective_date', sa.Date, nullable=False),
            sa.Column('end_date', sa.Date, nullable=True),
            sa.Column('is_active', sa.Boolean, default=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        print("Created technician_pay_rates table")

    print("All phase tables created successfully!")


def downgrade():
    """Drop all phase tables in reverse order."""
    # Phase 10: Payroll
    op.drop_table('technician_pay_rates')
    op.drop_table('commissions')
    op.drop_table('time_entries')
    op.drop_table('payroll_periods')

    # Phase 7: Marketing
    op.drop_table('sms_templates')
    op.drop_table('email_templates')
    op.drop_table('workflow_enrollments')
    op.drop_table('marketing_workflows')
    op.drop_table('marketing_campaigns')

    # Phase 6: Predictions
    op.drop_table('prediction_models')
    op.drop_table('deal_health')
    op.drop_table('revenue_forecasts')
    op.drop_table('churn_predictions')
    op.drop_index('ix_lead_scores_customer_created', 'lead_scores')
    op.drop_table('lead_scores')

    # Phase 5: AI Agents
    op.drop_table('agent_tasks')
    op.drop_table('agent_messages')
    op.drop_table('agent_conversations')
    op.drop_table('ai_agents')

    # Phase 4: Pricing
    op.drop_table('customer_pricing_tiers')
    op.drop_table('pricing_rules')
    op.drop_table('pricing_zones')
    op.drop_table('service_catalog')

    # Phase 3: E-Signatures
    op.drop_table('signed_documents')
    op.drop_table('signatures')
    op.drop_table('signature_requests')

    # Phase 2: Call Logs
    op.drop_table('call_logs')

    # Phase 1: AI
    op.drop_table('ai_messages')
    op.drop_table('ai_conversations')
    op.drop_index('ix_ai_embeddings_entity', 'ai_embeddings')
    op.drop_table('ai_embeddings')
