"""hr shared tables (audit log + role assignments)

Revision ID: 096_hr_shared_tables
Revises: 095
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID


revision = "096_hr_shared_tables"
down_revision = "095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("actor_ip", INET(), nullable=True),
        sa.Column("actor_user_agent", sa.Text(), nullable=True),
        sa.Column("actor_location", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_hr_audit_log_entity",
        "hr_audit_log",
        ["entity_type", "entity_id", "created_at"],
    )
    op.create_index(
        "ix_hr_audit_log_actor",
        "hr_audit_log",
        ["actor_user_id", "created_at"],
    )

    op.create_table(
        "hr_role_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_hr_role_assignments_active",
        "hr_role_assignments",
        ["role", "active", "priority"],
    )


def downgrade() -> None:
    op.drop_index("ix_hr_role_assignments_active", table_name="hr_role_assignments")
    op.drop_table("hr_role_assignments")
    op.drop_index("ix_hr_audit_log_actor", table_name="hr_audit_log")
    op.drop_index("ix_hr_audit_log_entity", table_name="hr_audit_log")
    op.drop_table("hr_audit_log")
