"""Clover OAuth token storage model."""

from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.database import Base
import uuid as uuid_module


class CloverOAuthToken(Base):
    """Stores Clover OAuth2 access tokens per merchant."""

    __tablename__ = "clover_oauth_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4)
    merchant_id = Column(String(50), nullable=False, unique=True, index=True)
    access_token = Column(Text, nullable=False)
    token_type = Column(String(20), default="Bearer")
    scope = Column(Text, nullable=True)
    merchant_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    connected_by = Column(String(255), nullable=True)  # email of user who connected
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<CloverOAuthToken merchant={self.merchant_id} active={self.is_active}>"
