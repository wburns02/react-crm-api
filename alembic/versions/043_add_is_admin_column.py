"""Add is_admin column to api_users table

This migration adds the is_admin column that RBAC expects.
Previously the code used getattr(user, "is_admin", False) as a fallback.

Revision ID: 043_add_is_admin_column
Revises: 042_add_work_order_number
Create Date: 2026-02-02
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "043_add_is_admin_column"
down_revision = "042_add_work_order_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_admin column with default False
    op.add_column(
        "api_users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )

    # Promote will@macseptic.com to admin
    op.execute("""
        UPDATE api_users
        SET is_admin = true
        WHERE email = 'will@macseptic.com';
    """)


def downgrade() -> None:
    op.drop_column("api_users", "is_admin")
