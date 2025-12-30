"""Add technicians and invoices tables

Revision ID: 001_add_technicians_invoices
Revises:
Create Date: 2024-12-29

Note: Tables may already exist from Flask data import. Using raw SQL with
IF NOT EXISTS to make migration idempotent.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '001_add_technicians_invoices'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create technicians and invoices tables if they don't exist."""
    conn = op.get_bind()

    # Check if technicians table exists
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'technicians')"
    ))
    technicians_exists = result.scalar()

    if not technicians_exists:
        # Create technicians table - matching Flask schema with String(36) UUID id
        op.create_table(
            'technicians',
            sa.Column('id', sa.String(36), primary_key=True, index=True),
            sa.Column('first_name', sa.String(100), nullable=False),
            sa.Column('last_name', sa.String(100), nullable=False),
            sa.Column('email', sa.String(255), index=True),
            sa.Column('phone', sa.String(20)),
            sa.Column('employee_id', sa.String(50), unique=True, index=True),
            sa.Column('is_active', sa.Boolean(), default=True),
            # Home location
            sa.Column('home_region', sa.String(100)),
            sa.Column('home_address', sa.String(255)),
            sa.Column('home_city', sa.String(100)),
            sa.Column('home_state', sa.String(50)),
            sa.Column('home_postal_code', sa.String(20)),
            sa.Column('home_latitude', sa.Float()),
            sa.Column('home_longitude', sa.Float()),
            # Skills (ARRAY in Flask)
            sa.Column('skills', sa.ARRAY(sa.String())),
            # Vehicle info
            sa.Column('assigned_vehicle', sa.String(100)),
            sa.Column('vehicle_capacity_gallons', sa.Integer()),
            # Licensing
            sa.Column('license_number', sa.String(100)),
            sa.Column('license_expiry', sa.Date()),
            # Pay rates
            sa.Column('hourly_rate', sa.Float()),
            sa.Column('overtime_rate', sa.Numeric()),
            sa.Column('double_time_rate', sa.Numeric()),
            sa.Column('travel_rate', sa.Numeric()),
            sa.Column('pay_type', sa.String(50)),
            sa.Column('salary_amount', sa.Numeric()),
            # Work hours
            sa.Column('default_hours_per_week', sa.Numeric()),
            sa.Column('overtime_threshold', sa.Numeric()),
            # PTO
            sa.Column('pto_balance_hours', sa.Numeric()),
            sa.Column('pto_accrual_rate', sa.Numeric()),
            # Employment
            sa.Column('hire_date', sa.Date()),
            sa.Column('hired_date', sa.Date()),
            sa.Column('department', sa.String(100)),
            sa.Column('external_payroll_id', sa.String(100)),
            # Notes
            sa.Column('notes', sa.Text()),
            # Timestamps
            sa.Column('created_at', sa.DateTime()),
            sa.Column('updated_at', sa.DateTime()),
        )

    # Check if invoices table exists
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'invoices')"
    ))
    invoices_exists = result.scalar()

    if not invoices_exists:
        # Create invoices table - matching Flask schema with String(36) work_order_id
        op.create_table(
            'invoices',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('invoice_number', sa.String(50), unique=True, index=True, nullable=False),
            sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
            sa.Column('work_order_id', sa.String(36), sa.ForeignKey('work_orders.id'), nullable=True, index=True),
            sa.Column('status', sa.String(20), default='draft', nullable=False),
            # Line items
            sa.Column('line_items', sa.JSON(), default=list),
            # Totals
            sa.Column('subtotal', sa.Float(), default=0),
            sa.Column('tax_rate', sa.Float(), default=0),
            sa.Column('tax', sa.Float(), default=0),
            sa.Column('total', sa.Float(), default=0),
            # Dates
            sa.Column('due_date', sa.String(20)),
            sa.Column('paid_date', sa.String(20)),
            # Additional info
            sa.Column('notes', sa.Text()),
            sa.Column('terms', sa.Text()),
            # Timestamps
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        )


def downgrade():
    """Drop technicians and invoices tables."""
    conn = op.get_bind()

    # Check if tables exist before dropping
    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'invoices')"
    ))
    if result.scalar():
        op.drop_table('invoices')

    result = conn.execute(text(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'technicians')"
    ))
    if result.scalar():
        op.drop_table('technicians')
