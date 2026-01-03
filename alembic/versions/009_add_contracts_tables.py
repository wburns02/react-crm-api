"""Add contracts tables (contracts, contract_templates)

Revision ID: 009_add_contracts
Revises: 008_add_compliance
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009_add_contracts'
down_revision = '008_add_compliance'
branch_labels = None
depends_on = None


def upgrade():
    # Create contract_templates table first (referenced by contracts)
    op.create_table(
        'contract_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('contract_type', sa.String(50), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('terms_and_conditions', sa.Text, nullable=True),
        sa.Column('default_duration_months', sa.Integer, default=12),
        sa.Column('default_billing_frequency', sa.String(20), default='monthly'),
        sa.Column('default_payment_terms', sa.String(100), nullable=True),
        sa.Column('default_auto_renew', sa.Boolean, default=False),
        sa.Column('default_services', postgresql.JSON, nullable=True),
        sa.Column('base_price', sa.Float, nullable=True),
        sa.Column('pricing_notes', sa.Text, nullable=True),
        sa.Column('variables', postgresql.JSON, nullable=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('version', sa.Integer, default=1),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create contracts table
    op.create_table(
        'contracts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('contract_number', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('contract_type', sa.String(50), nullable=False),
        sa.Column('customer_id', sa.Integer, nullable=False, index=True),
        sa.Column('customer_name', sa.String(255), nullable=True),
        sa.Column('template_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=False, index=True),
        sa.Column('auto_renew', sa.Boolean, default=False),
        sa.Column('renewal_terms', sa.Text, nullable=True),
        sa.Column('total_value', sa.Float, nullable=True),
        sa.Column('billing_frequency', sa.String(20), default='monthly'),
        sa.Column('payment_terms', sa.String(100), nullable=True),
        sa.Column('services_included', postgresql.JSON, nullable=True),
        sa.Column('covered_properties', postgresql.JSON, nullable=True),
        sa.Column('coverage_details', sa.Text, nullable=True),
        sa.Column('status', sa.String(20), default='draft'),
        sa.Column('requires_signature', sa.Boolean, default=True),
        sa.Column('customer_signed', sa.Boolean, default=False),
        sa.Column('customer_signed_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('company_signed', sa.Boolean, default=False),
        sa.Column('company_signed_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('signature_request_id', sa.String(36), nullable=True),
        sa.Column('document_url', sa.String(500), nullable=True),
        sa.Column('signed_document_url', sa.String(500), nullable=True),
        sa.Column('terms_and_conditions', sa.Text, nullable=True),
        sa.Column('special_terms', sa.Text, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('internal_notes', sa.Text, nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade():
    op.drop_table('contracts')
    op.drop_table('contract_templates')
