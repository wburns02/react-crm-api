"""Add owner_phone and owner_email to septic_permits.

Revision ID: 085
Revises: 084
Create Date: 2026-03-04
"""
from alembic import op
import sqlalchemy as sa

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("septic_permits", sa.Column("owner_phone", sa.String(50), nullable=True))
    op.add_column("septic_permits", sa.Column("owner_email", sa.String(255), nullable=True))
    op.create_index("idx_septic_permits_owner_phone", "septic_permits", ["owner_phone"], postgresql_where=sa.text("owner_phone IS NOT NULL"))
    op.create_index("idx_septic_permits_owner_email", "septic_permits", ["owner_email"], postgresql_where=sa.text("owner_email IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("idx_septic_permits_owner_email", table_name="septic_permits")
    op.drop_index("idx_septic_permits_owner_phone", table_name="septic_permits")
    op.drop_column("septic_permits", "owner_email")
    op.drop_column("septic_permits", "owner_phone")
