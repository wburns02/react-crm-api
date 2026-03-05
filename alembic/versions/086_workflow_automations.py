"""Add workflow_automations and workflow_executions tables.

Revision ID: 086
Revises: 085
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_automations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), sa.ForeignKey("company_entities.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("trigger_config", JSON, server_default="{}"),
        sa.Column("nodes", JSON, server_default="[]"),
        sa.Column("edges", JSON, server_default="[]"),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("run_count", sa.Integer, server_default="0"),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "workflow_executions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflow_automations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_event", JSON, nullable=True),
        sa.Column("steps_executed", JSON, server_default="[]"),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_index("ix_workflow_automations_status", "workflow_automations", ["status"])
    op.create_index("ix_workflow_automations_trigger_type", "workflow_automations", ["trigger_type"])
    op.create_index("ix_workflow_executions_workflow_id", "workflow_executions", ["workflow_id"])


def downgrade() -> None:
    op.drop_index("ix_workflow_executions_workflow_id")
    op.drop_index("ix_workflow_automations_trigger_type")
    op.drop_index("ix_workflow_automations_status")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_automations")
