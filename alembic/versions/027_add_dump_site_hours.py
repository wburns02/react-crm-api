"""Add hours_of_operation to dump_sites

Revision ID: 027_add_dump_site_hours
Revises: 026_add_commission_auto_calc
Create Date: 2026-01-29

Adds hours_of_operation column to dump_sites table for storing
operating hours (e.g., "Mon-Fri 7AM-5PM", "24/7")

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '027_add_dump_site_hours'
down_revision = '026_add_commission_auto_calc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('dump_sites', sa.Column('hours_of_operation', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('dump_sites', 'hours_of_operation')
