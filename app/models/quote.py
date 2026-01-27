"""
SQLAlchemy model for Quotes/Estimates.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Numeric, Boolean, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Quote(Base):
    """Quote model for customer quotes/estimates."""
    __tablename__ = "quotes"

    # Integer primary key (matches existing database schema)
    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(String(50), unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

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

    # Notes
    notes = Column(Text)
    terms = Column(Text)

    # Signature
    signature_data = Column(Text)  # Base64 signature image
    signed_at = Column(DateTime(timezone=True))
    signed_by = Column(String(255))

    # Approval workflow
    approval_status = Column(String(30))  # pending, approved, rejected
    approved_by = Column(Integer)
    approved_at = Column(DateTime(timezone=True))

    # Conversion tracking
    converted_to_work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    converted_at = Column(DateTime(timezone=True))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    sent_at = Column(DateTime(timezone=True))

    # Relationships
    customer = relationship("Customer", backref="quotes")

    def calculate_totals(self):
        """Calculate subtotal, tax, and total from line items."""
        if self.line_items:
            # Calculate subtotal from line items
            subtotal = 0.0
            processed_items = []
            for item in self.line_items:
                quantity = float(item.get('quantity', 0))
                rate = float(item.get('rate', 0))
                amount = round(quantity * rate, 2)
                processed_item = {
                    'service': item.get('service', ''),
                    'description': item.get('description'),
                    'quantity': quantity,
                    'rate': rate,
                    'amount': amount,
                }
                processed_items.append(processed_item)
                subtotal += amount

            self.line_items = processed_items
            self.subtotal = round(subtotal, 2)
            tax_rate = float(self.tax_rate or 0)
            self.tax = round(self.subtotal * (tax_rate / 100), 2)
            self.total = round(self.subtotal + self.tax, 2)
        else:
            self.subtotal = 0.0
            self.tax = 0.0
            self.total = 0.0

    def __repr__(self):
        return f"<Quote(id={self.id}, quote_number={self.quote_number}, status={self.status})>"
