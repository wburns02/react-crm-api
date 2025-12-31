"""
Admin Settings API - System configuration endpoints.

Provides settings management for system, notifications, integrations, and security.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.api.deps import CurrentUser

router = APIRouter()


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
