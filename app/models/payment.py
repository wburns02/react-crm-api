from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid as uuid_module


class Payment(Base):
    """Payment model."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id", ondelete="SET NULL"), nullable=True, index=True)

    # Invoice reference (UUID to match invoices.id)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)

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
    payment_date = Column(DateTime)  # When payment was completed

    # Multi-entity (LLC) support
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True, index=True)

    customer = relationship("Customer", foreign_keys=[customer_id], lazy="selectin")

    def __repr__(self):
        return f"<Payment {self.id} ${self.amount}>"
