"""Convert Customer PK from Integer to UUID.

THE BIG ONE. Leverages migration 040's customer_uuid column (UUID5 deterministic values).
Converts all 16 dependent tables and finally enables Invoice FK constraint.

Revision ID: 049
Revises: 048
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None

CUSTOMER_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _table_exists(conn, table_name):
    return conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
    ), {"t": table_name}).scalar()


def _column_exists(conn, table_name, column_name):
    return conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c)"
    ), {"t": table_name, "c": column_name}).scalar()


def _drop_all_fks_referencing(conn, target_table):
    """Drop ALL foreign key constraints that reference the given table."""
    fks = conn.execute(sa.text("""
        SELECT tc.table_name, tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.referential_constraints rc ON tc.constraint_name = rc.constraint_name
        JOIN information_schema.table_constraints tc2 ON rc.unique_constraint_name = tc2.constraint_name
        WHERE tc2.table_name = :target AND tc.constraint_type = 'FOREIGN KEY'
    """), {"target": target_table}).fetchall()
    for table_name, constraint_name in fks:
        conn.execute(sa.text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'))
    return fks


def upgrade() -> None:
    conn = op.get_bind()

    # ══════════════════════════════════════════════════════════════════
    # PREREQUISITE CHECKS
    # ══════════════════════════════════════════════════════════════════

    # Verify customer_uuid column exists and is fully populated
    if not _column_exists(conn, "customers", "customer_uuid"):
        # Backfill customer_uuid from migration 040 if it hasn't run
        conn.execute(sa.text(
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS customer_uuid UUID"
        ))
        conn.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_customer_uuid "
            "ON customers(customer_uuid)"
        ))
        # Populate with UUID5 deterministic values
        rows = conn.execute(sa.text("SELECT id FROM customers")).fetchall()
        for (cid,) in rows:
            cuuid = uuid.uuid5(CUSTOMER_UUID_NAMESPACE, str(cid))
            conn.execute(sa.text(
                "UPDATE customers SET customer_uuid = :uuid WHERE id = :id"
            ), {"uuid": str(cuuid), "id": cid})

    # Ensure no NULLs in customer_uuid
    null_count = conn.execute(sa.text(
        "SELECT COUNT(*) FROM customers WHERE customer_uuid IS NULL"
    )).scalar()
    if null_count > 0:
        rows = conn.execute(sa.text(
            "SELECT id FROM customers WHERE customer_uuid IS NULL"
        )).fetchall()
        for (cid,) in rows:
            cuuid = uuid.uuid5(CUSTOMER_UUID_NAMESPACE, str(cid))
            conn.execute(sa.text(
                "UPDATE customers SET customer_uuid = :uuid WHERE id = :id"
            ), {"uuid": str(cuuid), "id": cid})

    # Verify invoice customer_ids match (critical for FK creation)
    orphans = 0
    if _table_exists(conn, "invoices"):
        orphans = conn.execute(sa.text(
            "SELECT COUNT(*) FROM invoices i "
            "LEFT JOIN customers c ON c.customer_uuid = i.customer_id "
            "WHERE c.customer_uuid IS NULL AND i.customer_id IS NOT NULL"
        )).scalar()
        if orphans > 0:
            import logging
            logging.getLogger(__name__).warning(
                f"Found {orphans} invoices with customer_ids not matching any customer_uuid. "
                f"Invoice FK constraint will not be created."
            )

    # ══════════════════════════════════════════════════════════════════
    # STEP 1: Add new UUID customer_id columns to all dependent tables
    # ══════════════════════════════════════════════════════════════════

    # Tables with Integer customer_id referencing customers.id
    dependent_tables = [
        "work_orders", "messages", "activities", "quotes", "tickets",
        "equipment", "bookings", "sms_consent", "customer_service_schedules",
        "service_reminders", "geofences", "customer_tracking_links",
        "payments", "contracts", "call_logs", "inspections",
    ]

    for table in dependent_tables:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "customer_id"):
            continue
        conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN customer_id_new UUID"))

    # ══════════════════════════════════════════════════════════════════
    # STEP 2: Backfill UUID customer_id via JOIN to customers
    # ══════════════════════════════════════════════════════════════════

    for table in dependent_tables:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "customer_id_new"):
            continue
        # Cast both sides to text for comparison since customer_id may be
        # Integer or VARCHAR depending on the table
        conn.execute(sa.text(
            f"UPDATE {table} t SET customer_id_new = c.customer_uuid "
            f"FROM customers c WHERE t.customer_id::text = c.id::text"
        ))

    # ══════════════════════════════════════════════════════════════════
    # STEP 3: Drop ALL FK constraints referencing customers (dynamic)
    # ══════════════════════════════════════════════════════════════════

    _drop_all_fks_referencing(conn, "customers")

    # ══════════════════════════════════════════════════════════════════
    # STEP 4: Swap Customer PK
    # ══════════════════════════════════════════════════════════════════

    # Drop old PK and rename columns
    conn.execute(sa.text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_pkey"))

    # Drop old indexes on id
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_id"))

    # Rename: id → old_int_id, customer_uuid → id
    conn.execute(sa.text("ALTER TABLE customers RENAME COLUMN id TO old_int_id"))
    conn.execute(sa.text("ALTER TABLE customers RENAME COLUMN customer_uuid TO id"))

    # Drop the unique index on customer_uuid (now named id)
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_customer_uuid"))

    # Add new PK
    conn.execute(sa.text("ALTER TABLE customers ADD PRIMARY KEY (id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_customers_id ON customers(id)"))

    # ══════════════════════════════════════════════════════════════════
    # STEP 5: Swap FK columns on all dependent tables
    # ══════════════════════════════════════════════════════════════════

    for table in dependent_tables:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "customer_id_new"):
            continue

        # Drop old Integer customer_id
        conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN customer_id"))
        # Rename new UUID column
        conn.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN customer_id_new TO customer_id"))
        # Create index
        conn.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_customer_id ON {table}(customer_id)"
        ))

    # ══════════════════════════════════════════════════════════════════
    # STEP 6: Re-create FK constraints for ALL dependent tables
    # ══════════════════════════════════════════════════════════════════

    for table in dependent_tables:
        if _table_exists(conn, table) and _column_exists(conn, table, "customer_id"):
            conn.execute(sa.text(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey "
                f"FOREIGN KEY (customer_id) REFERENCES customers(id)"
            ))

    # THE PAYOFF: Invoice FK constraint (was NEVER possible before!)
    if _table_exists(conn, "invoices") and orphans == 0:
        conn.execute(sa.text(
            "ALTER TABLE invoices ADD CONSTRAINT invoices_customer_id_fkey "
            "FOREIGN KEY (customer_id) REFERENCES customers(id)"
        ))


def downgrade() -> None:
    conn = op.get_bind()

    # ══════════════════════════════════════════════════════════════════
    # Reverse the Customer PK swap using preserved old_int_id
    # ══════════════════════════════════════════════════════════════════

    dependent_tables = [
        "work_orders", "messages", "activities", "quotes", "tickets",
        "equipment", "bookings", "sms_consent", "customer_service_schedules",
        "service_reminders", "geofences", "customer_tracking_links",
        "payments", "contracts", "call_logs", "inspections",
    ]

    # Drop all FK constraints
    all_fk_tables = dependent_tables + ["invoices"]
    for table in all_fk_tables:
        if _table_exists(conn, table):
            conn.execute(sa.text(
                f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_customer_id_fkey"
            ))

    # Reverse Customer PK swap
    conn.execute(sa.text("ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_pkey"))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_customers_id"))
    conn.execute(sa.text("ALTER TABLE customers RENAME COLUMN id TO customer_uuid"))
    conn.execute(sa.text("ALTER TABLE customers RENAME COLUMN old_int_id TO id"))
    conn.execute(sa.text("ALTER TABLE customers ADD PRIMARY KEY (id)"))
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_customers_customer_uuid ON customers(customer_uuid)"
    ))

    # Reverse FK columns: add back Integer customer_id, backfill from UUID
    for table in dependent_tables:
        if not _table_exists(conn, table) or not _column_exists(conn, table, "customer_id"):
            continue

        conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN customer_id_old INTEGER"))
        conn.execute(sa.text(
            f"UPDATE {table} t SET customer_id_old = c.id "
            f"FROM customers c WHERE t.customer_id = c.customer_uuid"
        ))
        conn.execute(sa.text(f"DROP INDEX IF EXISTS ix_{table}_customer_id"))
        conn.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN customer_id"))
        conn.execute(sa.text(f"ALTER TABLE {table} RENAME COLUMN customer_id_old TO customer_id"))
        conn.execute(sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_customer_id ON {table}(customer_id)"
        ))

    # Re-create original FK constraints (Integer)
    fk_tables = [
        "work_orders", "messages", "activities", "quotes", "tickets",
        "equipment", "bookings", "sms_consent", "customer_service_schedules",
        "service_reminders", "geofences", "customer_tracking_links",
    ]
    for table in fk_tables:
        if _table_exists(conn, table) and _column_exists(conn, table, "customer_id"):
            conn.execute(sa.text(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey "
                f"FOREIGN KEY (customer_id) REFERENCES customers(id)"
            ))
