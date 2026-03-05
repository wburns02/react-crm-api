"""Document model for storing generated PDFs (invoices, quotes, work orders, inspection reports)."""

from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, LargeBinary, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    document_type = Column(String(50), nullable=False)  # invoice, quote, work_order, inspection_report
    reference_id = Column(UUID(as_uuid=True), nullable=True)  # FK to source record
    reference_number = Column(String(100), nullable=True)  # INV-2026-0042, QUO-2026-0015
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)  # bytes
    pdf_data = Column(LargeBinary, nullable=True)  # PDF bytes (<500KB each)
    status = Column(String(30), default="draft")  # draft, sent, viewed, signed, expired
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_to = Column(String(255), nullable=True)  # email address
    viewed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_documents_entity_type", "entity_id", "document_type"),
        Index("ix_documents_customer", "customer_id"),
        Index("ix_documents_reference", "reference_id"),
    )
