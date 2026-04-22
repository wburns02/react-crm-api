"""outbound campaigns persistence

Revision ID: 106
Revises: 105
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbound_campaigns",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("source_sheet", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "outbound_campaign_contacts",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("campaign_id", sa.Text(), sa.ForeignKey("outbound_campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_number", sa.String(length=100), nullable=True),
        sa.Column("account_name", sa.String(length=255), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=8), nullable=True),
        sa.Column("zip_code", sa.String(length=16), nullable=True),
        sa.Column("service_zone", sa.String(length=100), nullable=True),
        sa.Column("system_type", sa.String(length=100), nullable=True),
        sa.Column("contract_type", sa.String(length=50), nullable=True),
        sa.Column("contract_status", sa.String(length=50), nullable=True),
        sa.Column("contract_start", sa.Date(), nullable=True),
        sa.Column("contract_end", sa.Date(), nullable=True),
        sa.Column("contract_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("customer_type", sa.String(length=50), nullable=True),
        sa.Column("call_priority_label", sa.String(length=50), nullable=True),
        sa.Column("call_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("call_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_call_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_call_duration", sa.Integer(), nullable=True),
        sa.Column("last_disposition", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("callback_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_rep", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_outbound_contacts_campaign_status",
        "outbound_campaign_contacts",
        ["campaign_id", "call_status"],
    )
    op.create_index("ix_outbound_contacts_phone", "outbound_campaign_contacts", ["phone"])

    op.create_table(
        "outbound_call_attempts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("outbound_campaign_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.Text(),
            sa.ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rep_user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column(
            "dispositioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("call_status", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_outbound_attempts_contact_time",
        "outbound_call_attempts",
        ["contact_id", "dispositioned_at"],
    )
    op.create_index(
        "ix_outbound_attempts_rep_time",
        "outbound_call_attempts",
        ["rep_user_id", "dispositioned_at"],
    )

    op.create_table(
        "outbound_callbacks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("outbound_campaign_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.Text(),
            sa.ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rep_user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbound_callbacks_sched", "outbound_callbacks", ["scheduled_for", "status"])


def downgrade() -> None:
    op.drop_index("ix_outbound_callbacks_sched", table_name="outbound_callbacks")
    op.drop_table("outbound_callbacks")
    op.drop_index("ix_outbound_attempts_rep_time", table_name="outbound_call_attempts")
    op.drop_index("ix_outbound_attempts_contact_time", table_name="outbound_call_attempts")
    op.drop_table("outbound_call_attempts")
    op.drop_index("ix_outbound_contacts_phone", table_name="outbound_campaign_contacts")
    op.drop_index("ix_outbound_contacts_campaign_status", table_name="outbound_campaign_contacts")
    op.drop_table("outbound_campaign_contacts")
    op.drop_table("outbound_campaigns")
