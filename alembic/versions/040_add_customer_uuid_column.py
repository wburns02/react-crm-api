"""Add customer_uuid column for FK optimization

This migration adds a UUID column to customers that stores the deterministic
UUID generated from the integer ID. This enables efficient joins with the
invoices table which stores customer_id as UUID.

Revision ID: 040_add_customer_uuid
Revises: 039_add_commission_dump_site_columns
Create Date: 2026-02-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid


# revision identifiers, used by Alembic
revision = "040_add_customer_uuid"
down_revision = "039_add_commission_dump_site_columns"
branch_labels = None
depends_on = None

# Namespace for deterministic UUID generation (must match invoices.py)
CUSTOMER_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def upgrade() -> None:
    # Add customer_uuid column
    op.add_column(
        "customers",
        sa.Column("customer_uuid", UUID(as_uuid=True), nullable=True),
    )

    # Create index for efficient lookups
    op.create_index(
        "ix_customers_customer_uuid",
        "customers",
        ["customer_uuid"],
        unique=True,
    )

    # Populate the column with deterministic UUIDs
    # Using raw SQL for efficiency
    connection = op.get_bind()

    # Get all customers and update their UUIDs
    customers = connection.execute(sa.text("SELECT id FROM customers")).fetchall()

    for (customer_id,) in customers:
        customer_uuid = uuid.uuid5(CUSTOMER_UUID_NAMESPACE, str(customer_id))
        connection.execute(
            sa.text("UPDATE customers SET customer_uuid = :uuid WHERE id = :id"),
            {"uuid": str(customer_uuid), "id": customer_id},
        )


def downgrade() -> None:
    op.drop_index("ix_customers_customer_uuid", table_name="customers")
    op.drop_column("customers", "customer_uuid")
