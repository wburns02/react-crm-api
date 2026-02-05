"""Standardize String(36) columns to native PostgreSQL UUID type.

Converts PKs and FK columns for: technicians, work_orders, bookings,
work_order_photos, inventory_transactions, and all columns referencing them.

Revision ID: 046
Revises: 045
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    return conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
    ), {"t": table_name}).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # ── Step 1: Drop FK constraints that reference the tables being converted ──
    # Using IF EXISTS since some constraints may not exist due to prior type mismatches
    fk_drops = [
        # FKs referencing technicians.id
        ("work_orders", "work_orders_technician_id_fkey"),
        # FKs referencing work_orders.id
        ("quotes", "quotes_converted_to_work_order_id_fkey"),
        ("bookings", "bookings_work_order_id_fkey"),
        ("work_order_photos", "work_order_photos_work_order_id_fkey"),
        ("tickets", "tickets_work_order_id_fkey"),
        ("invoices", "invoices_work_order_id_fkey"),
        # FK referencing inventory_items.id (UUID → String(36) mismatch)
        ("inventory_transactions", "inventory_transactions_item_id_fkey"),
    ]
    for table, constraint in fk_drops:
        if _table_exists(conn, table):
            conn.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"))

    # ── Step 2: Convert Primary Keys from VARCHAR(36) to native UUID ──
    pk_tables = ["technicians", "work_orders", "bookings", "work_order_photos", "inventory_transactions"]
    for table in pk_tables:
        if _table_exists(conn, table):
            conn.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN id TYPE UUID USING id::uuid"))

    # ── Step 3: Convert FK/reference columns from VARCHAR(36) to UUID ──
    # Group A: Columns with actual FK constraints (will be re-created)
    # Group B: Columns without FK constraints (just type change)
    varchar_to_uuid_columns = [
        # Table, Column, Nullable
        # -- WorkOrder FK columns --
        ("work_orders", "technician_id", True),
        # -- Tables referencing work_orders.id --
        ("quotes", "converted_to_work_order_id", True),
        ("bookings", "work_order_id", True),
        ("work_order_photos", "work_order_id", False),
        ("tickets", "work_order_id", True),
        ("payments", "work_order_id", True),
        ("messages", "work_order_id", True),
        # -- Inventory --
        ("inventory_transactions", "item_id", False),
        # -- Payroll (no FK constraints, just String(36) columns) --
        ("time_entries", "technician_id", False),
        ("time_entries", "work_order_id", True),
        ("commissions", "technician_id", False),
        ("commissions", "work_order_id", True),
        ("commissions", "invoice_id", True),
        ("technician_pay_rates", "technician_id", False),
        # -- Inspection (no FK constraints) --
        ("inspections", "technician_id", True),
        ("inspections", "work_order_id", True),
        # -- Job costs (no FK constraints) --
        ("job_costs", "work_order_id", False),
        ("job_costs", "technician_id", True),
        ("job_costs", "invoice_id", True),
    ]

    for table, column, nullable in varchar_to_uuid_columns:
        # Check if table exists first (some tables may be created at runtime)
        exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
        ), {"t": table}).scalar()
        if not exists:
            continue

        # Check if column exists
        col_exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ), {"t": table, "c": column}).scalar()
        if not col_exists:
            continue

        # Null out any non-UUID-format values (safety net for bad data)
        if nullable:
            conn.execute(sa.text(
                f"UPDATE {table} SET {column} = NULL "
                f"WHERE {column} IS NOT NULL AND {column} !~ "
                f"'^[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}$'"
            ))

        conn.execute(sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE UUID USING {column}::uuid"
        ))

    # ── Step 4: Re-create FK constraints with correct UUID types ──
    fk_creates = [
        ("work_orders", "technician_id", "technicians", "id"),
        ("quotes", "converted_to_work_order_id", "work_orders", "id"),
        ("bookings", "work_order_id", "work_orders", "id"),
        ("work_order_photos", "work_order_id", "work_orders", "id"),
        ("tickets", "work_order_id", "work_orders", "id"),
        ("invoices", "work_order_id", "work_orders", "id"),
        ("inventory_transactions", "item_id", "inventory_items", "id"),
    ]
    for child_table, child_col, parent_table, parent_col in fk_creates:
        if _table_exists(conn, child_table) and _table_exists(conn, parent_table):
            constraint_name = f"{child_table}_{child_col}_fkey"
            conn.execute(sa.text(
                f"ALTER TABLE {child_table} ADD CONSTRAINT {constraint_name} "
                f"FOREIGN KEY ({child_col}) REFERENCES {parent_table}({parent_col})"
            ))


def downgrade() -> None:
    conn = op.get_bind()

    # Drop FK constraints
    fk_drops = [
        ("work_orders", "work_orders_technician_id_fkey"),
        ("quotes", "quotes_converted_to_work_order_id_fkey"),
        ("bookings", "bookings_work_order_id_fkey"),
        ("work_order_photos", "work_order_photos_work_order_id_fkey"),
        ("tickets", "tickets_work_order_id_fkey"),
        ("invoices", "invoices_work_order_id_fkey"),
        ("inventory_transactions", "inventory_transactions_item_id_fkey"),
    ]
    for table, constraint in fk_drops:
        if _table_exists(conn, table):
            conn.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}"))

    # Revert PKs back to VARCHAR(36)
    pk_tables = ["technicians", "work_orders", "bookings", "work_order_photos", "inventory_transactions"]
    for table in pk_tables:
        if _table_exists(conn, table):
            conn.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN id TYPE VARCHAR(36) USING id::text"))

    # Revert FK columns back to VARCHAR(36)
    varchar_columns = [
        "work_orders.technician_id", "quotes.converted_to_work_order_id",
        "bookings.work_order_id", "work_order_photos.work_order_id",
        "tickets.work_order_id", "payments.work_order_id", "messages.work_order_id",
        "inventory_transactions.item_id",
        "time_entries.technician_id", "time_entries.work_order_id",
        "commissions.technician_id", "commissions.work_order_id", "commissions.invoice_id",
        "technician_pay_rates.technician_id",
        "inspections.technician_id", "inspections.work_order_id",
        "job_costs.work_order_id", "job_costs.technician_id", "job_costs.invoice_id",
    ]
    for entry in varchar_columns:
        table, column = entry.split(".")
        exists = conn.execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c)"
        ), {"t": table, "c": column}).scalar()
        if exists:
            conn.execute(sa.text(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE VARCHAR(36) USING {column}::text"
            ))

    # Re-create original FK constraints as VARCHAR(36)
    fk_creates = [
        ("work_orders", "technician_id", "technicians", "id"),
        ("quotes", "converted_to_work_order_id", "work_orders", "id"),
        ("bookings", "work_order_id", "work_orders", "id"),
        ("work_order_photos", "work_order_id", "work_orders", "id"),
        ("tickets", "work_order_id", "work_orders", "id"),
    ]
    for child_table, child_col, parent_table, parent_col in fk_creates:
        if _table_exists(conn, child_table) and _table_exists(conn, parent_table):
            constraint_name = f"{child_table}_{child_col}_fkey"
            conn.execute(sa.text(
                f"ALTER TABLE {child_table} ADD CONSTRAINT {constraint_name} "
                f"FOREIGN KEY ({child_col}) REFERENCES {parent_table}({parent_col})"
            ))
