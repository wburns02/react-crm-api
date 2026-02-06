"""Create operational tables (compliance and service intervals)

Revision ID: 050
Revises: 049
Create Date: 2026-02-06

This migration creates tables for compliance tracking and service intervals.
These tables were defined in earlier migrations (008, 034) but were never
actually created in the production database. This migration creates them
with the current UUID-based schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Check if tables already exist
    tables_to_check = ['licenses', 'certifications', 'inspections',
                       'service_intervals', 'customer_service_schedules', 'service_reminders']

    for table_name in tables_to_check:
        exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
        ), {"t": table_name}).scalar()

        if exists:
            print(f"Table {table_name} already exists, skipping")
            continue

        # Create table based on its name
        if table_name == 'licenses':
            op.create_table(
                'licenses',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('license_number', sa.String(100), nullable=False, index=True),
                sa.Column('license_type', sa.String(100), nullable=False),
                sa.Column('issuing_authority', sa.String(255), nullable=True),
                sa.Column('issuing_state', sa.String(2), nullable=True),
                sa.Column('holder_type', sa.String(20), nullable=False, server_default='business'),
                sa.Column('holder_id', sa.String(36), nullable=True, index=True),
                sa.Column('holder_name', sa.String(255), nullable=True),
                sa.Column('issue_date', sa.Date, nullable=True),
                sa.Column('expiry_date', sa.Date, nullable=False, index=True),
                sa.Column('status', sa.String(20), server_default='active'),
                sa.Column('renewal_reminder_sent', sa.Boolean, server_default='false'),
                sa.Column('renewal_reminder_date', sa.Date, nullable=True),
                sa.Column('document_url', sa.String(500), nullable=True),
                sa.Column('notes', sa.Text, nullable=True),
                sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            )

        elif table_name == 'certifications':
            op.create_table(
                'certifications',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('name', sa.String(255), nullable=False),
                sa.Column('certification_type', sa.String(100), nullable=False),
                sa.Column('certification_number', sa.String(100), nullable=True),
                sa.Column('issuing_organization', sa.String(255), nullable=True),
                sa.Column('technician_id', sa.String(36), nullable=False, index=True),
                sa.Column('technician_name', sa.String(255), nullable=True),
                sa.Column('issue_date', sa.Date, nullable=True),
                sa.Column('expiry_date', sa.Date, nullable=True, index=True),
                sa.Column('status', sa.String(20), server_default='active'),
                sa.Column('renewal_reminder_sent', sa.Boolean, server_default='false'),
                sa.Column('requires_renewal', sa.Boolean, server_default='true'),
                sa.Column('renewal_interval_months', sa.Integer, nullable=True),
                sa.Column('training_hours', sa.Integer, nullable=True),
                sa.Column('training_date', sa.Date, nullable=True),
                sa.Column('training_provider', sa.String(255), nullable=True),
                sa.Column('document_url', sa.String(500), nullable=True),
                sa.Column('notes', sa.Text, nullable=True),
                sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            )

        elif table_name == 'inspections':
            op.create_table(
                'inspections',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('inspection_number', sa.String(50), unique=True, nullable=False, index=True),
                sa.Column('inspection_type', sa.String(100), nullable=False),
                sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
                sa.Column('property_address', sa.String(500), nullable=True),
                sa.Column('system_type', sa.String(100), nullable=True),
                sa.Column('system_age_years', sa.Integer, nullable=True),
                sa.Column('tank_size_gallons', sa.Integer, nullable=True),
                sa.Column('scheduled_date', sa.Date, nullable=True, index=True),
                sa.Column('completed_date', sa.Date, nullable=True),
                sa.Column('technician_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
                sa.Column('technician_name', sa.String(255), nullable=True),
                sa.Column('work_order_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
                sa.Column('status', sa.String(20), server_default='pending'),
                sa.Column('result', sa.String(20), nullable=True),
                sa.Column('overall_condition', sa.String(20), nullable=True),
                sa.Column('checklist', postgresql.JSON, nullable=True),
                sa.Column('sludge_depth_inches', sa.Float, nullable=True),
                sa.Column('scum_depth_inches', sa.Float, nullable=True),
                sa.Column('liquid_depth_inches', sa.Float, nullable=True),
                sa.Column('requires_followup', sa.Boolean, server_default='false'),
                sa.Column('followup_due_date', sa.Date, nullable=True),
                sa.Column('violations_found', postgresql.JSON, nullable=True),
                sa.Column('corrective_actions', sa.Text, nullable=True),
                sa.Column('county', sa.String(100), nullable=True),
                sa.Column('permit_number', sa.String(100), nullable=True),
                sa.Column('filed_with_county', sa.Boolean, server_default='false'),
                sa.Column('county_filing_date', sa.Date, nullable=True),
                sa.Column('photos', postgresql.JSON, nullable=True),
                sa.Column('report_url', sa.String(500), nullable=True),
                sa.Column('notes', sa.Text, nullable=True),
                sa.Column('inspection_fee', sa.Float, nullable=True),
                sa.Column('fee_collected', sa.Boolean, server_default='false'),
                sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            )

        elif table_name == 'service_intervals':
            op.create_table(
                'service_intervals',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('name', sa.String(255), nullable=False),
                sa.Column('description', sa.Text, nullable=True),
                sa.Column('service_type', sa.String(50), nullable=False),
                sa.Column('interval_months', sa.Integer, nullable=False),
                sa.Column('reminder_days_before', postgresql.JSON, server_default='[30, 14, 7]'),
                sa.Column('is_active', sa.Boolean, server_default='true'),
                sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            )

        elif table_name == 'customer_service_schedules':
            op.create_table(
                'customer_service_schedules',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
                sa.Column('service_interval_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
                sa.Column('last_service_date', sa.Date, nullable=True),
                sa.Column('next_due_date', sa.Date, nullable=False, index=True),
                sa.Column('status', sa.String(30), server_default='upcoming', index=True),
                sa.Column('scheduled_work_order_id', sa.String(36), nullable=True, index=True),
                sa.Column('reminder_sent', sa.Boolean, server_default='false'),
                sa.Column('last_reminder_sent_at', sa.DateTime(timezone=True), nullable=True),
                sa.Column('notes', sa.Text, nullable=True),
                sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            )
            # Add FK constraints after all tables are created

        elif table_name == 'service_reminders':
            op.create_table(
                'service_reminders',
                sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
                sa.Column('schedule_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
                sa.Column('customer_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
                sa.Column('reminder_type', sa.String(20), nullable=False),
                sa.Column('days_before_due', sa.Integer, nullable=True),
                sa.Column('status', sa.String(20), server_default='sent'),
                sa.Column('error_message', sa.Text, nullable=True),
                sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True),
                sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
                sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
            )
            # FK constraints will be added after all tables exist


    # Add FK constraints after all tables are created
    if conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'customer_service_schedules')"
    )).scalar():
        try:
            op.create_foreign_key(
                'customer_service_schedules_customer_id_fkey',
                'customer_service_schedules', 'customers',
                ['customer_id'], ['id']
            )
            op.create_foreign_key(
                'customer_service_schedules_service_interval_id_fkey',
                'customer_service_schedules', 'service_intervals',
                ['service_interval_id'], ['id']
            )
        except Exception:
            pass  # FK may already exist

    if conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'service_reminders')"
    )).scalar():
        try:
            op.create_foreign_key(
                'service_reminders_schedule_id_fkey',
                'service_reminders', 'customer_service_schedules',
                ['schedule_id'], ['id']
            )
            op.create_foreign_key(
                'service_reminders_customer_id_fkey',
                'service_reminders', 'customers',
                ['customer_id'], ['id']
            )
        except Exception:
            pass  # FK may already exist


def downgrade() -> None:
    op.drop_table('service_reminders', if_exists=True)
    op.drop_table('customer_service_schedules', if_exists=True)
    op.drop_table('service_intervals', if_exists=True)
    op.drop_table('inspections', if_exists=True)
    op.drop_table('certifications', if_exists=True)
    op.drop_table('licenses', if_exists=True)
