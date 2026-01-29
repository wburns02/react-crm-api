"""Add missing pay_type and salary_amount columns to technician_pay_rates

Migration 025 was supposed to add these but may not have run.
This migration is idempotent - it checks if columns exist first.

Revision ID: 031_fix_pay_rates_columns
Revises: 030_fix_pay_rates_unique_constraint
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '031_fix_pay_rates_columns'
down_revision = '030_fix_pay_rates_unique_constraint'
branch_labels = None
depends_on = None


def column_exists(table_name, column_name):
    """Check if a column exists in a table."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # Add pay_type column if missing
    if not column_exists('technician_pay_rates', 'pay_type'):
        op.add_column('technician_pay_rates', sa.Column('pay_type', sa.String(20), server_default='hourly', nullable=False))
        print("Added pay_type column to technician_pay_rates")
    else:
        print("pay_type column already exists")

    # Add salary_amount column if missing
    if not column_exists('technician_pay_rates', 'salary_amount'):
        op.add_column('technician_pay_rates', sa.Column('salary_amount', sa.Float(), nullable=True))
        print("Added salary_amount column to technician_pay_rates")
    else:
        print("salary_amount column already exists")

    # Make hourly_rate nullable (for salary employees)
    # Note: This is idempotent - if already nullable, this is a no-op
    try:
        op.alter_column('technician_pay_rates', 'hourly_rate',
                        existing_type=sa.Float(),
                        nullable=True)
        print("Made hourly_rate nullable")
    except Exception as e:
        print(f"Note: hourly_rate alter column: {e}")


def downgrade() -> None:
    # These columns should be kept even on downgrade since
    # the model expects them. Only downgrade if necessary.
    pass
