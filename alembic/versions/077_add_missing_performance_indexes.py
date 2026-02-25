"""add missing performance indexes

Revision ID: 077
Revises: 076
Create Date: 2026-02-25

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '077'
down_revision = '076'
branch_labels = None
depends_on = None


def upgrade():
    # Multi-tenant filtering (used on nearly every query)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_customers_entity_id ON customers(entity_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_work_orders_entity_id ON work_orders(entity_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_payments_entity_id ON payments(entity_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_invoices_entity_id ON invoices(entity_id)")
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_technicians_entity_id ON technicians(entity_id)")

    # Date-range work order queries (schedule page, dashboards)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_work_orders_scheduled_status ON work_orders(scheduled_date, status)")

    # Payment FK lookups
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_payments_invoice_id ON payments(invoice_id)")

    # Payroll/commission time series
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_time_entries_payroll_period ON time_entries(payroll_period_id)")

    # Work order customer lookups (used in cascade delete, customer detail)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_work_orders_customer_id ON work_orders(customer_id)")

    # Full-text customer search (GIN trigram)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_customers_name_trgm
        ON customers USING gin ((first_name || ' ' || last_name) gin_trgm_ops)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_customers_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_work_orders_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_payments_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_invoices_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_technicians_entity_id")
    op.execute("DROP INDEX IF EXISTS ix_work_orders_scheduled_status")
    op.execute("DROP INDEX IF EXISTS ix_payments_invoice_id")
    op.execute("DROP INDEX IF EXISTS ix_time_entries_payroll_period")
    op.execute("DROP INDEX IF EXISTS ix_work_orders_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_customers_name_trgm")
