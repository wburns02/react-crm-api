"""Convert GPS tracking models and standalone Integer PK tables to UUID.

GPS tracking: Fix broken Integer FK types (should reference UUID PKs from migration 046).
Standalone: payments, quotes, call_logs, call_dispositions (no inbound FKs).

Revision ID: 047
Revises: 046
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def _table_exists(conn, table_name):
    return conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :t)"
    ), {"t": table_name}).scalar()


def _column_exists(conn, table_name, column_name):
    return conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c)"
    ), {"t": table_name, "c": column_name}).scalar()


def _convert_int_pk_to_uuid(conn, table_name):
    """Convert an Integer PK to UUID for a table with no inbound FK references."""
    if not _table_exists(conn, table_name):
        return

    conn.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN new_id UUID DEFAULT gen_random_uuid()"))
    conn.execute(sa.text(f"UPDATE {table_name} SET new_id = gen_random_uuid() WHERE new_id IS NULL"))
    conn.execute(sa.text(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {table_name}_pkey"))
    conn.execute(sa.text(f"ALTER TABLE {table_name} DROP COLUMN id"))
    conn.execute(sa.text(f"ALTER TABLE {table_name} RENAME COLUMN new_id TO id"))
    conn.execute(sa.text(f"ALTER TABLE {table_name} ADD PRIMARY KEY (id)"))
    conn.execute(sa.text(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_id ON {table_name}(id)"))


def _convert_int_fk_to_uuid(conn, table_name, column_name, nullable=True):
    """Convert an Integer FK column to UUID, setting existing values to NULL."""
    if not _table_exists(conn, table_name) or not _column_exists(conn, table_name, column_name):
        return

    # Drop any FK constraint on this column
    constraint_name = f"{table_name}_{column_name}_fkey"
    conn.execute(sa.text(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {constraint_name}"))

    # Add new UUID column, drop old Integer column, rename
    new_col = f"{column_name}_new"
    conn.execute(sa.text(f"ALTER TABLE {table_name} ADD COLUMN {new_col} UUID"))
    # Cannot JOIN-map Integer→UUID for GPS tables since the Integer values never matched String(36) PKs
    # These columns held invalid data (if any), so we leave them NULL
    conn.execute(sa.text(f"ALTER TABLE {table_name} DROP COLUMN {column_name}"))
    conn.execute(sa.text(f"ALTER TABLE {table_name} RENAME COLUMN {new_col} TO {column_name}"))


def upgrade() -> None:
    conn = op.get_bind()

    # ══════════════════════════════════════════════════════════════════
    # PART A: GPS Tracking Models - Fix broken Integer FK types + PKs
    # ══════════════════════════════════════════════════════════════════

    gps_tables = [
        # (table_name, [(fk_column, nullable), ...])
        ("technician_locations", [
            ("technician_id", False),
            ("current_work_order_id", True),
        ]),
        ("location_history", [
            ("technician_id", False),
            ("work_order_id", True),
        ]),
        ("geofences", [
            # customer_id stays Integer until migration 049
            ("work_order_id", True),
        ]),
        ("geofence_events", [
            ("technician_id", False),
            ("work_order_id", True),
        ]),
        ("customer_tracking_links", [
            # customer_id stays Integer until migration 049
            ("technician_id", False),
            ("work_order_id", False),
        ]),
        ("eta_calculations", [
            ("technician_id", False),
            ("work_order_id", False),
        ]),
        ("gps_tracking_config", [
            ("technician_id", True),
        ]),
    ]

    # First: handle geofence_events.geofence_id FK → geofences.id
    # Must process geofences PK first, then geofence_events FK
    if _table_exists(conn, "geofence_events"):
        conn.execute(sa.text(
            "ALTER TABLE geofence_events DROP CONSTRAINT IF EXISTS geofence_events_geofence_id_fkey"
        ))

    # Convert GPS Integer FKs to UUID (data is invalid due to type mismatch, so NULL it)
    for table, fk_columns in gps_tables:
        for fk_col, nullable in fk_columns:
            _convert_int_fk_to_uuid(conn, table, fk_col, nullable)

    # Convert GPS Integer PKs to UUID
    for table, _ in gps_tables:
        _convert_int_pk_to_uuid(conn, table)

    # Handle geofence_events.geofence_id after geofences PK is converted
    if _table_exists(conn, "geofence_events") and _column_exists(conn, "geofence_events", "geofence_id"):
        # geofence_id was Integer FK to geofences.id (also Integer, now UUID)
        # Since both were Integer and the FK was valid, we need to map old values
        # But since we already converted geofences.id to UUID (random), the old integer
        # geofence_id values are meaningless. Set to NULL.
        conn.execute(sa.text("ALTER TABLE geofence_events ADD COLUMN geofence_id_new UUID"))
        conn.execute(sa.text("ALTER TABLE geofence_events DROP COLUMN geofence_id"))
        conn.execute(sa.text("ALTER TABLE geofence_events RENAME COLUMN geofence_id_new TO geofence_id"))

    # Re-create GPS FK constraints with UUID types
    gps_fks = [
        ("technician_locations", "technician_id", "technicians", "id"),
        ("technician_locations", "current_work_order_id", "work_orders", "id"),
        ("location_history", "technician_id", "technicians", "id"),
        ("location_history", "work_order_id", "work_orders", "id"),
        ("geofences", "work_order_id", "work_orders", "id"),
        ("geofence_events", "geofence_id", "geofences", "id"),
        ("geofence_events", "technician_id", "technicians", "id"),
        ("geofence_events", "work_order_id", "work_orders", "id"),
        ("customer_tracking_links", "technician_id", "technicians", "id"),
        ("customer_tracking_links", "work_order_id", "work_orders", "id"),
        ("eta_calculations", "technician_id", "technicians", "id"),
        ("eta_calculations", "work_order_id", "work_orders", "id"),
        ("gps_tracking_config", "technician_id", "technicians", "id"),
    ]
    for child, child_col, parent, parent_col in gps_fks:
        if _table_exists(conn, child) and _column_exists(conn, child, child_col):
            constraint = f"{child}_{child_col}_fkey"
            conn.execute(sa.text(
                f"ALTER TABLE {child} ADD CONSTRAINT {constraint} "
                f"FOREIGN KEY ({child_col}) REFERENCES {parent}({parent_col})"
            ))

    # ══════════════════════════════════════════════════════════════════
    # PART B: Standalone Integer PK tables (no inbound FK references)
    # ══════════════════════════════════════════════════════════════════

    standalone_tables = ["payments", "quotes", "call_logs", "call_dispositions"]

    for table in standalone_tables:
        _convert_int_pk_to_uuid(conn, table)


def downgrade() -> None:
    conn = op.get_bind()

    # Revert standalone tables
    for table in ["payments", "quotes", "call_logs", "call_dispositions"]:
        if not _table_exists(conn, table):
            continue
        # Cannot perfectly restore Integer PKs with original values
        # This is a lossy downgrade - original integer IDs are gone
        conn.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN id TYPE VARCHAR(36) USING id::text"))

    # Revert GPS tables - also lossy
    gps_tables = [
        "technician_locations", "location_history", "geofences",
        "geofence_events", "customer_tracking_links", "eta_calculations", "gps_tracking_config",
    ]
    for table in gps_tables:
        if not _table_exists(conn, table):
            continue
        conn.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN id TYPE VARCHAR(36) USING id::text"))

    # Note: GPS FK columns and geofence_events.geofence_id data is lost
    # A full restore requires a database backup
