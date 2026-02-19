"""Create company_entities table and add entity_id FK to core tables.

Multi-LLC support: each entity represents a separate legal business
with its own bank account, Clover merchant, QBO company, and invoice numbering.

Revision ID: 063
Revises: 062
Create Date: 2026-02-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create company_entities table
    op.create_table(
        "company_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_code", sa.String(10), unique=True, index=True),
        sa.Column("tax_id", sa.String(20)),
        sa.Column("address_line1", sa.String(255)),
        sa.Column("address_line2", sa.String(255)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(50)),
        sa.Column("postal_code", sa.String(20)),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(255)),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("invoice_prefix", sa.String(10)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    # Seed default entity (existing Mac Septic LLC)
    op.execute(
        """
        INSERT INTO company_entities (id, name, short_code, invoice_prefix, is_active, is_default, state)
        VALUES (gen_random_uuid(), 'Mac Septic, LLC', 'MACLLC', 'MACLLC', TRUE, TRUE, 'SC')
        """
    )

    # Add entity_id FK to core business tables (nullable — NULL means default entity)
    for table in ["customers", "work_orders", "invoices", "payments", "technicians"]:
        op.add_column(table, sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_entity_id",
            table,
            "company_entities",
            ["entity_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_entity_id", table, ["entity_id"])

    # Add entity_id to integration token tables
    for table in ["clover_oauth_tokens", "qbo_oauth_tokens"]:
        op.add_column(table, sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_entity_id",
            table,
            "company_entities",
            ["entity_id"],
            ["id"],
        )
        op.create_index(f"ix_{table}_entity_id", table, ["entity_id"])

    # Add default_entity_id to users
    op.add_column("api_users", sa.Column("default_entity_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_api_users_default_entity_id",
        "api_users",
        "company_entities",
        ["default_entity_id"],
        ["id"],
    )


def downgrade() -> None:
    # Remove default_entity_id from users
    op.drop_constraint("fk_api_users_default_entity_id", "api_users", type_="foreignkey")
    op.drop_column("api_users", "default_entity_id")

    # Remove entity_id from integration token tables
    for table in ["clover_oauth_tokens", "qbo_oauth_tokens"]:
        op.drop_index(f"ix_{table}_entity_id", table)
        op.drop_constraint(f"fk_{table}_entity_id", table, type_="foreignkey")
        op.drop_column(table, "entity_id")

    # Remove entity_id from core business tables
    for table in ["customers", "work_orders", "invoices", "payments", "technicians"]:
        op.drop_index(f"ix_{table}_entity_id", table)
        op.drop_constraint(f"fk_{table}_entity_id", table, type_="foreignkey")
        op.drop_column(table, "entity_id")

    # Drop company_entities table
    op.drop_table("company_entities")
