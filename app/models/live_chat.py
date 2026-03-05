"""Live Chat models for custom chat widget on macseptic.com."""

from sqlalchemy import Column, String, DateTime, Text, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ChatConversation(Base):
    """A live chat conversation initiated by a website visitor."""

    __tablename__ = "chat_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visitor_name = Column(String(255), nullable=True)
    visitor_email = Column(String(255), nullable=True)
    visitor_phone = Column(String(50), nullable=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), default="active")  # active, closed, archived
    assigned_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)  # browser info, page URL, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)

    messages = relationship("ChatMessage", back_populates="conversation", order_by="ChatMessage.created_at")

    def __repr__(self):
        return f"<ChatConversation {self.id} status={self.status}>"


class ChatMessage(Base):
    """A single message within a live chat conversation."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("chat_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_type = Column(String(20), nullable=False)  # "visitor" or "agent"
    sender_name = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("ChatConversation", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id} sender={self.sender_type}>"
