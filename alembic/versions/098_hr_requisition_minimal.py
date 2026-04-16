"""hr requisition table (minimal schema for careers page)

Revision ID: 098_hr_requisition_minimal
Revises: 097_hr_workflow_tables
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "098_hr_requisition_minimal"
down_revision = "097_hr_workflow_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_requisitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("department", sa.String(128), nullable=True),
        sa.Column("location_city", sa.String(128), nullable=True),
        sa.Column("location_state", sa.String(32), nullable=True),
        sa.Column("employment_type", sa.String(32), nullable=False, server_default="full_time"),
        sa.Column("compensation_min", sa.Numeric(10, 2), nullable=True),
        sa.Column("compensation_max", sa.Numeric(10, 2), nullable=True),
        sa.Column("compensation_display", sa.String(64), nullable=True),
        sa.Column("description_md", sa.Text(), nullable=True),
        sa.Column("requirements_md", sa.Text(), nullable=True),
        sa.Column("benefits_md", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("opened_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("hiring_manager_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column(
            "onboarding_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_templates.id"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_hr_requisitions_status", "hr_requisitions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_hr_requisitions_status", table_name="hr_requisitions")
    op.drop_table("hr_requisitions")
