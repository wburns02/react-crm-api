"""Add indexes for frequently filtered/sorted columns on customers and work_orders.

Performance audit identified ILIKE searches on first_name/last_name, WHERE
filters on prospect_stage, customer_type, job_type, priority, status, and
ORDER BY on created_at and scheduled_date that were missing dedicated indexes.

Revision ID: 081
Revises: 080
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── customers table ──────────────────────────────────────────────────

    # Individual B-tree indexes on first_name / last_name for ILIKE queries.
    # (The existing GIN trigram index covers concatenated full-name search,
    #  but simple ILIKE on each column benefits from a standard B-tree.)
    op.create_index(
        "ix_customers_first_name",
        "customers",
        ["first_name"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_customers_last_name",
        "customers",
        ["last_name"],
        if_not_exists=True,
    )

    # WHERE filters on prospect_stage and customer_type
    op.create_index(
        "ix_customers_prospect_stage",
        "customers",
        ["prospect_stage"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_customers_customer_type",
        "customers",
        ["customer_type"],
        if_not_exists=True,
    )

    # ORDER BY created_at DESC (list pages, dashboards)
    op.create_index(
        "ix_customers_created_at_desc",
        "customers",
        [sa.text("created_at DESC")],
        if_not_exists=True,
    )

    # ── work_orders table ────────────────────────────────────────────────

    # WHERE filters on job_type, priority, status (individual indexes)
    op.create_index(
        "ix_work_orders_job_type",
        "work_orders",
        ["job_type"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_work_orders_priority",
        "work_orders",
        ["priority"],
        if_not_exists=True,
    )
    # status is only part of composite indexes today; add a standalone index
    op.create_index(
        "ix_work_orders_status",
        "work_orders",
        ["status"],
        if_not_exists=True,
    )

    # Standalone scheduled_date index for single-column WHERE/ORDER BY
    # (existing composite indexes pair it with status, which doesn't help
    #  when the query only filters or sorts by date alone)
    op.create_index(
        "ix_work_orders_scheduled_date",
        "work_orders",
        ["scheduled_date"],
        if_not_exists=True,
    )


def downgrade() -> None:
    # work_orders
    op.drop_index("ix_work_orders_scheduled_date", table_name="work_orders", if_exists=True)
    op.drop_index("ix_work_orders_status", table_name="work_orders", if_exists=True)
    op.drop_index("ix_work_orders_priority", table_name="work_orders", if_exists=True)
    op.drop_index("ix_work_orders_job_type", table_name="work_orders", if_exists=True)

    # customers
    op.drop_index("ix_customers_created_at_desc", table_name="customers", if_exists=True)
    op.drop_index("ix_customers_customer_type", table_name="customers", if_exists=True)
    op.drop_index("ix_customers_prospect_stage", table_name="customers", if_exists=True)
    op.drop_index("ix_customers_last_name", table_name="customers", if_exists=True)
    op.drop_index("ix_customers_first_name", table_name="customers", if_exists=True)
