"""MFA (Multi-Factor Authentication) models for TOTP-based 2FA."""

from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class UserMFASettings(Base):
    """Per-user MFA configuration and settings."""

    __tablename__ = "user_mfa_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False, unique=True, index=True)

    # TOTP Configuration
    totp_secret = Column(String(32), nullable=True)  # Base32 encoded secret
    totp_enabled = Column(Boolean, default=False)
    totp_verified = Column(Boolean, default=False)  # True after user confirms setup

    # MFA Status
    mfa_enabled = Column(Boolean, default=False)
    mfa_enforced = Column(Boolean, default=False)  # Admin can require MFA

    # Backup codes tracking
    backup_codes_count = Column(Integer, default=0)
    backup_codes_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="mfa_settings")
    backup_codes = relationship("UserBackupCode", back_populates="mfa_settings", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<UserMFASettings user_id={self.user_id} mfa_enabled={self.mfa_enabled}>"


class UserBackupCode(Base):
    """Single-use backup codes for MFA recovery."""

    __tablename__ = "user_backup_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)
    mfa_settings_id = Column(Integer, ForeignKey("user_mfa_settings.id"), nullable=False)

    # Hashed backup code (bcrypt)
    code_hash = Column(String(255), nullable=False)

    # Usage tracking
    used = Column(Boolean, default=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    mfa_settings = relationship("UserMFASettings", back_populates="backup_codes")

    # Index for fast lookups
    __table_args__ = (Index("ix_backup_codes_user", "user_id"),)

    def __repr__(self):
        return f"<UserBackupCode user_id={self.user_id} used={self.used}>"


class MFASession(Base):
    """Temporary session for MFA verification during login."""

    __tablename__ = "mfa_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False, index=True)

    # Session token (hashed)
    session_token_hash = Column(String(255), nullable=False, unique=True, index=True)

    # Challenge tracking
    challenge_type = Column(String(20), default="totp")  # 'totp', 'backup_code'
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    # Validity
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MFASession user_id={self.user_id} challenge_type={self.challenge_type}>"

    @property
    def is_expired(self):
        """Check if the session has expired."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def attempts_remaining(self):
        """Get remaining verification attempts."""
        return max(0, self.max_attempts - self.attempts)
