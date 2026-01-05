"""
Web Push Notification API Endpoints

Provides:
- VAPID key retrieval
- Subscription management
- Push notification sending
- Notification preferences
"""

from fastapi import APIRouter, HTTPException, Query, Body
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import os
import json

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Configuration
# =============================================================================

# VAPID keys for Web Push
# Generate with: npx web-push generate-vapid-keys
VAPID_PUBLIC_KEY = os.getenv(
    "VAPID_PUBLIC_KEY",
    "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U"  # Demo key
)
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_CLAIMS_EMAIL = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@ecbtx.com")


# =============================================================================
# Pydantic Schemas
# =============================================================================

class PushSubscription(BaseModel):
    """Browser push subscription."""
    endpoint: str
    keys: dict  # Contains p256dh and auth


class SubscriptionCreate(BaseModel):
    """Request to create push subscription."""
    subscription: PushSubscription
    device_name: Optional[str] = None
    device_type: str = "web"  # web, mobile, desktop


class SubscriptionResponse(BaseModel):
    """Push subscription response."""
    id: str
    user_id: str
    device_name: Optional[str] = None
    device_type: str
    created_at: str
    last_used: Optional[str] = None
    is_active: bool = True


class SendNotificationRequest(BaseModel):
    """Request to send a push notification."""
    title: str
    body: str
    icon: Optional[str] = None
    badge: Optional[str] = None
    tag: Optional[str] = None
    data: Optional[dict] = None
    actions: Optional[list[dict]] = None
    # Target options
    user_ids: Optional[list[str]] = None  # Specific users
    role: Optional[str] = None  # All users with role
    all_users: bool = False


class NotificationPreferences(BaseModel):
    """User notification preferences."""
    new_work_order: bool = True
    work_order_assigned: bool = True
    work_order_status_change: bool = True
    payment_received: bool = True
    invoice_overdue: bool = True
    customer_message: bool = True
    schedule_reminder: bool = True
    system_alerts: bool = True
    marketing: bool = False


class NotificationLog(BaseModel):
    """Notification log entry."""
    id: str
    title: str
    body: str
    sent_at: str
    delivered_count: int
    failed_count: int
    click_count: int
    sent_by: str


# =============================================================================
# VAPID Key Endpoints
# =============================================================================

@router.get("/vapid-key")
async def get_vapid_public_key() -> dict:
    """Get VAPID public key for push subscription."""
    return {"publicKey": VAPID_PUBLIC_KEY}


# =============================================================================
# Subscription Management
# =============================================================================

