"""Remove unique constraint from technician_pay_rates.technician_id

The unique constraint prevents creating pay rate history for technicians.
A technician should be able to have multiple pay rate records (active + historical).

Revision ID: 030_fix_pay_rates_unique_constraint
Revises: 029_create_bookings_table
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '030_fix_pay_rates_unique_constraint'
down_revision = '029_create_bookings_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the unique constraint on technician_id
    # This allows multiple pay rate records per technician (for rate history)

    # First, try to drop the unique constraint if it exists as a named constraint
    try:
        op.drop_constraint('technician_pay_rates_technician_id_key', 'technician_pay_rates', type_='unique')
        print("Dropped unique constraint 'technician_pay_rates_technician_id_key'")
    except Exception as e:
        print(f"Constraint not found or already removed: {e}")

    # Also try dropping by the auto-generated index name
    try:
        op.drop_index('ix_technician_pay_rates_technician_id', table_name='technician_pay_rates')
        print("Dropped index 'ix_technician_pay_rates_technician_id'")
    except Exception as e:
        print(f"Index not found: {e}")

    # Create a non-unique index for performance
    op.create_index(
        'ix_technician_pay_rates_technician_id_active',
        'technician_pay_rates',
        ['technician_id', 'is_active'],
        unique=False
    )
    print("Created composite index on (technician_id, is_active)")


def downgrade() -> None:
    # This downgrade is destructive - it may fail if duplicate technician_ids exist
    op.drop_index('ix_technician_pay_rates_technician_id_active', table_name='technician_pay_rates')
    op.create_index('ix_technician_pay_rates_technician_id', 'technician_pay_rates', ['technician_id'], unique=True)
