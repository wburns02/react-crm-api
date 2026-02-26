"""create negative_keyword_queue table

Revision ID: 079
Revises: 078
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "negative_keyword_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False, server_default="exact"),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("campaign_id", sa.String(50), nullable=True),
        sa.Column("campaign_name", sa.String(255), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("estimated_waste", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_negative_keyword_queue_status", "negative_keyword_queue", ["status"])
    op.create_index("ix_negative_keyword_queue_keyword", "negative_keyword_queue", ["keyword"])


def downgrade() -> None:
    op.drop_table("negative_keyword_queue")
