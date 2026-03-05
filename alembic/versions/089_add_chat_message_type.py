"""Add 'chat' to messagetype ENUM for Brevo Conversations live chat.

Revision ID: 089
Revises: 088
Create Date: 2026-03-05
"""
from alembic import op

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TYPE messagetype ADD VALUE IF NOT EXISTS 'chat'")


def downgrade():
    # PostgreSQL does not support removing ENUM values; no-op
    pass
