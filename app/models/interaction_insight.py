"""InteractionInsight — weekly Opus 4.7 strategist report.

One row per ISO week (e.g., "2026-W17") storing the cached Opus output so
the Weekly Insights page doesn't re-run a $X+ model call on every view.

See alembic/versions/118_add_interaction_insights.py for the schema.
"""
import uuid

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Integer,
    Numeric,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


class InteractionInsight(Base):
    """One row per ISO week of customer interactions; Tier 3 Opus output."""

    __tablename__ = "interaction_insights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    iso_week = Column(Text, nullable=False, unique=True, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_interactions = Column(Integer, nullable=False, default=0)
    by_channel = Column(JSONB, nullable=False, default=dict)
    report_markdown = Column(Text, nullable=False, default="")
    report_json = Column(JSONB, nullable=True)
    model = Column(Text, nullable=False)
    prompt_version = Column(Text, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_read_tokens = Column(Integer, nullable=False, default=0)
    cache_write_tokens = Column(Integer, nullable=False, default=0)
    thinking_tokens = Column(Integer, nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<InteractionInsight {self.iso_week} total={self.total_interactions}>"
