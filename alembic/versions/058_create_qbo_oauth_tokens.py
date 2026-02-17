"""Create qbo_oauth_tokens table for QuickBooks Online integration.

Revision ID: 058
Revises: 057
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from alembic import op

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade():
    # Skip if table was already created manually
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'qbo_oauth_tokens')"
    ))
    if result.scalar():
        return
    op.create_table(
        "qbo_oauth_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("realm_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("token_type", sa.String(20), server_default="Bearer"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("connected_by", sa.String(255), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("qbo_oauth_tokens")
