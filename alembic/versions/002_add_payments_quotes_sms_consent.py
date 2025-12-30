"""Add payments, quotes, and sms_consent tables

Revision ID: 002_add_payments_quotes_sms
Revises: 001_add_technicians_invoices
Create Date: 2024-12-30

Note: Using IF NOT EXISTS pattern to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '002_add_payments_quotes_sms'
down_revision = '001_add_technicians_invoices'
branch_labels = None
depends_on = None


def table_exists(conn, table_name):
    """Check if a table exists in the database."""
    result = conn.execute(text(
        f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
    ))
    return result.scalar()


def upgrade():
    """Create payments, quotes, and sms_consent tables if they don't exist."""
    conn = op.get_bind()

    # Create payments table
    if not table_exists(conn, 'payments'):
        op.create_table(
            'payments',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id'), nullable=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('payment_method', sa.String(50)),
            sa.Column('payment_date', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('reference_number', sa.String(100)),
            sa.Column('status', sa.String(20), default='completed'),
            sa.Column('notes', sa.Text()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )

    # Create quotes table
    if not table_exists(conn, 'quotes'):
        op.create_table(
            'quotes',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('quote_number', sa.String(50), unique=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('title', sa.String(255)),
            sa.Column('description', sa.Text()),
            sa.Column('line_items', sa.JSON(), default=list),
            sa.Column('subtotal', sa.Numeric(10, 2), default=0),
            sa.Column('tax_rate', sa.Numeric(5, 2), default=0),
            sa.Column('tax', sa.Numeric(10, 2), default=0),
            sa.Column('discount', sa.Numeric(10, 2), default=0),
            sa.Column('total', sa.Numeric(10, 2), default=0),
            sa.Column('status', sa.String(30), default='draft'),
            sa.Column('valid_until', sa.DateTime(timezone=True)),
            sa.Column('signature_data', sa.Text()),
            sa.Column('signed_at', sa.DateTime(timezone=True)),
            sa.Column('signed_by', sa.String(150)),
            sa.Column('approval_status', sa.String(30)),
            sa.Column('approved_by', sa.String(100)),
            sa.Column('approved_at', sa.DateTime(timezone=True)),
            sa.Column('converted_to_work_order_id', sa.String(36), sa.ForeignKey('work_orders.id'), nullable=True),
            sa.Column('converted_at', sa.DateTime(timezone=True)),
            sa.Column('notes', sa.Text()),
            sa.Column('terms', sa.Text()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
            sa.Column('sent_at', sa.DateTime(timezone=True)),
        )

    # Create sms_consent table
    if not table_exists(conn, 'sms_consent'):
        op.create_table(
            'sms_consent',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('phone_number', sa.String(20), nullable=False, index=True),
            sa.Column('consent_status', sa.String(20), default='pending'),
            sa.Column('consent_source', sa.String(50)),
            sa.Column('opt_in_timestamp', sa.DateTime(timezone=True)),
            sa.Column('opt_in_ip_address', sa.String(45)),
            sa.Column('double_opt_in_confirmed', sa.Boolean(), default=False),
            sa.Column('double_opt_in_timestamp', sa.DateTime(timezone=True)),
            sa.Column('opt_out_timestamp', sa.DateTime(timezone=True)),
            sa.Column('opt_out_reason', sa.String(100)),
            sa.Column('tcpa_disclosure_version', sa.String(20)),
            sa.Column('tcpa_disclosure_accepted', sa.Boolean(), default=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )

    # Create sms_consent_audit table
    if not table_exists(conn, 'sms_consent_audit'):
        op.create_table(
            'sms_consent_audit',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('consent_id', sa.Integer(), sa.ForeignKey('sms_consent.id'), nullable=False, index=True),
            sa.Column('action', sa.String(30), nullable=False),
            sa.Column('previous_status', sa.String(20)),
            sa.Column('new_status', sa.String(20)),
            sa.Column('ip_address', sa.String(45)),
            sa.Column('user_agent', sa.Text()),
            sa.Column('performed_by', sa.String(100)),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        )


def downgrade():
    """Drop payments, quotes, and sms_consent tables."""
    conn = op.get_bind()

    if table_exists(conn, 'sms_consent_audit'):
        op.drop_table('sms_consent_audit')

    if table_exists(conn, 'sms_consent'):
        op.drop_table('sms_consent')

    if table_exists(conn, 'quotes'):
        op.drop_table('quotes')

    if table_exists(conn, 'payments'):
        op.drop_table('payments')
