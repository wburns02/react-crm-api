"""Add system_settings table for admin settings persistence.

Revision ID: 044
Revises: 043
"""

from alembic import op
import sqlalchemy as sa

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("settings_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category"),
    )
    op.create_index("ix_system_settings_category", "system_settings", ["category"])


def downgrade() -> None:
    op.drop_index("ix_system_settings_category")
    op.drop_table("system_settings")
