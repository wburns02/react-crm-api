"""Add commission auto-calculation fields

Revision ID: 026_add_commission_auto_calc
Revises: 025_add_salary_and_dump_sites
Create Date: 2026-01-28

Adds fields to commissions table for automatic calculation:
- dump_site_id: Reference to dump site used for pumping jobs
- job_type: Type of job (pumping, repair, inspection, etc.)
- gallons_pumped: Number of gallons pumped (for pumping jobs)
- dump_fee_per_gallon: Rate at time of commission creation
- dump_fee_amount: Total dump fee (gallons × rate)
- commissionable_amount: Amount after dump fee deduction

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '026_add_commission_auto_calc'
down_revision = '025_add_salary_and_dump_sites'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auto-calculation fields to commissions table
    op.add_column('commissions', sa.Column('dump_site_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('commissions', sa.Column('job_type', sa.String(50), nullable=True))
    op.add_column('commissions', sa.Column('gallons_pumped', sa.Integer(), nullable=True))
    op.add_column('commissions', sa.Column('dump_fee_per_gallon', sa.Float(), nullable=True))
    op.add_column('commissions', sa.Column('dump_fee_amount', sa.Float(), nullable=True))
    op.add_column('commissions', sa.Column('commissionable_amount', sa.Float(), nullable=True))

    # Add foreign key constraint for dump_site_id
    op.create_foreign_key(
        'fk_commissions_dump_site',
        'commissions', 'dump_sites',
        ['dump_site_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create index on job_type for filtering
    op.create_index(op.f('ix_commissions_job_type'), 'commissions', ['job_type'], unique=False)


def downgrade() -> None:
    # Remove foreign key and auto-calc columns from commissions
    op.drop_index(op.f('ix_commissions_job_type'), table_name='commissions')
    op.drop_constraint('fk_commissions_dump_site', 'commissions', type_='foreignkey')
    op.drop_column('commissions', 'commissionable_amount')
    op.drop_column('commissions', 'dump_fee_amount')
    op.drop_column('commissions', 'dump_fee_per_gallon')
    op.drop_column('commissions', 'gallons_pumped')
    op.drop_column('commissions', 'job_type')
    op.drop_column('commissions', 'dump_site_id')
