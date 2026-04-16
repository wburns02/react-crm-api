"""hr applicant + application + event + message-template tables

Revision ID: 101
Revises: 100
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID


revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_applicants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(256), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("resume_storage_key", sa.String(512), nullable=True),
        sa.Column("resume_parsed", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False, server_default="careers_page"),
        sa.Column("source_ref", sa.String(256), nullable=True),
        sa.Column("sms_consent_given", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sms_consent_ip", INET(), nullable=True),
        sa.Column("sms_consent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_hr_applicants_email", "hr_applicants", ["email"])
    op.create_index("ix_hr_applicants_created_at", "hr_applicants", ["created_at"])

    op.create_table(
        "hr_applications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "applicant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_applicants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requisition_id", UUID(as_uuid=True), sa.ForeignKey("hr_requisitions.id"), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False, server_default="applied"),
        sa.Column("stage_entered_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("assigned_recruiter_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("rejection_reason", sa.String(256), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("applicant_id", "requisition_id", name="uq_hr_applications_applicant_req"),
    )
    op.create_index("ix_hr_applications_requisition_stage", "hr_applications", ["requisition_id", "stage"])
    op.create_index("ix_hr_applications_stage", "hr_applications", ["stage"])

    op.create_table(
        "hr_application_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_hr_application_events_application_created",
        "hr_application_events",
        ["application_id", "created_at"],
    )

    op.create_table(
        "hr_recruiting_message_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("stage", sa.String(16), nullable=False, unique=True),
        sa.Column("channel", sa.String(16), nullable=False, server_default="sms"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_recruiting_message_templates")
    op.drop_index("ix_hr_application_events_application_created", table_name="hr_application_events")
    op.drop_table("hr_application_events")
    op.drop_index("ix_hr_applications_stage", table_name="hr_applications")
    op.drop_index("ix_hr_applications_requisition_stage", table_name="hr_applications")
    op.drop_table("hr_applications")
    op.drop_index("ix_hr_applicants_created_at", table_name="hr_applicants")
    op.drop_index("ix_hr_applicants_email", table_name="hr_applicants")
    op.drop_table("hr_applicants")
