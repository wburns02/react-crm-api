"""Add payment invoice_id and payment_date fields

Adds new columns needed for Stripe payment integration:
- invoice_id (UUID) - references invoices table
- payment_date (DateTime) - when payment completed

Revision ID: 041_add_payment_invoice_fields
Revises: 040_add_customer_uuid
Create Date: 2026-02-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic
revision = "041_add_payment_invoice_fields"
down_revision = "040_add_customer_uuid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add invoice_id column (UUID to match invoices.id)
    op.add_column(
        "payments",
        sa.Column("invoice_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    # Add payment_date column
    op.add_column(
        "payments",
        sa.Column("payment_date", sa.DateTime(), nullable=True),
    )

    # Make customer_id nullable (since we may only have invoice_id)
    op.alter_column(
        "payments",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_column("payments", "payment_date")
    op.drop_column("payments", "invoice_id")

    # Make customer_id required again
    op.alter_column(
        "payments",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
