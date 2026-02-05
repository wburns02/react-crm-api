"""Convert Message, SMSConsent, SMSConsentAudit Integer PKs to UUID.

These tables have inbound FK references that need careful migration:
- messages.id ← service_reminders.message_id
- sms_consent.id ← sms_consent_audit.consent_id

Revision ID: 048
Revises: 047
Create Date: 2026-02-05
"""

from alembic import op
import sqlalchemy as sa

revision = "048"
down_revision = "047"
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


def upgrade() -> None:
    conn = op.get_bind()

    # ══════════════════════════════════════════════════════════════════
    # PART 1: Messages (PK: Integer → UUID)
    # Inbound FK: service_reminders.message_id
    # ══════════════════════════════════════════════════════════════════

    # 1a. Drop FK from service_reminders (if it exists)
    if _table_exists(conn, "service_reminders"):
        conn.execute(sa.text(
            "ALTER TABLE service_reminders DROP CONSTRAINT IF EXISTS service_reminders_message_id_fkey"
        ))
        conn.execute(sa.text(
            "ALTER TABLE service_reminders DROP CONSTRAINT IF EXISTS fk_service_reminders_message_id"
        ))

    # 1b. Add UUID column to messages
    conn.execute(sa.text("ALTER TABLE messages ADD COLUMN new_id UUID DEFAULT gen_random_uuid()"))
    conn.execute(sa.text("UPDATE messages SET new_id = gen_random_uuid() WHERE new_id IS NULL"))

    # 1c. Add UUID column to service_reminders and backfill via JOIN
    if _table_exists(conn, "service_reminders") and _column_exists(conn, "service_reminders", "message_id"):
        conn.execute(sa.text("ALTER TABLE service_reminders ADD COLUMN new_message_id UUID"))
        conn.execute(sa.text(
            "UPDATE service_reminders sr SET new_message_id = m.new_id "
            "FROM messages m WHERE sr.message_id = m.id"
        ))

    # 1d. Swap PK on messages
    conn.execute(sa.text("ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_pkey"))
    conn.execute(sa.text("ALTER TABLE messages DROP COLUMN id"))
    conn.execute(sa.text("ALTER TABLE messages RENAME COLUMN new_id TO id"))
    conn.execute(sa.text("ALTER TABLE messages ADD PRIMARY KEY (id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_messages_id ON messages(id)"))

    # 1e. Swap FK column on service_reminders
    if _table_exists(conn, "service_reminders") and _column_exists(conn, "service_reminders", "message_id"):
        conn.execute(sa.text("ALTER TABLE service_reminders DROP COLUMN message_id"))
        conn.execute(sa.text("ALTER TABLE service_reminders RENAME COLUMN new_message_id TO message_id"))
        # Re-create FK constraint
        conn.execute(sa.text(
            "ALTER TABLE service_reminders ADD CONSTRAINT service_reminders_message_id_fkey "
            "FOREIGN KEY (message_id) REFERENCES messages(id)"
        ))

    # ══════════════════════════════════════════════════════════════════
    # PART 2: SMSConsent (PK: Integer → UUID)
    # Inbound FK: sms_consent_audit.consent_id
    # ══════════════════════════════════════════════════════════════════

    if _table_exists(conn, "sms_consent"):
        # 2a. Drop FK from sms_consent_audit
        if _table_exists(conn, "sms_consent_audit"):
            conn.execute(sa.text(
                "ALTER TABLE sms_consent_audit DROP CONSTRAINT IF EXISTS sms_consent_audit_consent_id_fkey"
            ))

        # 2b. Add UUID column to sms_consent
        conn.execute(sa.text("ALTER TABLE sms_consent ADD COLUMN new_id UUID DEFAULT gen_random_uuid()"))
        conn.execute(sa.text("UPDATE sms_consent SET new_id = gen_random_uuid() WHERE new_id IS NULL"))

        # 2c. Add UUID column to sms_consent_audit and backfill
        if _table_exists(conn, "sms_consent_audit"):
            conn.execute(sa.text("ALTER TABLE sms_consent_audit ADD COLUMN new_consent_id UUID"))
            conn.execute(sa.text(
                "UPDATE sms_consent_audit sca SET new_consent_id = sc.new_id "
                "FROM sms_consent sc WHERE sca.consent_id = sc.id"
            ))

        # 2d. Swap PK on sms_consent
        conn.execute(sa.text("ALTER TABLE sms_consent DROP CONSTRAINT IF EXISTS sms_consent_pkey"))
        conn.execute(sa.text("ALTER TABLE sms_consent DROP COLUMN id"))
        conn.execute(sa.text("ALTER TABLE sms_consent RENAME COLUMN new_id TO id"))
        conn.execute(sa.text("ALTER TABLE sms_consent ADD PRIMARY KEY (id)"))

        # 2e. Swap FK column on sms_consent_audit
        if _table_exists(conn, "sms_consent_audit"):
            conn.execute(sa.text("ALTER TABLE sms_consent_audit DROP COLUMN consent_id"))
            conn.execute(sa.text("ALTER TABLE sms_consent_audit RENAME COLUMN new_consent_id TO consent_id"))
            conn.execute(sa.text(
                "ALTER TABLE sms_consent_audit ADD CONSTRAINT sms_consent_audit_consent_id_fkey "
                "FOREIGN KEY (consent_id) REFERENCES sms_consent(id)"
            ))

    # ══════════════════════════════════════════════════════════════════
    # PART 3: SMSConsentAudit PK (Integer → UUID, no inbound FKs)
    # ══════════════════════════════════════════════════════════════════

    if _table_exists(conn, "sms_consent_audit"):
        conn.execute(sa.text("ALTER TABLE sms_consent_audit ADD COLUMN new_id UUID DEFAULT gen_random_uuid()"))
        conn.execute(sa.text("UPDATE sms_consent_audit SET new_id = gen_random_uuid() WHERE new_id IS NULL"))
        conn.execute(sa.text("ALTER TABLE sms_consent_audit DROP CONSTRAINT IF EXISTS sms_consent_audit_pkey"))
        conn.execute(sa.text("ALTER TABLE sms_consent_audit DROP COLUMN id"))
        conn.execute(sa.text("ALTER TABLE sms_consent_audit RENAME COLUMN new_id TO id"))
        conn.execute(sa.text("ALTER TABLE sms_consent_audit ADD PRIMARY KEY (id)"))


def downgrade() -> None:
    # Lossy downgrade - original integer IDs cannot be restored
    # Use database backup for full rollback
    conn = op.get_bind()

    for table in ["messages", "sms_consent", "sms_consent_audit"]:
        if _table_exists(conn, table):
            conn.execute(sa.text(f"ALTER TABLE {table} ALTER COLUMN id TYPE VARCHAR(36) USING id::text"))
