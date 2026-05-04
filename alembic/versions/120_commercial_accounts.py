"""commercial accounts: porta-potty job types + customer billing addr + parent/child.

Three changes for commercial-account support:

1. Adds three new values to `work_order_job_type_enum`:
   - `porta_potty_clean_pump`
   - `porta_potty_pickup`
   - `porta_potty_dropoff`

2. Adds billing-address columns to `customers` so a customer can have a
   billing address that differs from the service address:
   - `billing_address_line1`, `billing_address_line2`, `billing_city`,
     `billing_state`, `billing_postal_code` (all VARCHAR, nullable)
   - `use_separate_billing_address` BOOLEAN NOT NULL DEFAULT false

3. Adds parent/child relationships between customers (for parent
   commercial account → multiple sub-locations / billing children):
   - `parent_customer_id` UUID NULL, FK customers.id ON DELETE SET NULL
   - Index `ix_customers_parent_customer_id`

Revision ID: 120
Revises: 119
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "120"
down_revision = "119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add 3 enum values to work_order_job_type_enum.
    # Postgres 12+ supports ALTER TYPE ADD VALUE inside a transaction, but
    # only when the value does not already exist. The IF NOT EXISTS form is
    # safe regardless. We commit the surrounding transaction first to be
    # extra safe across PG versions, then reopen.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE work_order_job_type_enum ADD VALUE IF NOT EXISTS 'porta_potty_clean_pump'"
    )
    op.execute(
        "ALTER TYPE work_order_job_type_enum ADD VALUE IF NOT EXISTS 'porta_potty_pickup'"
    )
    op.execute(
        "ALTER TYPE work_order_job_type_enum ADD VALUE IF NOT EXISTS 'porta_potty_dropoff'"
    )
    op.execute("BEGIN")

    # 2) Billing-address columns on customers.
    op.add_column(
        "customers",
        sa.Column("billing_address_line1", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("billing_address_line2", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("billing_city", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("billing_state", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column("billing_postal_code", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "customers",
        sa.Column(
            "use_separate_billing_address",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # 3) Parent/child customer relationship.
    op.add_column(
        "customers",
        sa.Column(
            "parent_customer_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_customers_parent_customer_id_customers",
        "customers",
        "customers",
        ["parent_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_customers_parent_customer_id",
        "customers",
        ["parent_customer_id"],
    )


def downgrade() -> None:
    # Drop parent/child.
    op.drop_index("ix_customers_parent_customer_id", table_name="customers")
    op.drop_constraint(
        "fk_customers_parent_customer_id_customers",
        "customers",
        type_="foreignkey",
    )
    op.drop_column("customers", "parent_customer_id")

    # Drop billing-address columns.
    op.drop_column("customers", "use_separate_billing_address")
    op.drop_column("customers", "billing_postal_code")
    op.drop_column("customers", "billing_state")
    op.drop_column("customers", "billing_city")
    op.drop_column("customers", "billing_address_line2")
    op.drop_column("customers", "billing_address_line1")

    # Note: Postgres cannot reliably drop enum values once added.
    # The 3 porta_potty_* values stay in work_order_job_type_enum.
