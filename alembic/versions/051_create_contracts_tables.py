"""Create contracts tables (contracts, contract_templates)

Revision ID: 051
Revises: 050
Create Date: 2026-02-06

This migration creates contracts and contract_templates tables using raw SQL.
Fixes customer_id to be UUID (post-migration 049).
"""

from alembic import op

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create contract_templates table first (referenced by contracts)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contract_templates (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(50) UNIQUE NOT NULL,
            description TEXT,
            contract_type VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            terms_and_conditions TEXT,
            default_duration_months INTEGER DEFAULT 12,
            default_billing_frequency VARCHAR(20) DEFAULT 'monthly',
            default_payment_terms VARCHAR(100),
            default_auto_renew BOOLEAN DEFAULT false,
            default_services JSONB,
            base_price REAL,
            pricing_notes TEXT,
            variables JSONB,
            is_active BOOLEAN DEFAULT true,
            version INTEGER DEFAULT 1,
            created_by VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_contract_templates_code ON contract_templates(code)")

    # Create contracts table (customer_id as UUID to match customers table)
    op.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id UUID PRIMARY KEY,
            contract_number VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            contract_type VARCHAR(50) NOT NULL,
            customer_id UUID NOT NULL,
            customer_name VARCHAR(255),
            template_id UUID,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            auto_renew BOOLEAN DEFAULT false,
            renewal_terms TEXT,
            total_value REAL,
            billing_frequency VARCHAR(20) DEFAULT 'monthly',
            payment_terms VARCHAR(100),
            services_included JSONB,
            covered_properties JSONB,
            coverage_details TEXT,
            status VARCHAR(20) DEFAULT 'draft',
            requires_signature BOOLEAN DEFAULT true,
            customer_signed BOOLEAN DEFAULT false,
            customer_signed_date TIMESTAMP WITH TIME ZONE,
            company_signed BOOLEAN DEFAULT false,
            company_signed_date TIMESTAMP WITH TIME ZONE,
            signature_request_id VARCHAR(36),
            document_url VARCHAR(500),
            signed_document_url VARCHAR(500),
            terms_and_conditions TEXT,
            special_terms TEXT,
            notes TEXT,
            internal_notes TEXT,
            created_by VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_contract_number ON contracts(contract_number)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_customer_id ON contracts(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_template_id ON contracts(template_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_contracts_end_date ON contracts(end_date)")

    # Add FK constraints (skip if exist)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE contracts
            ADD CONSTRAINT contracts_customer_id_fkey
            FOREIGN KEY (customer_id) REFERENCES customers(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE contracts
            ADD CONSTRAINT contracts_template_id_fkey
            FOREIGN KEY (template_id) REFERENCES contract_templates(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS contracts CASCADE")
    op.execute("DROP TABLE IF EXISTS contract_templates CASCADE")
