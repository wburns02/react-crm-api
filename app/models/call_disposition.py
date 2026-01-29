"""CallDisposition model for categorizing call outcomes."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean
from sqlalchemy.sql import func

from app.database import Base


class CallDisposition(Base):
    """Call disposition for categorizing call outcomes.

    Common dispositions:
    - answered: Call was answered
    - voicemail: Left voicemail
    - no_answer: No answer
    - busy: Line was busy
    - callback_requested: Customer requested callback
    - appointment_set: Appointment scheduled
    - quote_given: Quote provided
    - not_interested: Customer not interested
    - wrong_number: Wrong number
    """

    __tablename__ = "call_dispositions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)

    # Disposition details
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True, default="#6B7280")  # Hex color for UI

    # Status
    is_active = Column(Boolean, default=True, index=True)
    is_default = Column(Boolean, default=False)  # Default disposition for new calls

    # Ordering
    display_order = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CallDisposition {self.name}>"
