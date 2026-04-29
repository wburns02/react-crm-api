"""interaction_insights — weekly Opus 4.7 strategist output cache.

Creates a single table to store the weekly strategy report so the
Sunday 6am CT scheduler doesn't re-run an expensive Opus call on every
page view.

See docs/AI_INTERACTION_ANALYZER_BUILD_PROMPT.md, Tier 3 — Weekly
Strategist for design.

Revision ID: 118
Revises: 117
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "118"
down_revision = "117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interaction_insights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("iso_week", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("total_interactions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "by_channel",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("report_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "report_json",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("thinking_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_interaction_insights_iso_week",
        "interaction_insights",
        ["iso_week"],
        unique=True,
    )
    op.create_index(
        "ix_interaction_insights_end_date_desc",
        "interaction_insights",
        [sa.text("end_date DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_insights_end_date_desc", table_name="interaction_insights")
    op.drop_index("ix_interaction_insights_iso_week", table_name="interaction_insights")
    op.drop_table("interaction_insights")
