"""Add custom_reports and report_snapshots tables.

Revision ID: 087
Revises: 086
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("company_entities.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("report_type", sa.String(30), server_default="table"),
        sa.Column("data_source", sa.String(50), nullable=False),
        sa.Column("columns", JSON, server_default="[]"),
        sa.Column("filters", JSON, server_default="[]"),
        sa.Column("group_by", JSON, server_default="[]"),
        sa.Column("sort_by", JSON, nullable=True),
        sa.Column("date_range", JSON, nullable=True),
        sa.Column("chart_config", JSON, nullable=True),
        sa.Column("layout", JSON, nullable=True),
        sa.Column("is_favorite", sa.Boolean, server_default="false"),
        sa.Column("is_shared", sa.Boolean, server_default="false"),
        sa.Column("schedule", JSON, nullable=True),
        sa.Column("last_generated_at", sa.DateTime, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "report_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", UUID(as_uuid=True), sa.ForeignKey("custom_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data", JSON, server_default="[]"),
        sa.Column("row_count", sa.Integer, server_default="0"),
        sa.Column("generated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_index("ix_custom_reports_data_source", "custom_reports", ["data_source"])
    op.create_index("ix_custom_reports_created_by", "custom_reports", ["created_by"])
    op.create_index("ix_report_snapshots_report_id", "report_snapshots", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_snapshots_report_id")
    op.drop_index("ix_custom_reports_created_by")
    op.drop_index("ix_custom_reports_data_source")
    op.drop_table("report_snapshots")
    op.drop_table("custom_reports")
