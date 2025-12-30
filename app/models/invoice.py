from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Invoice(Base):
    """Invoice model for customer billing."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(String(36), nullable=True, index=True)  # UUID string like work_orders.id

    status = Column(String(20), default="draft", nullable=False)

    # Line items stored as JSON array
    # Each item: {service, description, quantity, rate, amount}
    line_items = Column(JSON, default=list)

    # Calculated totals
    subtotal = Column(Float, default=0)
    tax_rate = Column(Float, default=0)  # Percentage (e.g., 8.25 for 8.25%)
    tax = Column(Float, default=0)
    total = Column(Float, default=0)

    # Dates
    due_date = Column(String(20))  # ISO date string
    paid_date = Column(String(20))  # ISO date string

    # Additional info
    notes = Column(Text)
    terms = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="invoices")
    work_order = relationship("WorkOrder", backref="invoices")

    def __repr__(self):
        return f"<Invoice {self.invoice_number}>"

    def calculate_totals(self):
        """Recalculate subtotal, tax, and total from line items."""
        if self.line_items:
            self.subtotal = sum(item.get('amount', 0) for item in self.line_items)
        else:
            self.subtotal = 0
        self.tax = self.subtotal * (self.tax_rate / 100) if self.tax_rate else 0
        self.total = self.subtotal + self.tax
