from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Payment(Base):
    """Payment model for tracking invoice payments."""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50))  # cash, check, credit_card, ach, other
    payment_date = Column(DateTime(timezone=True), server_default=func.now())
    reference_number = Column(String(100))  # Check number, transaction ID, etc.

    # Status
    status = Column(String(20), default="completed")  # pending, completed, failed, refunded

    # Notes
    notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    invoice = relationship("Invoice", backref="payments")
    customer = relationship("Customer", backref="payments")

    def __repr__(self):
        return f"<Payment {self.id} ${self.amount}>"
