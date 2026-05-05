"""realtor pipeline tables.

Adds two tables for cloud-backed Realtor Pipeline persistence:

- realtor_agents: real estate agents being cultivated as referral partners
- realtor_referrals: jobs/inspections referred by an agent

Revision ID: 121
Revises: 120
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "121"
down_revision = "120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realtor_agents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("brokerage", sa.String(length=255), nullable=True),
        sa.Column("license_number", sa.String(length=50), nullable=True),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("cell", sa.String(length=20), nullable=True),
        sa.Column(
            "preferred_contact",
            sa.String(length=20),
            nullable=False,
            server_default="call",
        ),
        sa.Column("coverage_area", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("zip_code", sa.String(length=16), nullable=True),
        sa.Column(
            "stage", sa.String(length=32), nullable=False, server_default="cold"
        ),
        sa.Column("current_inspector", sa.String(length=100), nullable=True),
        sa.Column("relationship_notes", sa.Text(), nullable=True),
        sa.Column(
            "call_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_call_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_duration", sa.Integer(), nullable=True),
        sa.Column("last_disposition", sa.String(length=40), nullable=True),
        sa.Column("next_follow_up", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "total_referrals", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_revenue",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_referral_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "one_pager_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "one_pager_sent_date", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "assigned_rep",
            sa.Integer(),
            sa.ForeignKey("api_users.id"),
            nullable=True,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_realtor_agents_phone", "realtor_agents", ["phone"], unique=False
    )
    op.create_index(
        "ix_realtor_agents_stage", "realtor_agents", ["stage"], unique=False
    )

    op.create_table(
        "realtor_referrals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "realtor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("realtor_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("property_address", sa.String(length=500), nullable=False),
        sa.Column("homeowner_name", sa.String(length=200), nullable=True),
        sa.Column(
            "service_type",
            sa.String(length=40),
            nullable=False,
            server_default="inspection",
        ),
        sa.Column("invoice_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "referred_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_realtor_referrals_realtor_id",
        "realtor_referrals",
        ["realtor_id"],
        unique=False,
    )
    op.create_index(
        "ix_realtor_referrals_status",
        "realtor_referrals",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_realtor_referrals_status", table_name="realtor_referrals")
    op.drop_index(
        "ix_realtor_referrals_realtor_id", table_name="realtor_referrals"
    )
    op.drop_table("realtor_referrals")
    op.drop_index("ix_realtor_agents_stage", table_name="realtor_agents")
    op.drop_index("ix_realtor_agents_phone", table_name="realtor_agents")
    op.drop_table("realtor_agents")
