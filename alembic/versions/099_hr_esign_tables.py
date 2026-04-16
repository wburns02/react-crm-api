"""hr e-sign tables (document templates, signature requests, signed documents, events)

Revision ID: 099
Revises: 098
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID


revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_document_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.String(64), nullable=False, unique=True),
        sa.Column("version", sa.String(32), nullable=False, server_default="1"),
        sa.Column("pdf_storage_key", sa.String(512), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hr_signature_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("signer_email", sa.String(256), nullable=False),
        sa.Column("signer_name", sa.String(256), nullable=False),
        sa.Column("signer_user_id", sa.Integer(), sa.ForeignKey("api_users.id"), nullable=True),
        sa.Column(
            "document_template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_document_templates.id"),
            nullable=False,
        ),
        sa.Column("field_values", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="sent"),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("viewed_at", sa.DateTime(), nullable=True),
        sa.Column("signed_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "workflow_task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_workflow_tasks.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_hr_sig_requests_status", "hr_signature_requests", ["status"])

    op.create_table(
        "hr_signed_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "signature_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_signature_requests.id"),
            nullable=False,
        ),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("signer_ip", INET(), nullable=True),
        sa.Column("signer_user_agent", sa.Text(), nullable=True),
        sa.Column("signature_image_key", sa.String(512), nullable=False),
        sa.Column("signed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("hash_sha256", sa.String(64), nullable=False),
    )

    op.create_table(
        "hr_signature_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "signature_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hr_signature_requests.id"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("ip", INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("hr_signature_events")
    op.drop_table("hr_signed_documents")
    op.drop_index("ix_hr_sig_requests_status", table_name="hr_signature_requests")
    op.drop_table("hr_signature_requests")
    op.drop_table("hr_document_templates")
