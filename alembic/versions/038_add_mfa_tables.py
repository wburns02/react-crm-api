"""Add MFA tables for multi-factor authentication

Revision ID: 038_add_mfa_tables
Revises: 037_add_email_templates_table
Create Date: 2026-01-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "038_add_mfa_tables"
down_revision: Union[str, None] = "037_add_email_templates_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create user_mfa_settings table
    op.create_table(
        "user_mfa_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # TOTP Configuration
        sa.Column("totp_secret", sa.String(32), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("totp_verified", sa.Boolean(), server_default="false", nullable=False),
        # MFA Status
        sa.Column("mfa_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("mfa_enforced", sa.Boolean(), server_default="false", nullable=False),
        # Backup codes tracking
        sa.Column("backup_codes_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("backup_codes_generated_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["api_users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_mfa_settings_id", "user_mfa_settings", ["id"])
    op.create_index("ix_user_mfa_settings_user_id", "user_mfa_settings", ["user_id"])

    # Create user_backup_codes table
    op.create_table(
        "user_backup_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("mfa_settings_id", sa.Integer(), nullable=False),
        # Hashed backup code
        sa.Column("code_hash", sa.String(255), nullable=False),
        # Usage tracking
        sa.Column("used", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["api_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mfa_settings_id"], ["user_mfa_settings.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_backup_codes_id", "user_backup_codes", ["id"])
    op.create_index("ix_backup_codes_user", "user_backup_codes", ["user_id"])

    # Create mfa_sessions table
    op.create_table(
        "mfa_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        # Session token (hashed)
        sa.Column("session_token_hash", sa.String(255), nullable=False),
        # Challenge tracking
        sa.Column("challenge_type", sa.String(20), server_default="totp", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        # Validity
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["api_users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("session_token_hash"),
    )
    op.create_index("ix_mfa_sessions_id", "mfa_sessions", ["id"])
    op.create_index("ix_mfa_sessions_user_id", "mfa_sessions", ["user_id"])
    op.create_index("ix_mfa_sessions_token_hash", "mfa_sessions", ["session_token_hash"])
    op.create_index("ix_mfa_sessions_expires_at", "mfa_sessions", ["expires_at"])


def downgrade() -> None:
    # Drop tables in reverse order (foreign key dependencies)
    op.drop_table("mfa_sessions")
    op.drop_table("user_backup_codes")
    op.drop_table("user_mfa_settings")
