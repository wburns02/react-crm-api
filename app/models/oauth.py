"""
OAuth2 Models

Models for public API authentication using OAuth2 client credentials flow.
Supports API client management, token storage, and rate limiting.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class APIClient(Base):
    """
    OAuth2 API Client for public API access.

    Represents a registered application that can access the public API.
    Uses client credentials flow for machine-to-machine authentication.
    """

    __tablename__ = "api_clients"

    id = Column(Integer, primary_key=True, index=True)

    # Client credentials
    client_id = Column(String(64), unique=True, nullable=False, index=True)
    client_secret_hash = Column(String(255), nullable=False)  # bcrypt hashed

    # Client metadata
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Permissions
    scopes = Column(String(500), default="read")  # Space-separated scopes

    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=100)
    rate_limit_per_hour = Column(Integer, default=1000)

    # Status
    is_active = Column(Boolean, default=True)

    # Owner tracking
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime)

    # Relationships
    tokens = relationship("APIToken", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<APIClient {self.name} ({self.client_id})>"

    @property
    def scope_list(self) -> list[str]:
        """Return scopes as a list."""
        return self.scopes.split() if self.scopes else []

    def has_scope(self, scope: str) -> bool:
        """Check if client has a specific scope."""
        return scope in self.scope_list or "admin" in self.scope_list


class APIToken(Base):
    """
    OAuth2 Access Token for public API.

    Stores issued access tokens and their metadata for validation.
    """

    __tablename__ = "api_tokens"

    id = Column(Integer, primary_key=True, index=True)

    # Token data
    token_hash = Column(String(255), unique=True, nullable=False, index=True)  # SHA256 hash
    token_type = Column(String(20), default="Bearer")

    # Client reference
    client_id = Column(Integer, ForeignKey("api_clients.id"), nullable=False)

    # Scope and permissions (may be subset of client scopes)
    scopes = Column(String(500))

    # Expiration
    expires_at = Column(DateTime, nullable=False)

    # Refresh token (optional)
    refresh_token_hash = Column(String(255), unique=True, index=True)
    refresh_expires_at = Column(DateTime)

    # Status
    is_revoked = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime)

    # Relationships
    client = relationship("APIClient", back_populates="tokens")

    def __repr__(self):
        return f"<APIToken client={self.client_id} expires={self.expires_at}>"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if token is valid (not expired and not revoked)."""
        return not self.is_expired and not self.is_revoked

    @property
    def scope_list(self) -> list[str]:
        """Return scopes as a list."""
        return self.scopes.split() if self.scopes else []
