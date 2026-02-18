"""Create AI provider config and usage tracking tables.

Revision ID: 062
Revises: 061
Create Date: 2026-02-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def table_exists(table_name):
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade():
    if not table_exists("ai_provider_config"):
        op.create_table(
            "ai_provider_config",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(50), nullable=False, unique=True, index=True),
            sa.Column("api_key_encrypted", sa.Text, nullable=True),
            sa.Column("is_active", sa.Boolean, default=True, nullable=False),
            sa.Column("is_primary", sa.Boolean, default=False, nullable=False),
            sa.Column("model_config_data", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("feature_config", sa.JSON, nullable=False, server_default="{}"),
            sa.Column("connected_by", sa.String(255), nullable=True),
            sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not table_exists("ai_usage_logs"):
        op.create_table(
            "ai_usage_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("provider", sa.String(50), nullable=False, index=True),
            sa.Column("model", sa.String(100), nullable=False),
            sa.Column("feature", sa.String(50), nullable=False, index=True),
            sa.Column("prompt_tokens", sa.Integer, default=0),
            sa.Column("completion_tokens", sa.Integer, default=0),
            sa.Column("total_tokens", sa.Integer, default=0),
            sa.Column("cost_cents", sa.Integer, default=0),
            sa.Column("user_id", sa.String(100), nullable=True),
            sa.Column("request_duration_ms", sa.Integer, nullable=True),
            sa.Column("success", sa.Boolean, default=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_ai_usage_logs_provider_created", "ai_usage_logs", ["provider", "created_at"])
        op.create_index("ix_ai_usage_logs_feature_created", "ai_usage_logs", ["feature", "created_at"])


def downgrade():
    if table_exists("ai_usage_logs"):
        op.drop_table("ai_usage_logs")
    if table_exists("ai_provider_config"):
        op.drop_table("ai_provider_config")
