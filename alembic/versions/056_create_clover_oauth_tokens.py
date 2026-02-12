"""Create clover_oauth_tokens table for OAuth 2.0 token storage.

Revision ID: 056
Revises: 055
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clover_oauth_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("merchant_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(20), server_default="Bearer"),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("merchant_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("connected_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("clover_oauth_tokens")
