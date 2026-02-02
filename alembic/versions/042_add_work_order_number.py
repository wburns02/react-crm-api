"""Add work_order_number column to work_orders table

This migration adds the work_order_number column that provides
human-readable work order numbers in WO-NNNNNN format.

Previously this was handled by a runtime SQL workaround in main.py.
This migration makes the schema change permanent.

Revision ID: 042_work_order_number
Revises: 041_add_payment_invoice_fields
Create Date: 2026-02-02
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision = "042_work_order_number"
down_revision = "041_add_payment_invoice_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add work_order_number column and backfill existing rows."""
    conn = op.get_bind()

    # Check if column already exists (idempotent)
    result = conn.execute(
        sa.text("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'work_orders' AND column_name = 'work_order_number'
            )
        """)
    )
    column_exists = result.scalar()

    if not column_exists:
        # Add the column
        op.add_column(
            "work_orders",
            sa.Column("work_order_number", sa.String(20), nullable=True),
        )

        # Backfill existing work orders with sequential numbers
        conn.execute(
            sa.text("""
                WITH numbered AS (
                    SELECT id, ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) as rn
                    FROM work_orders
                    WHERE work_order_number IS NULL
                )
                UPDATE work_orders wo
                SET work_order_number = 'WO-' || LPAD(n.rn::text, 6, '0')
                FROM numbered n
                WHERE wo.id = n.id
            """)
        )

        # Create unique index
        op.create_index(
            "ix_work_orders_number",
            "work_orders",
            ["work_order_number"],
            unique=True,
        )


def downgrade() -> None:
    """Remove work_order_number column."""
    op.drop_index("ix_work_orders_number", table_name="work_orders")
    op.drop_column("work_orders", "work_order_number")
