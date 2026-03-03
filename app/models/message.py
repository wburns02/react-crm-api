from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
import uuid
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
    """Message model for communications (SMS, email, etc.).

    Note: DB uses PostgreSQL ENUM types for type/direction/status (migration 036).
    The 'type' column is accessed as 'message_type' in Python to avoid conflicts.
    """

    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True)
    work_order_id = Column(UUID(as_uuid=True), nullable=True)

    # Type, direction, status - PostgreSQL ENUM types (migration 036)
    # DB column is "type", accessed as "message_type" in Python
    message_type = Column(
        "type",
        PG_ENUM("sms", "email", "call", "note", name="messagetype", create_type=False),
        nullable=False,
    )
    direction = Column(
        PG_ENUM("inbound", "outbound", name="messagedirection", create_type=False),
        nullable=False,
    )
    status = Column(
        PG_ENUM("pending", "queued", "sent", "delivered", "failed", "received", name="messagestatus", create_type=False),
    )

    # Phone numbers (for SMS)
    from_number = Column(String(50))
    to_number = Column(String(50))

    # Email addresses (for email)
    from_email = Column(String(255))
    to_email = Column(String(255))

    # Content
    subject = Column(String(500))  # For emails
    content = Column(Text)

    # Template tracking
    template_id = Column(String(100))

    # Campaign tracking
    campaign_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # External service ID (Twilio SID, SendGrid ID, etc.)
    external_id = Column(String(100))
    error_message = Column(Text)

    # Timestamps
    sent_at = Column(DateTime(timezone=True))
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="messages")

    # Convenience properties to maintain backwards compatibility
    @property
    def type(self) -> MessageType | None:
        """Get message type as enum."""
        if self.message_type:
            try:
                return MessageType(self.message_type)
            except ValueError:
                return None
        return None

    @property
    def to_address(self) -> str | None:
        """Get recipient address (phone or email)."""
        return self.to_number or self.to_email

    @property
    def from_address(self) -> str | None:
        """Get sender address (phone or email)."""
        return self.from_number or self.from_email

    @property
    def twilio_sid(self) -> str | None:
        """Alias for external_id (backwards compatibility)."""
        return self.external_id

    def __repr__(self):
        return f"<Message {self.id} - {self.message_type} - {self.status}>"
