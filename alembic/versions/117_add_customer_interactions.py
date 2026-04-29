"""customer_interactions — AI-analyzed unified cross-channel timeline.

Creates three tables for the AI Interaction Analyzer:
  - customer_interactions: one row per call/voicemail/sms/email/chat
  - interaction_action_items: extracted action items (one→many)
  - interaction_analysis_runs: audit log of every Claude/Deepgram model call

See docs/AI_INTERACTION_ANALYZER_BUILD_PROMPT.md for design.

Revision ID: 117
Revises: 116
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    interaction_channel = sa.Enum(
        "call",
        "voicemail",
        "sms",
        "email",
        "chat",
        name="interaction_channel",
        create_type=True,
    )
    interaction_direction = sa.Enum(
        "inbound",
        "outbound",
        name="interaction_direction",
        create_type=True,
    )
    interaction_provider = sa.Enum(
        "ringcentral",
        "twilio",
        "brevo",
        "microsoft365",
        "website_chat",
        name="interaction_provider",
        create_type=True,
    )
    action_item_status = sa.Enum(
        "open",
        "done",
        "dismissed",
        name="action_item_status",
        create_type=True,
    )
    analysis_run_tier = sa.Enum(
        "triage",
        "reply",
        "strategy",
        name="analysis_run_tier",
        create_type=True,
    )
    analysis_run_status = sa.Enum(
        "ok",
        "error",
        "timeout",
        name="analysis_run_status",
        create_type=True,
    )

    op.create_table(
        "customer_interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("external_id", sa.Text(), nullable=False, unique=True),
        sa.Column("channel", interaction_channel, nullable=False),
        sa.Column("direction", interaction_direction, nullable=False),
        sa.Column("provider", interaction_provider, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("from_address", sa.Text(), nullable=False),
        sa.Column("to_address", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_uri", sa.Text(), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "analysis",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("suggested_reply", sa.Text(), nullable=True),
        sa.Column("analysis_model", sa.Text(), nullable=True),
        sa.Column("analysis_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "analysis_cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "hot_lead_score",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("sentiment", sa.Text(), nullable=True),
        sa.Column("urgency", sa.Text(), nullable=True),
        sa.Column(
            "do_not_contact",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_customer_interactions_customer_occurred",
        "customer_interactions",
        ["customer_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_customer_interactions_hot_lead_score",
        "customer_interactions",
        [sa.text("hot_lead_score DESC")],
        postgresql_where=sa.text("hot_lead_score >= 70"),
    )
    op.create_index(
        "ix_customer_interactions_do_not_contact",
        "customer_interactions",
        ["do_not_contact"],
        postgresql_where=sa.text("do_not_contact = TRUE"),
    )
    op.create_index(
        "ix_customer_interactions_channel_occurred",
        "customer_interactions",
        ["channel", "occurred_at"],
    )
    op.create_index(
        "ix_customer_interactions_external_id",
        "customer_interactions",
        ["external_id"],
        unique=True,
    )

    op.create_table(
        "interaction_action_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "interaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_interactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            action_item_status,
            nullable=False,
            server_default="open",
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            onupdate=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_interaction_action_items_interaction_id",
        "interaction_action_items",
        ["interaction_id"],
    )
    op.create_index(
        "ix_interaction_action_items_status",
        "interaction_action_items",
        ["status"],
    )

    op.create_table(
        "interaction_analysis_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "interaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_interactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tier", analysis_run_tier, nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cache_read_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cache_write_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "cost_usd",
            sa.Numeric(10, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "duration_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", analysis_run_status, nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_interaction_analysis_runs_interaction_id",
        "interaction_analysis_runs",
        ["interaction_id"],
    )
    op.create_index(
        "ix_interaction_analysis_runs_created_at",
        "interaction_analysis_runs",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_interaction_analysis_runs_tier_status",
        "interaction_analysis_runs",
        ["tier", "status"],
    )


def downgrade() -> None:
    # Drop tables (FKs first via CASCADE on table drop)
    op.drop_table("interaction_analysis_runs")
    op.drop_table("interaction_action_items")
    op.drop_table("customer_interactions")

    # Then drop ENUM types
    op.execute("DROP TYPE IF EXISTS analysis_run_status")
    op.execute("DROP TYPE IF EXISTS analysis_run_tier")
    op.execute("DROP TYPE IF EXISTS action_item_status")
    op.execute("DROP TYPE IF EXISTS interaction_provider")
    op.execute("DROP TYPE IF EXISTS interaction_direction")
    op.execute("DROP TYPE IF EXISTS interaction_channel")
