"""Consolidate 11 runtime ensure_* schema patches into a proper migration.

All DDL here is idempotent (IF NOT EXISTS / DO $$ blocks).
These patches were previously applied at app startup via ensure_* functions in main.py.

Revision ID: 071
Revises: 070
Create Date: 2026-02-24
"""
from alembic import op


revision = "071"
down_revision = "070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. work_order_photos table (ensure_work_order_photos_table) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS work_order_photos (
            id VARCHAR(36) PRIMARY KEY,
            work_order_id VARCHAR(36) NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            photo_type VARCHAR(50) NOT NULL,
            data TEXT NOT NULL,
            thumbnail TEXT,
            timestamp TIMESTAMPTZ NOT NULL,
            device_info VARCHAR(255),
            gps_lat FLOAT,
            gps_lng FLOAT,
            gps_accuracy FLOAT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_order_photos_work_order_id ON work_order_photos(work_order_id)")

    # ── 2. pay_rate columns (ensure_pay_rate_columns) ──
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE technician_pay_rates ADD COLUMN pay_type VARCHAR(20) DEFAULT 'hourly' NOT NULL;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE technician_pay_rates ADD COLUMN salary_amount FLOAT;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE technician_pay_rates ALTER COLUMN hourly_rate DROP NOT NULL;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)

    # ── 3. messages columns (ensure_messages_columns) ──
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagetype AS ENUM ('sms', 'email', 'call', 'note');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagedirection AS ENUM ('inbound', 'outbound');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE messagestatus AS ENUM ('pending', 'queued', 'sent', 'delivered', 'failed', 'received');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS type messagetype")
    op.execute("UPDATE messages SET type = 'sms' WHERE type IS NULL")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE messages ALTER COLUMN type SET NOT NULL;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS direction messagedirection")
    op.execute("UPDATE messages SET direction = 'outbound' WHERE direction IS NULL")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE messages ALTER COLUMN direction SET NOT NULL;
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS status messagestatus DEFAULT 'sent'")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS subject VARCHAR(255)")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS from_address VARCHAR(255)")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'react'")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMPTZ")
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")

    # ── 4. email_templates table (ensure_email_templates_table) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            subject VARCHAR(255) NOT NULL,
            body_html TEXT NOT NULL,
            body_text TEXT,
            variables JSONB,
            category VARCHAR(50),
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_templates_category ON email_templates(category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_templates_is_active ON email_templates(is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_templates_name ON email_templates(name)")

    # ── 5. work_order_number column (ensure_work_order_number_column) ──
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS work_order_number VARCHAR(20)")
    # Backfill NULLs
    op.execute("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) as rn
            FROM work_orders
            WHERE work_order_number IS NULL
        )
        UPDATE work_orders wo
        SET work_order_number = 'WO-' || LPAD(n.rn::text, 6, '0')
        FROM numbered n
        WHERE wo.id = n.id
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_work_orders_number ON work_orders(work_order_number)")

    # ── 6. is_admin column (ensure_is_admin_column) ──
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE api_users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT false;
        EXCEPTION WHEN duplicate_column THEN NULL;
        END $$
    """)
    op.execute("UPDATE api_users SET is_admin = true WHERE email = 'will@macseptic.com' AND is_admin = false")

    # ── 7. commissions columns (ensure_commissions_columns) ──
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'commissions') THEN
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS dump_site_id UUID;
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS job_type VARCHAR(50);
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS gallons_pumped INTEGER;
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS dump_fee_per_gallon FLOAT;
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS dump_fee_amount FLOAT;
                ALTER TABLE commissions ADD COLUMN IF NOT EXISTS commissionable_amount FLOAT;
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_commissions_job_type ON commissions(job_type)")

    # ── 8. work_order audit columns + table (ensure_work_order_audit_columns) ──
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS created_by VARCHAR(100)")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS updated_by VARCHAR(100)")
    op.execute("ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'crm'")
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE work_orders ALTER COLUMN created_at SET DEFAULT NOW();
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE work_orders ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC';
        EXCEPTION WHEN others THEN NULL;
        END $$
    """)
    op.execute("UPDATE work_orders SET created_at = scheduled_date::timestamp WHERE created_at IS NULL AND scheduled_date IS NOT NULL")
    op.execute("UPDATE work_orders SET created_at = NOW() WHERE created_at IS NULL")
    op.execute("UPDATE work_orders SET source = 'crm' WHERE source IS NULL")

    op.execute("""
        CREATE TABLE IF NOT EXISTS work_order_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            work_order_id UUID NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            action VARCHAR(30) NOT NULL,
            description TEXT,
            user_email VARCHAR(100),
            user_name VARCHAR(200),
            source VARCHAR(50),
            ip_address VARCHAR(45),
            user_agent VARCHAR(500),
            changes JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_wo_audit_work_order_id ON work_order_audit_log(work_order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wo_audit_action ON work_order_audit_log(action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_wo_audit_created_at ON work_order_audit_log(created_at)")

    # ── 9. user_activity_log table (ensure_user_activity_table) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id INTEGER,
            user_email VARCHAR(100),
            user_name VARCHAR(200),
            category VARCHAR(30) NOT NULL,
            action VARCHAR(50) NOT NULL,
            description TEXT,
            ip_address VARCHAR(45),
            user_agent VARCHAR(500),
            source VARCHAR(50),
            resource_type VARCHAR(50),
            resource_id VARCHAR(100),
            endpoint VARCHAR(200),
            http_method VARCHAR(10),
            status_code INTEGER,
            response_time_ms INTEGER,
            session_id VARCHAR(50),
            entity_id VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_user_id ON user_activity_log(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_category ON user_activity_log(category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_action ON user_activity_log(action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_created_at ON user_activity_log(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_user_created ON user_activity_log(user_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ual_category_created ON user_activity_log(category, created_at)")

    # ── 10. missing indexes (ensure_missing_indexes) ──
    op.execute("CREATE INDEX IF NOT EXISTS ix_customers_entity_id ON customers(entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_orders_entity_id ON work_orders(entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_entity_id ON payments(entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_payments_invoice_id ON payments(invoice_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_work_orders_scheduled_date_status ON work_orders(scheduled_date, status)")

    # ── 11. MFA tables (ensure_mfa_tables) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_mfa_settings (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES api_users(id),
            totp_secret VARCHAR(32),
            totp_enabled BOOLEAN DEFAULT FALSE,
            totp_verified BOOLEAN DEFAULT FALSE,
            mfa_enabled BOOLEAN DEFAULT FALSE,
            mfa_enforced BOOLEAN DEFAULT FALSE,
            backup_codes_count INTEGER DEFAULT 0,
            backup_codes_generated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_backup_codes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES api_users(id),
            mfa_settings_id INTEGER NOT NULL REFERENCES user_mfa_settings(id),
            code_hash VARCHAR(255) NOT NULL,
            used BOOLEAN DEFAULT FALSE,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mfa_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id INTEGER NOT NULL REFERENCES api_users(id),
            session_token_hash VARCHAR(255) NOT NULL UNIQUE,
            challenge_type VARCHAR(20) DEFAULT 'totp',
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            expires_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_mfa_settings_user_id ON user_mfa_settings(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_backup_codes_user_id ON user_backup_codes(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mfa_sessions_user_id ON mfa_sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mfa_sessions_expires_at ON mfa_sessions(expires_at)")


def downgrade() -> None:
    # All changes are additive; downgrade is intentionally empty.
    pass
