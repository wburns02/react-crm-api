"""QuickBooks GoPayment parallel integration: payment sync columns + sync log + KV settings.

Revision ID: 095
Revises: 094
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ── payments: new columns (idempotent) ─────────────────────────
    existing_cols = {
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'payments'"
            )
        )
    }

    if "processor" not in existing_cols:
        op.add_column("payments", sa.Column("processor", sa.String(32), nullable=True))
    if "external_txn_id" not in existing_cols:
        op.add_column("payments", sa.Column("external_txn_id", sa.String(128), nullable=True))
    if "reference_code" not in existing_cols:
        op.add_column("payments", sa.Column("reference_code", sa.String(32), nullable=True))
    if "sync_status" not in existing_cols:
        op.add_column("payments", sa.Column("sync_status", sa.String(16), nullable=True))
    if "synced_at" not in existing_cols:
        op.add_column("payments", sa.Column("synced_at", sa.DateTime(), nullable=True))

    # Indexes (idempotent via IF NOT EXISTS)
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_external_txn_id ON payments(external_txn_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_reference_code ON payments(reference_code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_sync_status ON payments(sync_status)")

    # Backfill processor for historical rows
    op.execute(
        "UPDATE payments SET processor = 'stripe' "
        "WHERE processor IS NULL AND stripe_charge_id IS NOT NULL"
    )
    op.execute(
        "UPDATE payments SET processor = 'clover' "
        "WHERE processor IS NULL AND payment_method = 'clover'"
    )
    op.execute(
        "UPDATE payments SET processor = 'manual' WHERE processor IS NULL"
    )

    # ── qb_sync_log ────────────────────────────────────────────────
    exists = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'qb_sync_log')"
        )
    ).scalar()
    if not exists:
        op.create_table(
            "qb_sync_log",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column("run_started_at", sa.DateTime(), nullable=False),
            sa.Column("run_completed_at", sa.DateTime(), nullable=True),
            sa.Column("transactions_fetched", sa.Integer(), server_default="0"),
            sa.Column("transactions_matched", sa.Integer(), server_default="0"),
            sa.Column("transactions_unmatched", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("triggered_by", sa.String(64), nullable=True),
        )
        op.execute("CREATE INDEX ix_qb_sync_log_run_started_at ON qb_sync_log(run_started_at DESC)")

    # ── integration_settings_kv ────────────────────────────────────
    exists = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'integration_settings_kv')"
        )
    ).scalar()
    if not exists:
        op.create_table(
            "integration_settings_kv",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("value", sa.String(255), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_by", sa.String(255), nullable=True),
        )

    # Seed default
    op.execute(
        "INSERT INTO integration_settings_kv (key, value) "
        "VALUES ('primary_payment_processor', 'clover') "
        "ON CONFLICT (key) DO NOTHING"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_payments_external_txn_id")
    op.execute("DROP INDEX IF EXISTS ix_payments_reference_code")
    op.execute("DROP INDEX IF EXISTS ix_payments_sync_status")
    for col in ("synced_at", "sync_status", "reference_code", "external_txn_id", "processor"):
        try:
            op.drop_column("payments", col)
        except Exception:
            pass
    op.execute("DROP TABLE IF EXISTS qb_sync_log")
    op.execute("DROP TABLE IF EXISTS integration_settings_kv")
