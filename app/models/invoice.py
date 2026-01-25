from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Numeric, JSON, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Invoice(Base):
    """Invoice model - matches existing Flask database schema.

    NOTE: Flask uses UUID for id, customer_id, and work_order_id
    """

    __tablename__ = "invoices"

    # Primary key is UUID, but customer_id references Integer customers.id
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True, index=True)

    invoice_number = Column(String(50), unique=True, index=True)

    # Dates
    issue_date = Column(Date)
    due_date = Column(Date)
    paid_date = Column(Date)

    # Amounts
    amount = Column(Numeric(10, 2))  # Total amount
    paid_amount = Column(Numeric(10, 2))
    currency = Column(String(3), default="USD")

    # Status is a USER-DEFINED type in Flask DB
    status = Column(String(20), default="draft")  # draft, sent, paid, overdue, void

    # Line items stored as JSON
    line_items = Column(JSON, default=list)

    # Additional info
    notes = Column(Text)
    external_payment_link = Column(String(255))
    quickbooks_invoice_id = Column(String(100))

    # PDF
    pdf_url = Column(String(255))
    pdf_generated_at = Column(DateTime)

    # Sending
    last_sent_at = Column(DateTime)
    sent_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships - note: Customer.id is also UUID in Flask
    # We can't define relationship here as Customer model uses Integer id
    # customer = relationship("Customer", backref="invoices")
    # work_order = relationship("WorkOrder", backref="invoices")

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"
