"""
A/B Test Models for Campaign Optimization

Enables A/B testing of campaign elements:
- Subject line testing
- Content testing
- Send time testing
- Channel testing
- Statistical significance calculation
"""

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ABTest(Base):
    """
    A/B test definition for campaign optimization.

    Supports testing different variants of campaign elements
    with statistical significance tracking.
    """

    __tablename__ = "cs_ab_tests"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("cs_campaigns.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Test type: what element is being tested
    test_type = Column(String(50), default="subject")  # subject, content, send_time, channel

    # Status
    status = Column(String(20), default="draft")  # draft, running, paused, completed

    # Variant A (Control)
    variant_a_name = Column(String(200), default="Control")
    variant_a_config = Column(JSON)  # {subject: "...", content: "...", send_time: "...", etc}

    # Variant B (Treatment)
    variant_b_name = Column(String(200), default="Variant B")
    variant_b_config = Column(JSON)

    # Traffic split (percentage to variant B, rest goes to A)
    traffic_split = Column(Float, default=50.0)

    # Variant A Metrics
    variant_a_sent = Column(Integer, default=0)
    variant_a_opened = Column(Integer, default=0)
    variant_a_clicked = Column(Integer, default=0)
    variant_a_converted = Column(Integer, default=0)

    # Variant B Metrics
    variant_b_sent = Column(Integer, default=0)
    variant_b_opened = Column(Integer, default=0)
    variant_b_clicked = Column(Integer, default=0)
    variant_b_converted = Column(Integer, default=0)

    # Statistical results
    winning_variant = Column(String(1))  # 'a' or 'b' or null if not determined
    confidence_level = Column(Float)  # 0-100%
    is_significant = Column(Boolean, default=False)

    # Test settings
    min_sample_size = Column(Integer, default=100)  # Min samples before declaring winner
    significance_threshold = Column(Float, default=95.0)  # Required confidence %
    auto_winner = Column(Boolean, default=True)  # Auto-select winner when significant
    primary_metric = Column(String(50), default="conversion")  # conversion, open, click

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    campaign = relationship("Campaign", backref="ab_tests")

    def __repr__(self):
        return f"<ABTest id={self.id} name='{self.name}' type={self.test_type} status={self.status}>"

    @property
    def variant_a_conversion_rate(self) -> float:
        """Calculate variant A conversion rate."""
        if self.variant_a_sent and self.variant_a_sent > 0:
            return (self.variant_a_converted / self.variant_a_sent) * 100
        return 0.0

    @property
    def variant_b_conversion_rate(self) -> float:
        """Calculate variant B conversion rate."""
        if self.variant_b_sent and self.variant_b_sent > 0:
            return (self.variant_b_converted / self.variant_b_sent) * 100
        return 0.0

    @property
    def variant_a_open_rate(self) -> float:
        """Calculate variant A open rate."""
        if self.variant_a_sent and self.variant_a_sent > 0:
            return (self.variant_a_opened / self.variant_a_sent) * 100
        return 0.0

    @property
    def variant_b_open_rate(self) -> float:
        """Calculate variant B open rate."""
        if self.variant_b_sent and self.variant_b_sent > 0:
            return (self.variant_b_opened / self.variant_b_sent) * 100
        return 0.0

    @property
    def variant_a_click_rate(self) -> float:
        """Calculate variant A click rate."""
        if self.variant_a_sent and self.variant_a_sent > 0:
            return (self.variant_a_clicked / self.variant_a_sent) * 100
        return 0.0

    @property
    def variant_b_click_rate(self) -> float:
        """Calculate variant B click rate."""
        if self.variant_b_sent and self.variant_b_sent > 0:
            return (self.variant_b_clicked / self.variant_b_sent) * 100
        return 0.0

    @property
    def total_sample_size(self) -> int:
        """Total samples across both variants."""
        return (self.variant_a_sent or 0) + (self.variant_b_sent or 0)

    @property
    def has_min_sample(self) -> bool:
        """Check if minimum sample size has been reached."""
        return self.total_sample_size >= (self.min_sample_size or 100)
