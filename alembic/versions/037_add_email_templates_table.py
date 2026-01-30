"""Add email_templates table

Revision ID: 037_email_templates
Revises: 036_messages_columns
Create Date: 2026-01-30

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "037_email_templates"
down_revision = "036_messages_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create email_templates table."""
    conn = op.get_bind()

    # Check if table already exists
    result = conn.execute(
        sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'email_templates'
        )
    """)
    )
    exists = result.scalar()

    if not exists:
        op.create_table(
            "email_templates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("subject", sa.String(255), nullable=False),
            sa.Column("body_html", sa.Text, nullable=False),
            sa.Column("body_text", sa.Text, nullable=True),
            sa.Column("variables", postgresql.JSON, nullable=True),
            sa.Column("category", sa.String(50), nullable=True, index=True),
            sa.Column("is_active", sa.Boolean, default=True, index=True),
            sa.Column("created_by", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

        # Create index on name for faster lookups
        op.create_index("ix_email_templates_name", "email_templates", ["name"])


def downgrade() -> None:
    """Drop email_templates table."""
    op.drop_table("email_templates")
