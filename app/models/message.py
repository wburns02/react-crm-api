from sqlalchemy import Column, Integer, String, DateTime, Text, Enum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class MessageType(str, enum.Enum):
    sms = "sms"
    email = "email"
    call = "call"
    note = "note"


class MessageDirection(str, enum.Enum):
    inbound = "inbound"
    outbound = "outbound"


class MessageStatus(str, enum.Enum):
    pending = "pending"
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    received = "received"


class Message(Base):
    """Message model for communications (SMS, email, etc.)."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True)

    type = Column(Enum(MessageType), nullable=False)
    direction = Column(Enum(MessageDirection), nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.pending)

    # Content
    to_address = Column(String(255))  # Phone number or email
    from_address = Column(String(255))
    subject = Column(String(255))  # For emails
    content = Column(Text, nullable=False)

    # Twilio specific
    twilio_sid = Column(String(100), unique=True, index=True)
    twilio_status = Column(String(50))
    error_code = Column(String(20))
    error_message = Column(Text)

    # Source tracking (for webhook routing)
    source = Column(String(20), default="react")  # 'react' or 'legacy'

    # Timestamps
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="messages")

    def __repr__(self):
        return f"<Message {self.id} - {self.type} - {self.status}>"
