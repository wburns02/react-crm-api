"""Add job_costs table for job costing

Revision ID: 010_add_job_costs
Revises: 009_add_contracts
Create Date: 2025-01-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010_add_job_costs'
down_revision = '009_add_contracts'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'job_costs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('work_order_id', sa.String(36), nullable=False, index=True),
        sa.Column('cost_type', sa.String(50), nullable=False),
        sa.Column('category', sa.String(100), nullable=True),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('quantity', sa.Float, default=1.0),
        sa.Column('unit', sa.String(20), default='each'),
        sa.Column('unit_cost', sa.Float, nullable=False),
        sa.Column('total_cost', sa.Float, nullable=False),
        sa.Column('markup_percent', sa.Float, default=0.0),
        sa.Column('billable_amount', sa.Float, nullable=True),
        sa.Column('technician_id', sa.String(36), nullable=True, index=True),
        sa.Column('technician_name', sa.String(255), nullable=True),
        sa.Column('cost_date', sa.Date, nullable=False, index=True),
        sa.Column('is_billable', sa.Boolean, default=True),
        sa.Column('is_billed', sa.Boolean, default=False),
        sa.Column('invoice_id', sa.String(36), nullable=True),
        sa.Column('vendor_name', sa.String(255), nullable=True),
        sa.Column('vendor_invoice', sa.String(100), nullable=True),
        sa.Column('receipt_url', sa.String(500), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )


def downgrade():
    op.drop_table('job_costs')
