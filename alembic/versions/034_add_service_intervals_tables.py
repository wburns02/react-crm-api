"""Add service_intervals, customer_service_schedules, and service_reminders tables

Revision ID: 034_add_service_intervals
Revises: 033_ensure_work_order_photos_table
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '034_add_service_intervals'
down_revision = '033_ensure_work_order_photos_table'
branch_labels = None
depends_on = None


def upgrade():
    # Create service_intervals table (templates)
    op.create_table(
        'service_intervals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('service_type', sa.String(50), nullable=False),
        sa.Column('interval_months', sa.Integer, nullable=False),
        sa.Column('reminder_days_before', postgresql.JSON, default=[30, 14, 7]),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create customer_service_schedules table (assignments)
    op.create_table(
        'customer_service_schedules',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('service_interval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('service_intervals.id'), nullable=False, index=True),
        sa.Column('last_service_date', sa.Date, nullable=True),
        sa.Column('next_due_date', sa.Date, nullable=False, index=True),
        sa.Column('status', sa.String(30), default='upcoming', index=True),
        sa.Column('scheduled_work_order_id', sa.String(36), nullable=True, index=True),
        sa.Column('reminder_sent', sa.Boolean, default=False),
        sa.Column('last_reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create service_reminders table (audit log)
    op.create_table(
        'service_reminders',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('customer_service_schedules.id'), nullable=False, index=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('reminder_type', sa.String(20), nullable=False),
        sa.Column('days_before_due', sa.Integer, nullable=True),
        sa.Column('status', sa.String(20), default='sent'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('message_id', sa.Integer, sa.ForeignKey('messages.id'), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Seed default service interval templates
    op.execute("""
        INSERT INTO service_intervals (id, name, description, service_type, interval_months, reminder_days_before, is_active, created_at)
        VALUES
            (gen_random_uuid(), 'Septic Tank Pumping', 'Regular septic tank pumping service', 'pumping', 36, '[60, 30, 14]', true, NOW()),
            (gen_random_uuid(), 'Grease Trap Cleaning', 'Commercial grease trap maintenance', 'grease_trap', 3, '[14, 7, 3]', true, NOW()),
            (gen_random_uuid(), 'Annual Inspection', 'Yearly septic system inspection', 'inspection', 12, '[30, 14, 7]', true, NOW())
    """)


def downgrade():
    op.drop_table('service_reminders')
    op.drop_table('customer_service_schedules')
    op.drop_table('service_intervals')
