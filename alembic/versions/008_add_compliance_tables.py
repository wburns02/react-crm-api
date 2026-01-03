"""Add compliance tables (licenses, certifications, inspections)

Revision ID: 008_add_compliance
Revises: 007_add_call_dispositions
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008_add_compliance'
down_revision = '007_add_call_dispositions'
branch_labels = None
depends_on = None


def upgrade():
    # Create licenses table
    op.create_table(
        'licenses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('license_number', sa.String(100), nullable=False, index=True),
        sa.Column('license_type', sa.String(100), nullable=False),
        sa.Column('issuing_authority', sa.String(255), nullable=True),
        sa.Column('issuing_state', sa.String(2), nullable=True),
        sa.Column('holder_type', sa.String(20), nullable=False, default='business'),
        sa.Column('holder_id', sa.String(36), nullable=True, index=True),
        sa.Column('holder_name', sa.String(255), nullable=True),
        sa.Column('issue_date', sa.Date, nullable=True),
        sa.Column('expiry_date', sa.Date, nullable=False, index=True),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('renewal_reminder_sent', sa.Boolean, default=False),
        sa.Column('renewal_reminder_date', sa.Date, nullable=True),
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create certifications table
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
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('renewal_reminder_sent', sa.Boolean, default=False),
        sa.Column('requires_renewal', sa.Boolean, default=True),
        sa.Column('renewal_interval_months', sa.Integer, nullable=True),
        sa.Column('training_hours', sa.Integer, nullable=True),
        sa.Column('training_date', sa.Date, nullable=True),
        sa.Column('training_provider', sa.String(255), nullable=True),
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create inspections table
    op.create_table(
        'inspections',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('inspection_number', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('inspection_type', sa.String(100), nullable=False),
        sa.Column('customer_id', sa.Integer, nullable=False, index=True),
        sa.Column('property_address', sa.String(500), nullable=True),
        sa.Column('system_type', sa.String(100), nullable=True),
        sa.Column('system_age_years', sa.Integer, nullable=True),
        sa.Column('tank_size_gallons', sa.Integer, nullable=True),
        sa.Column('scheduled_date', sa.Date, nullable=True, index=True),
        sa.Column('completed_date', sa.Date, nullable=True),
        sa.Column('technician_id', sa.String(36), nullable=True, index=True),
        sa.Column('technician_name', sa.String(255), nullable=True),
        sa.Column('work_order_id', sa.String(36), nullable=True, index=True),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('result', sa.String(20), nullable=True),
        sa.Column('overall_condition', sa.String(20), nullable=True),
        sa.Column('checklist', postgresql.JSON, nullable=True),
        sa.Column('sludge_depth_inches', sa.Float, nullable=True),
        sa.Column('scum_depth_inches', sa.Float, nullable=True),
        sa.Column('liquid_depth_inches', sa.Float, nullable=True),
        sa.Column('requires_followup', sa.Boolean, default=False),
        sa.Column('followup_due_date', sa.Date, nullable=True),
        sa.Column('violations_found', postgresql.JSON, nullable=True),
        sa.Column('corrective_actions', sa.Text, nullable=True),
        sa.Column('county', sa.String(100), nullable=True),
        sa.Column('permit_number', sa.String(100), nullable=True),
        sa.Column('filed_with_county', sa.Boolean, default=False),
        sa.Column('county_filing_date', sa.Date, nullable=True),
        sa.Column('photos', postgresql.JSON, nullable=True),
        sa.Column('report_url', sa.String(500), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('inspection_fee', sa.Float, nullable=True),
        sa.Column('fee_collected', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade():
    op.drop_table('inspections')
    op.drop_table('certifications')
    op.drop_table('licenses')
