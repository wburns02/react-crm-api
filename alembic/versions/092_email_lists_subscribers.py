"""email_lists and email_subscribers tables

Revision ID: 092
Revises: 091
Create Date: 2026-03-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Email Lists table
    op.create_table(
        "email_lists",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Email Subscribers table
    op.create_table(
        "email_subscribers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("list_id", UUID(as_uuid=True), sa.ForeignKey("email_lists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("subscribed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
    )

    # Indexes
    op.create_index("idx_email_subscribers_list_id", "email_subscribers", ["list_id"])
    op.create_index("idx_email_subscribers_email", "email_subscribers", ["email"])
    op.create_index("idx_email_subscribers_list_status", "email_subscribers", ["list_id", "status"])

    # Unique constraint: one email per list
    op.create_unique_constraint(
        "uq_email_subscriber_list_email",
        "email_subscribers",
        ["list_id", "email"],
    )


def downgrade() -> None:
    op.drop_table("email_subscribers")
    op.drop_table("email_lists")
