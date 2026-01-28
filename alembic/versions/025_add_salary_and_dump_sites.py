"""Add salary pay type and dump sites

Revision ID: 025_add_salary_and_dump_sites
Revises: 024_add_activities_created_by
Create Date: 2026-01-28

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '025_add_salary_and_dump_sites'
down_revision = '024_add_activities_created_by'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add salary fields to technician_pay_rates table
    op.add_column('technician_pay_rates', sa.Column('pay_type', sa.String(20), server_default='hourly', nullable=False))
    op.add_column('technician_pay_rates', sa.Column('salary_amount', sa.Float(), nullable=True))

    # Make hourly_rate nullable for salary employees
    op.alter_column('technician_pay_rates', 'hourly_rate',
                    existing_type=sa.Float(),
                    nullable=True)

    # 2. Create dump_sites table
    op.create_table('dump_sites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('address_line1', sa.String(255), nullable=True),
        sa.Column('address_city', sa.String(100), nullable=True),
        sa.Column('address_state', sa.String(2), nullable=False),
        sa.Column('address_postal_code', sa.String(20), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('fee_per_gallon', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('contact_name', sa.String(100), nullable=True),
        sa.Column('contact_phone', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dump_sites_id'), 'dump_sites', ['id'], unique=False)
    op.create_index(op.f('ix_dump_sites_address_state'), 'dump_sites', ['address_state'], unique=False)

    # 3. Seed initial dump sites with state-specific fees
    op.execute("""
        INSERT INTO dump_sites (id, name, address_state, address_city, fee_per_gallon, is_active)
        VALUES
            (gen_random_uuid(), 'Texas Disposal Facility', 'TX', 'Austin', 0.07, true),
            (gen_random_uuid(), 'Dallas Waste Management', 'TX', 'Dallas', 0.07, true),
            (gen_random_uuid(), 'Houston Septic Disposal', 'TX', 'Houston', 0.07, true),
            (gen_random_uuid(), 'SC Waste Management', 'SC', 'Charleston', 0.10, true),
            (gen_random_uuid(), 'Columbia Disposal', 'SC', 'Columbia', 0.10, true),
            (gen_random_uuid(), 'TN Septic Disposal', 'TN', 'Nashville', 0.12, true),
            (gen_random_uuid(), 'Memphis Waste Facility', 'TN', 'Memphis', 0.12, true)
    """)

    # 4. Add pumping fields to work_orders table
    op.add_column('work_orders', sa.Column('gallons_pumped', sa.Integer(), nullable=True))
    op.add_column('work_orders', sa.Column('dump_site_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('work_orders', sa.Column('dump_fee', sa.Float(), nullable=True))

    # Add foreign key constraint for dump_site_id
    op.create_foreign_key(
        'fk_work_orders_dump_site',
        'work_orders', 'dump_sites',
        ['dump_site_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    # Remove foreign key and pumping columns from work_orders
    op.drop_constraint('fk_work_orders_dump_site', 'work_orders', type_='foreignkey')
    op.drop_column('work_orders', 'dump_fee')
    op.drop_column('work_orders', 'dump_site_id')
    op.drop_column('work_orders', 'gallons_pumped')

    # Drop dump_sites table
    op.drop_index(op.f('ix_dump_sites_address_state'), table_name='dump_sites')
    op.drop_index(op.f('ix_dump_sites_id'), table_name='dump_sites')
    op.drop_table('dump_sites')

    # Revert hourly_rate to non-nullable
    op.alter_column('technician_pay_rates', 'hourly_rate',
                    existing_type=sa.Float(),
                    nullable=False)

    # Remove salary fields from technician_pay_rates
    op.drop_column('technician_pay_rates', 'salary_amount')
    op.drop_column('technician_pay_rates', 'pay_type')
