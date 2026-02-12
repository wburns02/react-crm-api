"""Add commercial tiers, neighborhood bundles, and upsell fields to contracts.

Revision ID: 055
Revises: 054
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade():
    # --- New columns on contracts table ---
    op.add_column("contracts", sa.Column("tier", sa.String(30), nullable=True))
    op.add_column("contracts", sa.Column("bundle_id", UUID(as_uuid=True), nullable=True))
    op.add_column("contracts", sa.Column("discount_percent", sa.Float(), nullable=True))
    op.add_column("contracts", sa.Column("system_size", sa.String(50), nullable=True))
    op.add_column("contracts", sa.Column("daily_flow_gallons", sa.Integer(), nullable=True))
    op.add_column("contracts", sa.Column("add_ons", sa.JSON(), nullable=True))
    op.add_column("contracts", sa.Column("referral_code", sa.String(50), nullable=True))
    op.add_column("contracts", sa.Column("referral_credit", sa.Float(), nullable=True))
    op.add_column("contracts", sa.Column("annual_increase_percent", sa.Float(), nullable=True, server_default="5.0"))
    op.add_column("contracts", sa.Column("upsell_from_id", UUID(as_uuid=True), nullable=True))
    op.add_column("contracts", sa.Column("neighborhood_group_name", sa.String(255), nullable=True))

    op.create_index("ix_contracts_tier", "contracts", ["tier"])
    op.create_index("ix_contracts_bundle_id", "contracts", ["bundle_id"])

    # --- neighborhood_bundles table ---
    op.create_table(
        "neighborhood_bundles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("discount_percent", sa.Float(), nullable=False, server_default="10.0"),
        sa.Column("min_contracts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # FK from contracts.bundle_id -> neighborhood_bundles.id
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE contracts ADD CONSTRAINT fk_contracts_bundle_id
                FOREIGN KEY (bundle_id) REFERENCES neighborhood_bundles(id);
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)


def downgrade():
    op.execute("ALTER TABLE contracts DROP CONSTRAINT IF EXISTS fk_contracts_bundle_id")
    op.drop_index("ix_contracts_bundle_id", "contracts")
    op.drop_index("ix_contracts_tier", "contracts")
    op.drop_column("contracts", "neighborhood_group_name")
    op.drop_column("contracts", "upsell_from_id")
    op.drop_column("contracts", "annual_increase_percent")
    op.drop_column("contracts", "referral_credit")
    op.drop_column("contracts", "referral_code")
    op.drop_column("contracts", "add_ons")
    op.drop_column("contracts", "daily_flow_gallons")
    op.drop_column("contracts", "system_size")
    op.drop_column("contracts", "discount_percent")
    op.drop_column("contracts", "bundle_id")
    op.drop_column("contracts", "tier")
    op.drop_table("neighborhood_bundles")
