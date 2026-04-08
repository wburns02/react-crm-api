"""Add county column to customers table

Revision ID: 094
Revises: 093
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("county", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "county")
