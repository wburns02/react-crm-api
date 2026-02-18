"""AI Provider configuration and usage tracking models."""

from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, Float, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AIProviderConfig(Base):
    """Stores AI provider configuration (API keys, model selection, feature routing)."""

    __tablename__ = "ai_provider_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, unique=True, index=True)  # "anthropic", "openai"
    api_key_encrypted = Column(Text, nullable=True)  # Fernet-encrypted API key
    is_active = Column(Boolean, default=True, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)

    # Model config (JSON): {"default_model": "claude-sonnet-4-6", "available_models": [...]}
    model_config_data = Column(JSON, nullable=False, default=dict)

    # Feature routing (JSON): {"chat": true, "summarization": true, "dispatch": false, ...}
    feature_config = Column(JSON, nullable=False, default=dict)

    # Connection metadata
    connected_by = Column(String(255), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<AIProviderConfig {self.provider} active={self.is_active} primary={self.is_primary}>"


class AIUsageLog(Base):
    """Tracks per-request AI usage for cost monitoring."""

    __tablename__ = "ai_usage_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    feature = Column(String(50), nullable=False, index=True)

    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_cents = Column(Integer, default=0)  # USD cents to avoid float precision

    user_id = Column(String(100), nullable=True)
    request_duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AIUsageLog {self.provider}/{self.model} {self.feature} tokens={self.total_tokens}>"
