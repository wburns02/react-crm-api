"""Create dump_sites table standalone

Revision ID: 028_create_dump_sites
Revises: 027_add_dump_site_hours
Create Date: 2026-01-29

Creates the dump_sites table if it doesn't exist.
This is a safe migration that checks for table existence first.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '028_create_dump_sites'
down_revision = '027_add_dump_site_hours'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if dump_sites table already exists
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()

    if 'dump_sites' not in tables:
        # Create the table
        op.create_table('dump_sites',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
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
            sa.Column('hours_of_operation', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_dump_sites_id'), 'dump_sites', ['id'], unique=False)
        op.create_index(op.f('ix_dump_sites_address_state'), 'dump_sites', ['address_state'], unique=False)

        # Seed initial data
        op.execute("""
            INSERT INTO dump_sites (name, address_state, address_city, fee_per_gallon, is_active)
            VALUES
                ('Texas Disposal Facility', 'TX', 'Austin', 0.07, true),
                ('Dallas Waste Management', 'TX', 'Dallas', 0.07, true),
                ('Houston Septic Disposal', 'TX', 'Houston', 0.07, true),
                ('SC Waste Management', 'SC', 'Charleston', 0.10, true),
                ('Columbia Disposal', 'SC', 'Columbia', 0.10, true),
                ('TN Septic Disposal', 'TN', 'Nashville', 0.12, true),
                ('Memphis Waste Facility', 'TN', 'Memphis', 0.12, true)
        """)
    else:
        # Table exists, check if hours_of_operation column exists
        columns = [c['name'] for c in inspector.get_columns('dump_sites')]
        if 'hours_of_operation' not in columns:
            op.add_column('dump_sites', sa.Column('hours_of_operation', sa.String(255), nullable=True))


def downgrade() -> None:
    # This migration is idempotent, downgrade is a no-op
    pass
