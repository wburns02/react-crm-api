from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Payment(Base):
    """Payment model - matches existing Flask database schema.

    NOTE: Flask database uses:
    - Integer for id and customer_id
    - VARCHAR for work_order_id (not invoice_id)
    - Includes Stripe integration fields
    """

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    work_order_id = Column(String(36), ForeignKey("work_orders.id"), nullable=True, index=True)

    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="USD")
    payment_method = Column(String(50))  # card, cash, check, ach, etc.
    status = Column(String(30), default="pending")  # pending, completed, failed, refunded

    # Stripe integration
    stripe_payment_intent_id = Column(String(255))
    stripe_charge_id = Column(String(255))
    stripe_customer_id = Column(String(255))

    # Additional info
    description = Column(Text)
    receipt_url = Column(String(500))
    failure_reason = Column(Text)

    # Refund tracking
    refund_amount = Column(Numeric(10, 2))
    refund_reason = Column(Text)
    refunded = Column(Boolean, default=False)
    refund_id = Column(String(255))
    refunded_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    processed_at = Column(DateTime)

    # Relationships
    customer = relationship("Customer", backref="payments")

    def __repr__(self):
        return f"<Payment {self.id} ${self.amount}>"
