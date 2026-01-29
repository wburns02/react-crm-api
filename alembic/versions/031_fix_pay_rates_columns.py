"""Add missing pay_type and salary_amount columns to technician_pay_rates

Migration 025 was supposed to add these but may not have run.
This migration is idempotent - it checks if columns exist first.

Revision ID: 031_fix_pay_rates_columns
Revises: 030_fix_pay_rates_unique_constraint
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '031_fix_pay_rates_columns'
down_revision = '030_fix_pay_rates_unique_constraint'
branch_labels = None
depends_on = None


def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table using raw SQL."""
    result = conn.execute(text(
        """SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        )"""
    ), {"table_name": table_name, "column_name": column_name})
    return result.scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # Add pay_type column if missing
    if not column_exists(conn, 'technician_pay_rates', 'pay_type'):
        op.add_column('technician_pay_rates', sa.Column('pay_type', sa.String(20), server_default='hourly', nullable=False))
        print("Added pay_type column to technician_pay_rates")
    else:
        print("pay_type column already exists")

    # Add salary_amount column if missing
    if not column_exists(conn, 'technician_pay_rates', 'salary_amount'):
        op.add_column('technician_pay_rates', sa.Column('salary_amount', sa.Float(), nullable=True))
        print("Added salary_amount column to technician_pay_rates")
    else:
        print("salary_amount column already exists")

    # Make hourly_rate nullable (for salary employees)
    # Check if it's already nullable
    result = conn.execute(text(
        """SELECT is_nullable FROM information_schema.columns
           WHERE table_name = 'technician_pay_rates' AND column_name = 'hourly_rate'"""
    ))
    row = result.fetchone()
    if row and row[0] == 'NO':
        op.alter_column('technician_pay_rates', 'hourly_rate',
                        existing_type=sa.Float(),
                        nullable=True)
        print("Made hourly_rate nullable")
    else:
        print("hourly_rate is already nullable")


def downgrade() -> None:
    # These columns should be kept even on downgrade since
    # the model expects them. Only downgrade if necessary.
    pass
