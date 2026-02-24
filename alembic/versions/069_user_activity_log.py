"""User activity log for tracking logins, actions, and usage analytics.

Revision ID: 069
Revises: 068
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_activity_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Who
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("user_email", sa.String(100), nullable=True),
        sa.Column("user_name", sa.String(200), nullable=True),
        # What
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Where
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        # Resource
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("endpoint", sa.String(200), nullable=True),
        sa.Column("http_method", sa.String(10), nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        # Performance
        sa.Column("response_time_ms", sa.Integer, nullable=True),
        # Session
        sa.Column("session_id", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.String(100), nullable=True),
        # When
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Individual indexes
    op.create_index("ix_user_activity_log_user_id", "user_activity_log", ["user_id"])
    op.create_index("ix_user_activity_log_category", "user_activity_log", ["category"])
    op.create_index("ix_user_activity_log_action", "user_activity_log", ["action"])
    op.create_index("ix_user_activity_log_created_at", "user_activity_log", ["created_at"])

    # Composite indexes for common queries
    op.create_index("ix_user_activity_user_created", "user_activity_log", ["user_id", "created_at"])
    op.create_index("ix_user_activity_category_created", "user_activity_log", ["category", "created_at"])
    op.create_index("ix_user_activity_action_created", "user_activity_log", ["action", "created_at"])


def downgrade() -> None:
    op.drop_table("user_activity_log")
