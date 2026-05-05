"""Realtor Pipeline persistence models.

Matches the frontend's `RealtorAgent` and `Referral` types in
`ReactCRM/src/features/realtor-pipeline/types.ts`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class RealtorAgent(Base):
    __tablename__ = "realtor_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Identity
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    brokerage = Column(String(255), nullable=True)
    license_number = Column(String(50), nullable=True)

    # Contact
    phone = Column(String(20), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    cell = Column(String(20), nullable=True)
    preferred_contact = Column(String(20), nullable=False, default="call")

    # Location
    coverage_area = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(8), nullable=True)
    zip_code = Column(String(16), nullable=True)

    # Relationship
    stage = Column(String(32), nullable=False, default="cold", index=True)
    current_inspector = Column(String(100), nullable=True)
    relationship_notes = Column(Text, nullable=True)

    # Call tracking
    call_attempts = Column(Integer, nullable=False, default=0)
    last_call_date = Column(DateTime(timezone=True), nullable=True)
    last_call_duration = Column(Integer, nullable=True)
    last_disposition = Column(String(40), nullable=True)
    next_follow_up = Column(DateTime(timezone=True), nullable=True)

    # Referral aggregates (denormalized for fast reads)
    total_referrals = Column(Integer, nullable=False, default=0)
    total_revenue = Column(Numeric(12, 2), nullable=False, default=0)
    last_referral_date = Column(DateTime(timezone=True), nullable=True)

    # Documents
    one_pager_sent = Column(Boolean, nullable=False, default=False)
    one_pager_sent_date = Column(DateTime(timezone=True), nullable=True)

    # Meta
    assigned_rep = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    priority = Column(Integer, nullable=False, default=50)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())

    referrals = relationship(
        "RealtorReferral",
        back_populates="realtor",
        cascade="all, delete-orphan",
    )


class RealtorReferral(Base):
    __tablename__ = "realtor_referrals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    realtor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("realtor_agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    property_address = Column(String(500), nullable=False)
    homeowner_name = Column(String(200), nullable=True)
    service_type = Column(String(40), nullable=False, default="inspection")

    invoice_amount = Column(Numeric(12, 2), nullable=True)
    status = Column(String(20), nullable=False, default="pending", index=True)

    referred_date = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_date = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, onupdate=func.now())

    realtor = relationship("RealtorAgent", back_populates="referrals")
