from pydantic import BaseModel, EmailStr, Field, computed_field
from datetime import datetime
from typing import Optional, Literal


RoleType = Literal["admin", "manager", "technician", "sales", "user"]


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user."""

    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """Schema for user response - matches React frontend User type."""

    id: str  # React expects string ID
    is_active: bool
    is_superuser: bool
    created_at: datetime
    role: RoleType = "user"
    permissions: Optional[dict] = None
    technician_id: Optional[str] = None

    class Config:
        from_attributes = True

    @classmethod
    def from_db_user(cls, user) -> "UserResponse":
        """Create UserResponse from database User model."""
        role: RoleType = "admin" if user.is_superuser else "user"
        return cls(
            id=str(user.id),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            role=role,
            permissions=None,
            technician_id=None,
        )


class AuthMeResponse(BaseModel):
    """Response wrapper for /auth/me to match React frontend expectations."""

    user: UserResponse


class Token(BaseModel):
    """JWT token response - includes 'token' for React frontend compatibility."""

    access_token: str
    token: str  # Alias for access_token (React checks for this)
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data encoded in JWT token."""

    user_id: Optional[int] = None
    email: Optional[str] = None


class LoginRequest(BaseModel):
    """Login request schema."""

    email: EmailStr
    password: str
