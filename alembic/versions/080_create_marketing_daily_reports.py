"""create marketing_daily_reports table

Revision ID: 080
Revises: 079
Create Date: 2026-02-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_daily_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("report_date", sa.Date, nullable=False, unique=True),
        sa.Column("ads_data", JSON, nullable=True),
        sa.Column("ga4_data", JSON, nullable=True),
        sa.Column("deltas", JSON, nullable=True),
        sa.Column("alerts", JSON, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("email_sent", sa.Boolean, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_marketing_daily_reports_date", "marketing_daily_reports", ["report_date"])


def downgrade() -> None:
    op.drop_table("marketing_daily_reports")
