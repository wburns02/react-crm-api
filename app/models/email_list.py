"""Email Marketing Lists and Subscribers models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    DateTime,
    Text,
    Boolean,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class EmailList(Base):
    """Email marketing list for organizing subscribers."""

    __tablename__ = "email_lists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String(50), nullable=False, default="manual")  # manual, permit_import, crm_sync
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    subscribers = relationship(
        "EmailSubscriber",
        back_populates="email_list",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<EmailList(id={self.id}, name={self.name})>"


class EmailSubscriber(Base):
    """Subscriber in an email marketing list."""

    __tablename__ = "email_subscribers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    list_id = Column(
        UUID(as_uuid=True),
        ForeignKey("email_lists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(String(255), nullable=False, index=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    source = Column(String(50), nullable=False, default="manual")  # manual, permit, customer
    status = Column(String(20), nullable=False, default="active")  # active, unsubscribed, bounced, complained
    subscribed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    unsubscribed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)  # extra data (county, permit_number, etc.)

    # Relationships
    email_list = relationship("EmailList", back_populates="subscribers")

    __table_args__ = (
        UniqueConstraint("list_id", "email", name="uq_email_subscriber_list_email"),
        Index("idx_email_subscribers_list_status", "list_id", "status"),
        Index("idx_email_subscribers_email", "email"),
    )

    def __repr__(self):
        return f"<EmailSubscriber(id={self.id}, email={self.email}, list_id={self.list_id})>"
