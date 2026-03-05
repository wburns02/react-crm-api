"""Create documents table for PDF generation and storage.

Revision ID: 088
Revises: 087
Create Date: 2026-03-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("document_type", sa.String(50), nullable=False),
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
        sa.Column("reference_number", sa.String(100), nullable=True),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("pdf_data", sa.LargeBinary, nullable=True),
        sa.Column("status", sa.String(30), server_default="draft"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_to", sa.String(255), nullable=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_documents_entity_type", "documents", ["entity_id", "document_type"])
    op.create_index("ix_documents_customer", "documents", ["customer_id"])
    op.create_index("ix_documents_reference", "documents", ["reference_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_reference", table_name="documents")
    op.drop_index("ix_documents_customer", table_name="documents")
    op.drop_index("ix_documents_entity_type", table_name="documents")
    op.drop_table("documents")