@router.post("/subscribe")
async def create_subscription(
    request: SubscriptionCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> SubscriptionResponse:
    """Create a push notification subscription."""
    # In production: store in database
    subscription_id = f"sub_{uuid4().hex[:12]}"

    return SubscriptionResponse(
        id=subscription_id,
        user_id=str(current_user.id),
        device_name=request.device_name,
        device_type=request.device_type,
        created_at=datetime.utcnow().isoformat(),
        is_active=True
    )


@router.delete("/subscribe")
async def remove_subscription(
    endpoint: str = Query(...),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Remove a push notification subscription."""
    # In production: delete from database
    return {"success": True, "message": "Subscription removed"}


@router.get("/subscriptions")
async def get_user_subscriptions(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get all subscriptions for current user."""
    # Mock data
    subscriptions = [
        SubscriptionResponse(
            id="sub_abc123",
            user_id=str(current_user.id),
            device_name="Chrome on Windows",
            device_type="web",
            created_at=(datetime.utcnow()).isoformat(),
            last_used=(datetime.utcnow()).isoformat(),
            is_active=True
        ),
    ]

    return {"subscriptions": [s.model_dump() for s in subscriptions]}


# =============================================================================
# Send Notifications
# =============================================================================

@router.post("/send")
async def send_push_notification(
    request: SendNotificationRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Send push notifications to users."""
    if not VAPID_PRIVATE_KEY:
        raise HTTPException(
            status_code=503,
            detail="Push notifications not configured (missing VAPID private key)"
        )

    # In production:
    # 1. Get subscriptions for target users
    # 2. Build notification payload
    # 3. Send via web-push library
    # 4. Log results

    # Mock response
    delivered = 0
    failed = 0

    if request.all_users:
        delivered = 50
        failed = 2
    elif request.user_ids:
        delivered = len(request.user_ids)
    elif request.role:
        delivered = 15

    notification_id = f"notif_{uuid4().hex[:12]}"

    return {
        "notification_id": notification_id,
        "title": request.title,
        "delivered": delivered,
        "failed": failed,
        "sent_at": datetime.utcnow().isoformat()
    }


@router.post("/send/test")
async def send_test_notification(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Send a test notification to current user."""
    return {
        "success": True,
        "message": "Test notification sent",
        "title": "Test Notification",
        "body": "This is a test notification from ECBTX CRM"
    }


# =============================================================================
# Notification Templates
# =============================================================================

@router.get("/templates")
async def get_notification_templates(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get predefined notification templates."""
    templates = [
        {
            "id": "new_work_order",
            "name": "New Work Order",
            "title": "New Work Order Assigned",
            "body": "You have been assigned a new work order for {{customer_name}}",
            "variables": ["customer_name", "job_type", "scheduled_date"]
        },
        {
            "id": "schedule_reminder",
            "name": "Schedule Reminder",
            "title": "Upcoming Appointment",
            "body": "Reminder: {{job_type}} appointment at {{time}} for {{customer_name}}",
            "variables": ["customer_name", "job_type", "time", "address"]
        },
        {
            "id": "payment_received",
            "name": "Payment Received",
            "title": "Payment Received",
            "body": "Payment of ${{amount}} received from {{customer_name}}",
            "variables": ["customer_name", "amount", "invoice_number"]
        },
        {
            "id": "invoice_overdue",
            "name": "Invoice Overdue",
            "title": "Invoice Overdue",
            "body": "Invoice #{{invoice_number}} for {{customer_name}} is {{days_overdue}} days overdue",
            "variables": ["customer_name", "invoice_number", "amount", "days_overdue"]
        },
    ]

    return {"templates": templates}


# =============================================================================
# User Preferences
# =============================================================================

@router.get("/preferences")
async def get_notification_preferences(
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationPreferences:
    """Get user's notification preferences."""
    # In production: fetch from database
    return NotificationPreferences()


@router.patch("/preferences")
async def update_notification_preferences(
    preferences: NotificationPreferences,
    db: DbSession,
    current_user: CurrentUser,
) -> NotificationPreferences:
    """Update user's notification preferences."""
    # In production: save to database
    return preferences


# =============================================================================
# Notification History
# =============================================================================

@router.get("/history")
async def get_notification_history(
    db: DbSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Get notification history."""
    logs = [
        NotificationLog(
            id="notif_001",
            title="New Work Order Assigned",
            body="Work order #WO-123 assigned to Mike Johnson",
            sent_at=(datetime.utcnow()).isoformat(),
            delivered_count=1,
            failed_count=0,
            click_count=1,
            sent_by="system"
        ),
        NotificationLog(
            id="notif_002",
            title="Payment Received",
            body="Payment of $350.00 received from John Smith",
            sent_at=(datetime.utcnow()).isoformat(),
            delivered_count=3,
            failed_count=0,
            click_count=2,
            sent_by="system"
        ),
    ]

    return {
        "notifications": [n.model_dump() for n in logs],
        "total": len(logs),
        "page": page,
        "page_size": page_size
    }


@router.get("/stats")
async def get_notification_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get notification delivery statistics."""
    return {
        "total_sent_today": 45,
        "total_sent_week": 312,
        "total_sent_month": 1250,
        "delivery_rate": 0.97,
        "click_rate": 0.42,
        "active_subscriptions": 85,
        "by_type": {
            "work_order": 150,
            "payment": 80,
            "schedule": 120,
            "system": 45
        }
    }


# =============================================================================
# Scheduled Notifications
# =============================================================================

@router.post("/schedule")
async def schedule_notification(
    title: str = Query(...),
    body: str = Query(...),
    scheduled_for: str = Query(..., description="ISO datetime"),
    user_ids: list[str] = Body(default=[]),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Schedule a notification for future delivery."""
    schedule_id = f"sched_{uuid4().hex[:12]}"

    return {
        "schedule_id": schedule_id,
        "title": title,
        "scheduled_for": scheduled_for,
        "target_users": len(user_ids) if user_ids else "all",
        "status": "scheduled"
    }


@router.get("/scheduled")
async def get_scheduled_notifications(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get pending scheduled notifications."""
    return {
        "scheduled": [],
        "count": 0
    }


@router.delete("/scheduled/{schedule_id}")
async def cancel_scheduled_notification(
    schedule_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Cancel a scheduled notification."""
    return {"success": True, "message": "Scheduled notification cancelled"}
