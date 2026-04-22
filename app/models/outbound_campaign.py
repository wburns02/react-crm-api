"""Outbound Dialer campaign persistence models."""

import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class OutboundCampaign(Base):
    __tablename__ = "outbound_campaigns"

    id = Column(Text, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="draft")
    source_file = Column(Text, nullable=True)
    source_sheet = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    contacts = relationship(
        "OutboundCampaignContact",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )


class OutboundCampaignContact(Base):
    __tablename__ = "outbound_campaign_contacts"

    id = Column(Text, primary_key=True)
    campaign_id = Column(
        Text,
        ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_number = Column(String(100), nullable=True)
    account_name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    phone = Column(String(32), nullable=False)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(8), nullable=True)
    zip_code = Column(String(16), nullable=True)
    service_zone = Column(String(100), nullable=True)
    system_type = Column(String(100), nullable=True)
    contract_type = Column(String(50), nullable=True)
    contract_status = Column(String(50), nullable=True)
    contract_start = Column(Date, nullable=True)
    contract_end = Column(Date, nullable=True)
    contract_value = Column(Numeric(12, 2), nullable=True)
    customer_type = Column(String(50), nullable=True)
    call_priority_label = Column(String(50), nullable=True)
    call_status = Column(String(32), nullable=False, default="pending")
    call_attempts = Column(Integer, nullable=False, default=0)
    last_call_date = Column(DateTime(timezone=True), nullable=True)
    last_call_duration = Column(Integer, nullable=True)
    last_disposition = Column(String(32), nullable=True)
    notes = Column(Text, nullable=True)
    callback_date = Column(DateTime(timezone=True), nullable=True)
    assigned_rep = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    opens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    campaign = relationship("OutboundCampaign", back_populates="contacts")

    __table_args__ = (
        Index("ix_outbound_contacts_campaign_status", "campaign_id", "call_status"),
        Index("ix_outbound_contacts_phone", "phone"),
    )


class OutboundCallAttempt(Base):
    __tablename__ = "outbound_call_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(
        Text,
        ForeignKey("outbound_campaign_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id = Column(
        Text,
        ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    rep_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    dispositioned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    call_status = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)
    duration_sec = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_outbound_attempts_contact_time", "contact_id", "dispositioned_at"),
        Index("ix_outbound_attempts_rep_time", "rep_user_id", "dispositioned_at"),
    )


class OutboundCallback(Base):
    __tablename__ = "outbound_callbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(
        Text,
        ForeignKey("outbound_campaign_contacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    campaign_id = Column(
        Text,
        ForeignKey("outbound_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    rep_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    scheduled_for = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="scheduled")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_outbound_callbacks_sched", "scheduled_for", "status"),)
