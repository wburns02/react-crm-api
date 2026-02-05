"""Add inventory_transactions table for audit trail.

Revision ID: 045
Revises: 044
"""

from alembic import op
import sqlalchemy as sa

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("item_id", sa.String(36), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("adjustment", sa.Integer(), nullable=False),
        sa.Column("previous_quantity", sa.Integer(), nullable=False),
        sa.Column("new_quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.String(36), nullable=True),
        sa.Column("performed_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_inventory_transactions_item_id", "inventory_transactions", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_inventory_transactions_item_id")
    op.drop_table("inventory_transactions")
