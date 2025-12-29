"""Add technicians and invoices tables

Revision ID: 001_add_technicians_invoices
Revises:
Create Date: 2024-12-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_add_technicians_invoices'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create technicians and invoices tables."""

    # Create technicians table
    op.create_table(
        'technicians',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
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
        # Skills
        sa.Column('skills', sa.JSON(), default=list),
        # Vehicle info
        sa.Column('assigned_vehicle', sa.String(100)),
        sa.Column('vehicle_capacity_gallons', sa.Float()),
        # Licensing
        sa.Column('license_number', sa.String(100)),
        sa.Column('license_expiry', sa.String(20)),
        # Payroll
        sa.Column('hourly_rate', sa.Float()),
        # Notes
        sa.Column('notes', sa.Text()),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('invoice_number', sa.String(50), unique=True, index=True, nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False, index=True),
        sa.Column('work_order_id', sa.Integer(), sa.ForeignKey('work_orders.id'), nullable=True, index=True),
        sa.Column('status', sa.Enum('draft', 'sent', 'paid', 'overdue', 'void', name='invoice_status'), default='draft', nullable=False),
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
    op.drop_table('invoices')
    op.drop_table('technicians')
    op.execute("DROP TYPE IF EXISTS invoice_status")
