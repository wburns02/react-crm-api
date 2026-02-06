"""Create operational tables (compliance and service intervals)

Revision ID: 050
Revises: 049
Create Date: 2026-02-06

This migration creates tables for compliance tracking and service intervals using raw SQL.
"""

from alembic import op

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create licenses table
    op.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id UUID PRIMARY KEY,
            license_number VARCHAR(100) NOT NULL,
            license_type VARCHAR(100) NOT NULL,
            issuing_authority VARCHAR(255),
            issuing_state VARCHAR(2),
            holder_type VARCHAR(20) NOT NULL DEFAULT 'business',
            holder_id VARCHAR(36),
            holder_name VARCHAR(255),
            issue_date DATE,
            expiry_date DATE NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            renewal_reminder_sent BOOLEAN DEFAULT false,
            renewal_reminder_date DATE,
            document_url VARCHAR(500),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_licenses_license_number ON licenses(license_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_licenses_expiry_date ON licenses(expiry_date)")

    # Create certifications table
    op.execute("""
        CREATE TABLE IF NOT EXISTS certifications (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            certification_type VARCHAR(100) NOT NULL,
            certification_number VARCHAR(100),
            issuing_organization VARCHAR(255),
            technician_id VARCHAR(36) NOT NULL,
            technician_name VARCHAR(255),
            issue_date DATE,
            expiry_date DATE,
            status VARCHAR(20) DEFAULT 'active',
            renewal_reminder_sent BOOLEAN DEFAULT false,
            requires_renewal BOOLEAN DEFAULT true,
            renewal_interval_months INTEGER,
            training_hours INTEGER,
            training_date DATE,
            training_provider VARCHAR(255),
            document_url VARCHAR(500),
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_certifications_technician_id ON certifications(technician_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_certifications_expiry_date ON certifications(expiry_date)")

    # Create inspections table
    op.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id UUID PRIMARY KEY,
            inspection_number VARCHAR(50) UNIQUE NOT NULL,
            inspection_type VARCHAR(100) NOT NULL,
            customer_id UUID NOT NULL,
            property_address VARCHAR(500),
            system_type VARCHAR(100),
            system_age_years INTEGER,
            tank_size_gallons INTEGER,
            scheduled_date DATE,
            completed_date DATE,
            technician_id UUID,
            technician_name VARCHAR(255),
            work_order_id UUID,
            status VARCHAR(20) DEFAULT 'pending',
            result VARCHAR(20),
            overall_condition VARCHAR(20),
            checklist JSONB,
            sludge_depth_inches REAL,
            scum_depth_inches REAL,
            liquid_depth_inches REAL,
            requires_followup BOOLEAN DEFAULT false,
            followup_due_date DATE,
            violations_found JSONB,
            corrective_actions TEXT,
            county VARCHAR(100),
            permit_number VARCHAR(100),
            filed_with_county BOOLEAN DEFAULT false,
            county_filing_date DATE,
            photos JSONB,
            report_url VARCHAR(500),
            notes TEXT,
            inspection_fee REAL,
            fee_collected BOOLEAN DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_inspections_inspection_number ON inspections(inspection_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inspections_customer_id ON inspections(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_inspections_scheduled_date ON inspections(scheduled_date)")

    # Create service_intervals table
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_intervals (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            service_type VARCHAR(50) NOT NULL,
            interval_months INTEGER NOT NULL,
            reminder_days_before JSONB DEFAULT '[30, 14, 7]',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)

    # Create customer_service_schedules table
    op.execute("""
        CREATE TABLE IF NOT EXISTS customer_service_schedules (
            id UUID PRIMARY KEY,
            customer_id UUID NOT NULL,
            service_interval_id UUID NOT NULL,
            last_service_date DATE,
            next_due_date DATE NOT NULL,
            status VARCHAR(30) DEFAULT 'upcoming',
            scheduled_work_order_id VARCHAR(36),
            reminder_sent BOOLEAN DEFAULT false,
            last_reminder_sent_at TIMESTAMP WITH TIME ZONE,
            notes TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_service_schedules_customer_id ON customer_service_schedules(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_customer_service_schedules_next_due_date ON customer_service_schedules(next_due_date)")

    # Create service_reminders table
    op.execute("""
        CREATE TABLE IF NOT EXISTS service_reminders (
            id UUID PRIMARY KEY,
            schedule_id UUID NOT NULL,
            customer_id UUID NOT NULL,
            reminder_type VARCHAR(20) NOT NULL,
            days_before_due INTEGER,
            status VARCHAR(20) DEFAULT 'sent',
            error_message TEXT,
            message_id UUID,
            sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            delivered_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_service_reminders_schedule_id ON service_reminders(schedule_id)")

    # Add FK constraints (skip if exist)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE customer_service_schedules
            ADD CONSTRAINT customer_service_schedules_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE customer_service_schedules
            ADD CONSTRAINT customer_service_schedules_service_interval_id_fkey
            FOREIGN KEY (service_interval_id) REFERENCES service_intervals(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE service_reminders
            ADD CONSTRAINT service_reminders_schedule_id_fkey
            FOREIGN KEY (schedule_id) REFERENCES customer_service_schedules(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE service_reminders
            ADD CONSTRAINT service_reminders_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS service_reminders CASCADE")
    op.execute("DROP TABLE IF EXISTS customer_service_schedules CASCADE")
    op.execute("DROP TABLE IF EXISTS service_intervals CASCADE")
    op.execute("DROP TABLE IF EXISTS inspections CASCADE")
    op.execute("DROP TABLE IF EXISTS certifications CASCADE")
    op.execute("DROP TABLE IF EXISTS licenses CASCADE")
