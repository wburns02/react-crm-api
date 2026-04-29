"""Customer interaction models.

Three tables for the AI Interaction Analyzer:
  - CustomerInteraction: unified cross-channel timeline row
  - InteractionActionItem: extracted action items (one->many)
  - InteractionAnalysisRun: per-model-call audit log

See alembic/versions/117_add_customer_interactions.py for the schema.
"""
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# Re-use the Postgres ENUMs created in migration 117 (do not recreate at SA layer).
InteractionChannelEnum = ENUM(
    "call",
    "voicemail",
    "sms",
    "email",
    "chat",
    name="interaction_channel",
    create_type=False,
)

InteractionDirectionEnum = ENUM(
    "inbound",
    "outbound",
    name="interaction_direction",
    create_type=False,
)

InteractionProviderEnum = ENUM(
    "ringcentral",
    "twilio",
    "brevo",
    "microsoft365",
    "website_chat",
    name="interaction_provider",
    create_type=False,
)

ActionItemStatusEnum = ENUM(
    "open",
    "done",
    "dismissed",
    name="action_item_status",
    create_type=False,
)

AnalysisRunTierEnum = ENUM(
    "triage",
    "reply",
    "strategy",
    name="analysis_run_tier",
    create_type=False,
)

AnalysisRunStatusEnum = ENUM(
    "ok",
    "error",
    "timeout",
    name="analysis_run_status",
    create_type=False,
)


class CustomerInteraction(Base):
    """One row per inbound/outbound interaction across every channel."""

    __tablename__ = "customer_interactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_id = Column(Text, nullable=False, unique=True, index=True)
    channel = Column(InteractionChannelEnum, nullable=False)
    direction = Column(InteractionDirectionEnum, nullable=False)
    provider = Column(InteractionProviderEnum, nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    from_address = Column(Text, nullable=False)
    to_address = Column(Text, nullable=False)
    subject = Column(Text, nullable=True)
    content = Column(Text, nullable=False, default="")
    content_uri = Column(Text, nullable=True)
    raw_payload = Column(JSONB, nullable=False, default=dict)
    analysis = Column(JSONB, nullable=False, default=dict)
    suggested_reply = Column(Text, nullable=True)
    analysis_model = Column(Text, nullable=True)
    analysis_at = Column(DateTime(timezone=True), nullable=True)
    analysis_cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    hot_lead_score = Column(Integer, nullable=False, default=0)
    intent = Column(Text, nullable=True)
    sentiment = Column(Text, nullable=True)
    urgency = Column(Text, nullable=True)
    do_not_contact = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    # Relationships
    customer = relationship("Customer", foreign_keys=[customer_id], lazy="noload")
    action_items = relationship(
        "InteractionActionItem",
        back_populates="interaction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InteractionActionItem.created_at",
    )
    analysis_runs = relationship(
        "InteractionAnalysisRun",
        back_populates="interaction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InteractionAnalysisRun.created_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<CustomerInteraction {self.channel}/{self.direction} "
            f"score={self.hot_lead_score} id={self.id}>"
        )


class InteractionActionItem(Base):
    """Extracted action item attached to one interaction."""

    __tablename__ = "interaction_action_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customer_interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action = Column(Text, nullable=False)
    owner = Column(Text, nullable=False)  # 'dannia' | 'will' | 'dispatch' | 'none'
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(ActionItemStatusEnum, nullable=False, default="open")
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    interaction = relationship("CustomerInteraction", back_populates="action_items")

    def __repr__(self) -> str:
        return f"<InteractionActionItem {self.owner} {self.status}: {self.action[:40]}>"


class InteractionAnalysisRun(Base):
    """Audit log of every Claude/Deepgram model call against an interaction."""

    __tablename__ = "interaction_analysis_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("customer_interactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tier = Column(AnalysisRunTierEnum, nullable=False)
    model = Column(Text, nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    prompt_version = Column(Text, nullable=False)
    status = Column(AnalysisRunStatusEnum, nullable=False)
    error_detail = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    interaction = relationship("CustomerInteraction", back_populates="analysis_runs")

    def __repr__(self) -> str:
        return (
            f"<InteractionAnalysisRun tier={self.tier} status={self.status} "
            f"cost=${self.cost_usd}>"
        )
