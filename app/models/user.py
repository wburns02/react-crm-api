from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    """User model for authentication - separate from legacy users table."""

    __tablename__ = "api_users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    default_entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # MFA relationship
    mfa_settings = relationship("UserMFASettings", back_populates="user", uselist=False)

    def __repr__(self):
        return f"<User {self.email}>"

    @property
    def mfa_enabled(self) -> bool:
        """Check if MFA is enabled for this user."""
        return self.mfa_settings is not None and self.mfa_settings.mfa_enabled
