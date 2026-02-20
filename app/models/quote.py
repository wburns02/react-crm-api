from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Numeric, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class Quote(Base):
    """Quote model for customer quotes/estimates."""

    __tablename__ = "quotes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    quote_number = Column(String(50), unique=True, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Quote details
    title = Column(String(255))
    description = Column(Text)

    # Line items stored as JSON array
    # [{service: str, description: str, quantity: float, rate: float, amount: float}]
    line_items = Column(JSON, default=list)

    # Totals
    subtotal = Column(Numeric(10, 2), default=0)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax = Column(Numeric(10, 2), default=0)
    discount = Column(Numeric(10, 2), default=0)
    total = Column(Numeric(10, 2), default=0)

    # Status
    status = Column(String(30), default="draft")  # draft, sent, viewed, accepted, rejected, expired, converted

    # Validity
    valid_until = Column(DateTime(timezone=True))

    # E-signature
    signature_data = Column(Text)  # Base64 encoded signature image
    signed_at = Column(DateTime(timezone=True))
    signed_by = Column(String(150))

    # Approval workflow
    approval_status = Column(String(30))  # pending, approved, rejected
    approved_by = Column(String(100))
    approved_at = Column(DateTime(timezone=True))

    # Conversion tracking
    converted_to_work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True)
    converted_at = Column(DateTime(timezone=True))

    # Notes
    notes = Column(Text)
    terms = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    sent_at = Column(DateTime(timezone=True))

    customer = relationship("Customer", foreign_keys=[customer_id], lazy="selectin")

    def __repr__(self):
        return f"<Quote {self.quote_number}>"

    def calculate_totals(self):
        """Calculate subtotal, tax, and total from line items."""
        if self.line_items:
            self.subtotal = sum(item.get("amount", 0) for item in self.line_items)
        else:
            self.subtotal = 0
        self.tax = float(self.subtotal) * float(self.tax_rate or 0) / 100
        self.total = float(self.subtotal) + float(self.tax) - float(self.discount or 0)
