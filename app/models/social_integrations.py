"""
Social Platform Integration Models

Models for storing OAuth tokens, reviews, and sync state for
Yelp and Facebook integrations.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class SocialIntegration(Base):
    """
    OAuth/API credentials for social platform integrations.
    Stores credentials for Yelp and Facebook.
    """
    __tablename__ = "social_integrations"

    id = Column(Integer, primary_key=True, index=True)

    # Platform identifier
    platform = Column(String(50), nullable=False, index=True)  # 'yelp', 'facebook'

    # Business identification
    business_id = Column(String(255), nullable=True)  # Yelp business ID or FB page ID
    business_name = Column(String(255), nullable=True)

    # OAuth tokens (for Facebook)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # Scopes granted (for Facebook)
    scopes = Column(String(500), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime, nullable=True)
    sync_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    reviews = relationship("SocialReview", back_populates="integration", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SocialIntegration {self.platform}: {self.business_name}>"

    @property
    def is_token_expired(self) -> bool:
        """Check if OAuth token is expired."""
        if not self.token_expires_at:
            return False
        return datetime.utcnow() > self.token_expires_at


class SocialReview(Base):
    """
    Reviews fetched from Yelp and Facebook.
    Cached locally for display and response tracking.
    """
    __tablename__ = "social_reviews"

    id = Column(Integer, primary_key=True, index=True)

    integration_id = Column(Integer, ForeignKey("social_integrations.id"), nullable=False, index=True)

    # Review identifiers
    platform = Column(String(50), nullable=False, index=True)  # 'yelp', 'facebook'
    external_id = Column(String(255), nullable=False)  # Platform's review ID

    # Review content
    author_name = Column(String(255), nullable=True)
    author_profile_url = Column(Text, nullable=True)
    author_image_url = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)  # 1-5 scale
    text = Column(Text, nullable=True)
    review_url = Column(Text, nullable=True)

    # Timestamps from platform
    review_created_at = Column(DateTime, nullable=True)

    # Response tracking
    has_response = Column(Boolean, default=False)
    response_text = Column(Text, nullable=True)
    response_sent_at = Column(DateTime, nullable=True)
    response_status = Column(String(50), nullable=True)  # 'pending', 'sent', 'failed'

    # AI-generated response suggestion
    ai_suggested_response = Column(Text, nullable=True)

    # Sentiment analysis
    sentiment_score = Column(Float, nullable=True)  # -1.0 to 1.0
    sentiment_label = Column(String(50), nullable=True)  # 'positive', 'neutral', 'negative'

    # Local timestamps
    fetched_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    integration = relationship("SocialIntegration", back_populates="reviews")

    # Unique constraint to prevent duplicate reviews
    __table_args__ = (
        UniqueConstraint('platform', 'external_id', name='uq_platform_external_id'),
    )

    def __repr__(self):
        return f"<SocialReview {self.platform}: {self.author_name} ({self.rating})>"
