from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid


class InboundEmail(Base):
    """Inbound email parsed from monitored mailbox."""

    __tablename__ = "inbound_emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(String(500), unique=True, nullable=False)
    sender_email = Column(String(255), nullable=False, index=True)
    sender_name = Column(String(255))
    subject = Column(String(500))
    body_preview = Column(Text)
    received_at = Column(DateTime(timezone=True), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    action_taken = Column(String(50), default="none")
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<InboundEmail {self.sender_email}: {self.subject}>"
