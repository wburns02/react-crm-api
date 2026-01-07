"""Add role views tables for demo mode

Revision ID: 016_add_role_views_tables
Revises: 015_make_test_user_admin
Create Date: 2026-01-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = '016_add_role_views_tables'
down_revision = '015_make_test_user_admin'
branch_labels = None
depends_on = None


def upgrade():
    # Create role_views table
    op.create_table(
        'role_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('role_key', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('icon', sa.String(10), nullable=True),
        sa.Column('color', sa.String(20), nullable=True),
        sa.Column('visible_modules', JSON, nullable=True, default=[]),
        sa.Column('default_route', sa.String(100), nullable=True, default='/'),
        sa.Column('dashboard_widgets', JSON, nullable=True, default=[]),
        sa.Column('quick_actions', JSON, nullable=True, default=[]),
        sa.Column('features', JSON, nullable=True, default={}),
        sa.Column('is_active', sa.Boolean(), nullable=True, default=True),
        sa.Column('sort_order', sa.Integer(), nullable=True, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_role_views_id', 'role_views', ['id'])
    op.create_index('ix_role_views_role_key', 'role_views', ['role_key'], unique=True)

    # Create user_role_sessions table
    op.create_table(
        'user_role_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('current_role_key', sa.String(50), nullable=False),
        sa.Column('switched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['api_users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_role_key'], ['role_views.role_key'], ondelete='CASCADE'),
    )
    op.create_index('ix_user_role_sessions_id', 'user_role_sessions', ['id'])
    op.create_index('ix_user_role_sessions_user_id', 'user_role_sessions', ['user_id'])

    # Seed default roles
    op.execute("""
        INSERT INTO role_views (role_key, display_name, description, icon, color, sort_order, visible_modules, default_route, dashboard_widgets, quick_actions, features, is_active)
        VALUES
        ('admin', 'Administrator', 'Full system access with all features and settings', '👑', 'purple', 1, '["*"]', '/', '["revenue_chart", "work_orders_summary", "customer_health", "team_performance"]', '["create_work_order", "add_customer", "view_reports", "manage_users"]', '{"can_manage_users": true, "can_view_reports": true, "can_manage_settings": true}', true),
        ('executive', 'Executive', 'High-level KPIs, financial metrics, and business intelligence', '📊', 'blue', 2, '["dashboard", "reports", "analytics", "customer-success"]', '/', '["revenue_kpi", "customer_growth", "profitability", "forecasts"]', '["view_reports", "export_data", "schedule_review"]', '{"can_view_reports": true, "can_export_data": true}', true),
        ('manager', 'Operations Manager', 'Day-to-day operations, team management, and scheduling oversight', '📋', 'green', 3, '["dashboard", "schedule", "work-orders", "technicians", "customers", "reports"]', '/schedule', '["today_schedule", "team_availability", "pending_work_orders", "customer_issues"]', '["create_work_order", "assign_technician", "view_schedule", "contact_customer"]', '{"can_assign_work": true, "can_view_reports": true, "can_manage_schedule": true}', true),
        ('technician', 'Field Technician', 'Mobile-optimized view for field work and service completion', '🔧', 'orange', 4, '["my-schedule", "work-orders", "customers", "equipment"]', '/my-schedule', '["my_jobs_today", "next_appointment", "route_map", "time_tracker"]', '["start_job", "complete_job", "add_notes", "call_customer"]', '{"can_update_work_orders": true, "can_capture_photos": true, "can_collect_signatures": true}', true),
        ('phone_agent', 'Phone Agent', 'Customer service focus with quick access to customer info and scheduling', '📞', 'cyan', 5, '["customers", "work-orders", "schedule", "communications"]', '/customers', '["incoming_calls", "customer_search", "recent_interactions", "quick_schedule"]', '["search_customer", "create_work_order", "schedule_appointment", "send_sms"]', '{"can_create_work_orders": true, "can_schedule": true, "can_communicate": true}', true),
        ('dispatcher', 'Dispatcher', 'Schedule management, route optimization, and real-time tracking', '🗺️', 'indigo', 6, '["schedule", "schedule-map", "work-orders", "technicians", "fleet"]', '/schedule-map', '["live_map", "unassigned_jobs", "technician_status", "route_efficiency"]', '["assign_job", "optimize_routes", "contact_technician", "reschedule"]', '{"can_assign_work": true, "can_manage_schedule": true, "can_track_fleet": true}', true),
        ('billing', 'Billing Specialist', 'Invoicing, payments, and financial operations', '💰', 'emerald', 7, '["invoices", "payments", "customers", "reports"]', '/invoices', '["outstanding_invoices", "payments_today", "aging_report", "collection_queue"]', '["create_invoice", "record_payment", "send_reminder", "generate_statement"]', '{"can_manage_invoices": true, "can_process_payments": true, "can_view_financial_reports": true}', true)
        ON CONFLICT (role_key) DO NOTHING;
    """)


def downgrade():
    op.drop_table('user_role_sessions')
    op.drop_table('role_views')
