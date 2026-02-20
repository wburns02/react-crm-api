"""email_campaigns table for SendGrid-backed marketing campaigns.

Revision ID: 066
Revises: 065
Create Date: 2026-02-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_campaigns",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("html_content", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("recipient_count", sa.Integer, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("email_campaigns")
