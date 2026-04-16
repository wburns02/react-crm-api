"""hr workflow engine tables (templates, instances, tasks, deps, comments, attachments)

Revision ID: 097_hr_workflow_tables
Revises: 096_hr_shared_tables
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "097_hr_workflow_tables"
down_revision = "096_hr_shared_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_workflow_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "hr_workflow_template_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("assignee_role", sa.String(32), nullable=False),
        sa.Column("due_offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", sa.JSON(), nullable=True),
    )

    op.create_table(
        "hr_workflow_template_dependencies",
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "depends_on_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "hr_workflow_instances",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("template_id", UUID(as_uuid=True), sa.ForeignKey("hr_workflow_templates.id"), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("subject_type", sa.String(32), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("started_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
    )

    op.create_table(
        "hr_workflow_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "instance_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_task_id", UUID(as_uuid=True), sa.ForeignKey("hr_workflow_template_tasks.id"), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(64), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("assignee_user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("assignee_subject_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assignee_role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="blocked"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("completed_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_hr_workflow_tasks_instance_status",
        "hr_workflow_tasks",
        ["instance_id", "status"],
    )
    op.create_index(
        "ix_hr_workflow_tasks_assignee_open",
        "hr_workflow_tasks",
        ["assignee_user_id", "status"],
    )

    op.create_table(
        "hr_workflow_task_dependencies",
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "depends_on_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "hr_workflow_task_comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_workflow_task_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(256), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_workflow_task_attachments")
    op.drop_table("hr_workflow_task_comments")
    op.drop_table("hr_workflow_task_dependencies")
    op.drop_index("ix_hr_workflow_tasks_assignee_open", table_name="hr_workflow_tasks")
    op.drop_index("ix_hr_workflow_tasks_instance_status", table_name="hr_workflow_tasks")
    op.drop_table("hr_workflow_tasks")
    op.drop_table("hr_workflow_instances")
    op.drop_table("hr_workflow_template_dependencies")
    op.drop_table("hr_workflow_template_tasks")
    op.drop_table("hr_workflow_templates")
