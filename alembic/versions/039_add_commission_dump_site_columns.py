"""Add commission auto-calculation columns if missing

Revision ID: 039_add_commission_dump_site_columns
Revises: 038_add_mfa_tables
Create Date: 2026-01-30

Adds missing columns to commissions table for auto-calculation.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '039_add_commission_dump_site_columns'
down_revision = '038_add_mfa_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Check which columns exist
    result = conn.execute(sa.text("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'commissions'
    """))
    existing_columns = {row[0] for row in result}
    
    # Add missing columns
    columns_to_add = [
        ('dump_site_id', postgresql.UUID(as_uuid=True), True),
        ('job_type', sa.String(50), True),
        ('gallons_pumped', sa.Integer(), True),
        ('dump_fee_per_gallon', sa.Float(), True),
        ('dump_fee_amount', sa.Float(), True),
        ('commissionable_amount', sa.Float(), True),
    ]
    
    for col_name, col_type, nullable in columns_to_add:
        if col_name not in existing_columns:
            op.add_column('commissions', sa.Column(col_name, col_type, nullable=nullable))
            print(f"Added column: {col_name}")
        else:
            print(f"Column already exists: {col_name}")
    
    # Add index on job_type if not exists
    try:
        op.create_index(op.f('ix_commissions_job_type'), 'commissions', ['job_type'], unique=False)
        print("Created index: ix_commissions_job_type")
    except Exception as e:
        print(f"Index may already exist: {e}")


def downgrade() -> None:
    # Optional - only remove what we added
    pass
