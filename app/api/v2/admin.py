"""
Admin Settings API - System configuration endpoints.

Provides settings management for system, notifications, integrations, and security.
Also provides user management endpoints.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from sqlalchemy import select
from datetime import datetime

from app.api.deps import CurrentUser, DbSession, get_password_hash
from app.models.user import User

router = APIRouter()


# ============ User Management ============

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True
    last_login: Optional[str] = None
    created_at: str


class CreateUserRequest(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "user"
    password: str


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


def user_to_response(user: User) -> dict:
    """Convert User model to response dict."""
    role = "admin" if user.is_superuser else "user"
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": role,
        "is_active": user.is_active,
        "last_login": None,  # Not tracked yet
        "created_at": user.created_at.isoformat() if user.created_at else datetime.utcnow().isoformat(),
    }


@router.get("/users")
async def list_users(
    db: DbSession,
    current_user: CurrentUser,
):
    """List all users."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return {"users": [user_to_response(u) for u in users]}


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new user."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=request.email,
        hashed_password=get_password_hash(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        is_active=True,
        is_superuser=(request.role == "admin"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user": user_to_response(user)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a user."""
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields
    if request.email is not None:
        user.email = request.email
    if request.first_name is not None:
        user.first_name = request.first_name
    if request.last_name is not None:
        user.last_name = request.last_name
    if request.role is not None:
        user.is_superuser = (request.role == "admin")
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password is not None:
        user.hashed_password = get_password_hash(request.password)

    await db.commit()
    await db.refresh(user)

    return {"user": user_to_response(user)}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Deactivate a user (soft delete)."""
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = False
    await db.commit()

    return {"message": "User deactivated"}


class SystemSettings(BaseModel):
    company_name: str = "MAC Septic CRM"
    timezone: str = "America/Chicago"
    date_format: str = "MM/DD/YYYY"
    currency: str = "USD"
    language: str = "en"


class NotificationSettings(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = False
    daily_digest: bool = True
    work_order_alerts: bool = True
    payment_alerts: bool = True


class IntegrationSettings(BaseModel):
    samsara_enabled: bool = False
    ringcentral_enabled: bool = False
    quickbooks_enabled: bool = False
    stripe_enabled: bool = False


class SecuritySettings(BaseModel):
    two_factor_required: bool = False
    session_timeout_minutes: int = 30
    password_expiry_days: int = 90
    ip_whitelist_enabled: bool = False
    ip_whitelist: list[str] = []


@router.get("/settings/system")
async def get_system_settings(current_user: CurrentUser) -> SystemSettings:
    """Get system settings."""
    return SystemSettings()


@router.patch("/settings/system")
async def update_system_settings(
    settings: SystemSettings,
    current_user: CurrentUser,
) -> SystemSettings:
    """Update system settings."""
    # TODO: Persist settings to database
    return settings


@router.get("/settings/notifications")
async def get_notification_settings(current_user: CurrentUser) -> NotificationSettings:
    """Get notification settings."""
    return NotificationSettings()


@router.patch("/settings/notifications")
async def update_notification_settings(
    settings: NotificationSettings,
    current_user: CurrentUser,
) -> NotificationSettings:
    """Update notification settings."""
    return settings


@router.get("/settings/integrations")
async def get_integration_settings(current_user: CurrentUser) -> IntegrationSettings:
    """Get integration settings."""
    return IntegrationSettings()


@router.patch("/settings/integrations")
async def update_integration_settings(
    settings: IntegrationSettings,
    current_user: CurrentUser,
) -> IntegrationSettings:
    """Update integration settings."""
    return settings


@router.get("/settings/security")
async def get_security_settings(current_user: CurrentUser) -> SecuritySettings:
    """Get security settings."""
    return SecuritySettings()


@router.patch("/settings/security")
async def update_security_settings(
    settings: SecuritySettings,
    current_user: CurrentUser,
) -> SecuritySettings:
    """Update security settings."""
    return settings
