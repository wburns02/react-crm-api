"""
Booking model for direct book & pay services.
"""

import uuid
from sqlalchemy import Column, String, Integer, Date, Time, Numeric, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class Booking(Base):
    """Booking model for pre-paid service appointments."""

    __tablename__ = "bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    work_order_id = Column(UUID(as_uuid=True), ForeignKey("work_orders.id"), nullable=True)

    # Customer info (for non-registered customers)
    customer_first_name = Column(String(100), nullable=False)
    customer_last_name = Column(String(100), nullable=False)
    customer_email = Column(String(255))
    customer_phone = Column(String(20), nullable=False)
    service_address = Column(Text)

    # Service details
    service_type = Column(String(50), nullable=False, default="pumping")
    scheduled_date = Column(Date, nullable=False)
    time_window_start = Column(Time)
    time_window_end = Column(Time)
    time_slot = Column(String(20))  # morning, afternoon, any

    # Pricing
    base_price = Column(Numeric(10, 2), nullable=False)  # 575.00
    included_gallons = Column(Integer, nullable=False, default=1750)
    overage_rate = Column(Numeric(10, 4), nullable=False, default=0.45)

    # Actual service (filled after completion)
    actual_gallons = Column(Integer)
    overage_gallons = Column(Integer)
    overage_amount = Column(Numeric(10, 2))
    final_amount = Column(Numeric(10, 2))

    # Payment
    clover_charge_id = Column(String(100))
    preauth_amount = Column(Numeric(10, 2))
    payment_status = Column(String(20), default="pending")
    # pending, preauthorized, captured, refunded, failed, test
    captured_at = Column(DateTime(timezone=True))

    # Test mode
    is_test = Column(Boolean, default=False)

    # Status
    status = Column(String(20), default="confirmed")
    # confirmed, in_progress, completed, cancelled

    # Consent
    overage_acknowledged = Column(Boolean, default=False)
    sms_consent = Column(Boolean, default=False)

    # Notes
    customer_notes = Column(Text)
    internal_notes = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="bookings", foreign_keys=[customer_id])

    def __repr__(self):
        return f"<Booking {self.id} - {self.service_type} on {self.scheduled_date}>"

    def calculate_final_amount(self) -> tuple[Numeric, Numeric, Numeric]:
        """
        Calculate final amount based on actual gallons pumped.

        Returns:
            tuple: (final_amount, overage_gallons, overage_amount)
        """
        if self.actual_gallons is None:
            return self.base_price, 0, 0

        overage_gal = max(0, self.actual_gallons - self.included_gallons)
        overage_amt = overage_gal * float(self.overage_rate)
        final = float(self.base_price) + overage_amt

        return final, overage_gal, overage_amt
