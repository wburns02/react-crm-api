"""Add missing database indexes for multi-tenant filtering and common queries.

Revision ID: 070
Revises: 069
Create Date: 2026-02-24
"""
from alembic import op


revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Multi-tenant entity_id indexes (used on nearly every query)
    op.create_index("ix_customers_entity_id", "customers", ["entity_id"], if_not_exists=True)
    op.create_index("ix_work_orders_entity_id", "work_orders", ["entity_id"], if_not_exists=True)
    op.create_index("ix_payments_entity_id", "payments", ["entity_id"], if_not_exists=True)

    # Work order date-range + status queries
    op.create_index(
        "ix_work_orders_scheduled_date_status",
        "work_orders",
        ["scheduled_date", "status"],
        if_not_exists=True,
    )

    # Payment FK lookup
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"], if_not_exists=True)

    # Payroll / commission time-series
    op.create_index("ix_time_entries_payroll_period_id", "time_entries", ["payroll_period_id"], if_not_exists=True)
    op.create_index("ix_commissions_earned_date", "commissions", ["earned_date"], if_not_exists=True)

    # User activity log — user lookups by date
    op.create_index("ix_user_activity_log_user_email", "user_activity_log", ["user_email", "created_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_user_activity_log_user_email", table_name="user_activity_log", if_exists=True)
    op.drop_index("ix_commissions_earned_date", table_name="commissions", if_exists=True)
    op.drop_index("ix_time_entries_payroll_period_id", table_name="time_entries", if_exists=True)
    op.drop_index("ix_payments_invoice_id", table_name="payments", if_exists=True)
    op.drop_index("ix_work_orders_scheduled_date_status", table_name="work_orders", if_exists=True)
    op.drop_index("ix_payments_entity_id", table_name="payments", if_exists=True)
    op.drop_index("ix_work_orders_entity_id", table_name="work_orders", if_exists=True)
    op.drop_index("ix_customers_entity_id", table_name="customers", if_exists=True)
