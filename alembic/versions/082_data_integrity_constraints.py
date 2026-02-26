"""Add data integrity constraints.

Adds missing FK constraints, ondelete clauses on existing FKs, CHECK
constraints on status/priority fields, NOT NULL where missing, and
creates the ai_suggestions table.

Revision ID: 082
Revises: 081
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_execute(sql: str) -> None:
    """Execute SQL, swallowing errors for idempotency."""
    try:
        op.execute(sql)
    except Exception:
        pass


def _replace_fk(
    table: str,
    column: str,
    ref_table: str,
    ref_column: str = "id",
    on_delete: str = "CASCADE",
    constraint_name: str | None = None,
) -> None:
    """Drop an FK constraint if it exists and recreate with the given ON DELETE."""
    name = constraint_name or f"{table}_{column}_fkey"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")
    op.execute(
        f"ALTER TABLE {table} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column}) "
        f"ON DELETE {on_delete};"
    )


def _drop_fk(table: str, column: str, constraint_name: str | None = None) -> None:
    """Drop an FK constraint if it exists (used in downgrade)."""
    name = constraint_name or f"{table}_{column}_fkey"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};")


def _add_check(table: str, constraint_name: str, expression: str) -> None:
    """Add a CHECK constraint if it does not already exist."""
    op.execute(
        f"DO $$ BEGIN "
        f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} CHECK ({expression}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
    )


def _drop_check(table: str, constraint_name: str) -> None:
    """Drop a CHECK constraint if it exists."""
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name};")


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ==================================================================
    # 1. Missing FK constraints
    # ==================================================================

    # payments.invoice_id -> invoices.id (SET NULL)
    # Column exists but has no FK constraint in the model definition.
    _replace_fk("payments", "invoice_id", "invoices", on_delete="SET NULL")

    # job_costs.work_order_id -> work_orders.id (CASCADE)
    # Column exists but has no FK constraint in the model definition.
    _replace_fk("job_costs", "work_order_id", "work_orders", on_delete="CASCADE")

    # ==================================================================
    # 2. Replace existing FKs with proper ondelete clauses
    # ==================================================================

    # --- work_orders ---
    _replace_fk("work_orders", "customer_id", "customers", on_delete="CASCADE")
    _replace_fk("work_orders", "technician_id", "technicians", on_delete="SET NULL")

    # --- invoices ---
    _replace_fk("invoices", "customer_id", "customers", on_delete="CASCADE")
    _replace_fk("invoices", "work_order_id", "work_orders", on_delete="SET NULL")

    # --- contracts ---
    _replace_fk("contracts", "customer_id", "customers", on_delete="CASCADE")

    # --- activities ---
    _replace_fk("activities", "customer_id", "customers", on_delete="CASCADE")

    # --- equipment ---
    _replace_fk("equipment", "customer_id", "customers", on_delete="CASCADE")

    # --- quotes ---
    _replace_fk("quotes", "customer_id", "customers", on_delete="CASCADE")

    # --- work_order_photos ---
    _replace_fk("work_order_photos", "work_order_id", "work_orders", on_delete="CASCADE")

    # --- bookings ---
    _replace_fk("bookings", "customer_id", "customers", on_delete="CASCADE")
    _replace_fk("bookings", "work_order_id", "work_orders", on_delete="SET NULL")

    # --- payments ---
    _replace_fk("payments", "customer_id", "customers", on_delete="SET NULL")
    _replace_fk("payments", "work_order_id", "work_orders", on_delete="SET NULL")

    # ==================================================================
    # 3. CHECK constraints on status/priority fields
    # ==================================================================

    # work_orders.status
    _add_check(
        "work_orders",
        "ck_work_orders_status",
        "status IN ('draft', 'scheduled', 'confirmed', 'enroute', 'on_site', "
        "'in_progress', 'completed', 'canceled', 'requires_followup')",
    )

    # work_orders.priority
    _add_check(
        "work_orders",
        "ck_work_orders_priority",
        "priority IN ('low', 'normal', 'high', 'urgent', 'emergency')",
    )

    # invoices.status
    _add_check(
        "invoices",
        "ck_invoices_status",
        "status IN ('draft', 'sent', 'paid', 'overdue', 'void', 'partial')",
    )

    # contracts.status
    _add_check(
        "contracts",
        "ck_contracts_status",
        "status IN ('draft', 'pending', 'active', 'expired', 'cancelled', 'renewed')",
    )

    # payments.status
    _add_check(
        "payments",
        "ck_payments_status",
        "status IN ('pending', 'completed', 'failed', 'refunded')",
    )

    # quotes.status
    _add_check(
        "quotes",
        "ck_quotes_status",
        "status IN ('draft', 'sent', 'viewed', 'accepted', 'rejected', 'expired', 'converted')",
    )

    # ==================================================================
    # 4. NOT NULL constraints where missing
    # ==================================================================

    # bookings.customer_id should be NOT NULL
    # First ensure there are no NULLs, then enforce.
    op.execute(
        "UPDATE bookings SET customer_id = '00000000-0000-0000-0000-000000000000' "
        "WHERE customer_id IS NULL;"
    )
    op.execute("ALTER TABLE bookings ALTER COLUMN customer_id SET NOT NULL;")

    # ==================================================================
    # 5. Create ai_suggestions table (missing from prior migrations)
    # ==================================================================

    op.execute("""
        CREATE TABLE IF NOT EXISTS ai_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            suggestion_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            target_segment VARCHAR(50),
            estimated_recipients INTEGER,
            estimated_revenue DOUBLE PRECISION,
            priority_score DOUBLE PRECISION,
            ai_rationale TEXT,
            suggested_subject VARCHAR(500),
            suggested_body TEXT,
            suggested_send_date TIMESTAMPTZ,
            status VARCHAR(20) DEFAULT 'pending',
            campaign_id UUID,
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ai_suggestions_id ON ai_suggestions (id);"
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # ==================================================================
    # 5. Drop ai_suggestions table
    # ==================================================================

    op.execute("DROP TABLE IF EXISTS ai_suggestions;")

    # ==================================================================
    # 4. Revert NOT NULL on bookings.customer_id
    # ==================================================================

    op.execute("ALTER TABLE bookings ALTER COLUMN customer_id DROP NOT NULL;")

    # ==================================================================
    # 3. Drop CHECK constraints
    # ==================================================================

    _drop_check("quotes", "ck_quotes_status")
    _drop_check("payments", "ck_payments_status")
    _drop_check("contracts", "ck_contracts_status")
    _drop_check("invoices", "ck_invoices_status")
    _drop_check("work_orders", "ck_work_orders_priority")
    _drop_check("work_orders", "ck_work_orders_status")

    # ==================================================================
    # 2. Restore FKs without ondelete clauses
    # ==================================================================

    # --- payments ---
    _drop_fk("payments", "work_order_id")
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT payments_work_order_id_fkey "
        "FOREIGN KEY (work_order_id) REFERENCES work_orders(id);"
    )
    _drop_fk("payments", "customer_id")
    op.execute(
        "ALTER TABLE payments ADD CONSTRAINT payments_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- bookings ---
    _drop_fk("bookings", "work_order_id")
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT bookings_work_order_id_fkey "
        "FOREIGN KEY (work_order_id) REFERENCES work_orders(id);"
    )
    _drop_fk("bookings", "customer_id")
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT bookings_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- work_order_photos ---
    _drop_fk("work_order_photos", "work_order_id")
    op.execute(
        "ALTER TABLE work_order_photos ADD CONSTRAINT work_order_photos_work_order_id_fkey "
        "FOREIGN KEY (work_order_id) REFERENCES work_orders(id);"
    )

    # --- quotes ---
    _drop_fk("quotes", "customer_id")
    op.execute(
        "ALTER TABLE quotes ADD CONSTRAINT quotes_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- equipment ---
    _drop_fk("equipment", "customer_id")
    op.execute(
        "ALTER TABLE equipment ADD CONSTRAINT equipment_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- activities ---
    _drop_fk("activities", "customer_id")
    op.execute(
        "ALTER TABLE activities ADD CONSTRAINT activities_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- contracts ---
    _drop_fk("contracts", "customer_id")
    op.execute(
        "ALTER TABLE contracts ADD CONSTRAINT contracts_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- invoices ---
    _drop_fk("invoices", "work_order_id")
    op.execute(
        "ALTER TABLE invoices ADD CONSTRAINT invoices_work_order_id_fkey "
        "FOREIGN KEY (work_order_id) REFERENCES work_orders(id);"
    )
    _drop_fk("invoices", "customer_id")
    op.execute(
        "ALTER TABLE invoices ADD CONSTRAINT invoices_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # --- work_orders ---
    _drop_fk("work_orders", "technician_id")
    op.execute(
        "ALTER TABLE work_orders ADD CONSTRAINT work_orders_technician_id_fkey "
        "FOREIGN KEY (technician_id) REFERENCES technicians(id);"
    )
    _drop_fk("work_orders", "customer_id")
    op.execute(
        "ALTER TABLE work_orders ADD CONSTRAINT work_orders_customer_id_fkey "
        "FOREIGN KEY (customer_id) REFERENCES customers(id);"
    )

    # ==================================================================
    # 1. Remove newly-added FK constraints
    # ==================================================================

    _drop_fk("job_costs", "work_order_id")
    _drop_fk("payments", "invoice_id")
