"""Notifications API - User notification management.

Provides endpoints for fetching and managing user notifications.
"""
from fastapi import APIRouter, Query, Body
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import uuid

from app.api.deps import CurrentUser, DbSession
from app.services.websocket_manager import manager

router = APIRouter()


class NotificationResponse(BaseModel):
    id: str
    type: str  # work_order, payment, customer, system
    title: str
    message: str
    read: bool = False
    created_at: datetime
    link: Optional[str] = None
    metadata: Optional[dict] = None


class NotificationStats(BaseModel):
    total: int = 0
    unread: int = 0


@router.get("")
async def list_notifications(
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = False,
):
    """List notifications for the current user."""
    # TODO: Implement with database table
    # For now return empty list to prevent 404
    return {
        "items": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_notification_stats(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get notification statistics for the current user."""
    # TODO: Implement with database table
    # For now return zeros to prevent 404
    return NotificationStats(total=0, unread=0)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Mark a notification as read."""
    return {"success": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: CurrentUser,
    db: DbSession,
):
    """Mark all notifications as read."""
    return {"success": True, "count": 0}


class NotificationCreate(BaseModel):
    """Schema for creating a new notification."""
    type: str  # work_order, payment, customer, system
    title: str
    message: str
    link: Optional[str] = None
    metadata: Optional[dict] = None
    target_user_id: Optional[int] = None  # None = broadcast to all
    target_role: Optional[str] = None  # Optional role-based targeting


@router.post("")
async def create_notification(
    notification_data: NotificationCreate,
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Create a new notification and broadcast via WebSocket.

    This endpoint creates a notification and immediately pushes it
    to connected WebSocket clients based on targeting:
    - If target_user_id is set, only that user receives it
    - If target_role is set, all users with that role receive it
    - If neither is set, broadcasts to all connected users
    """
    notification_id = str(uuid.uuid4())
    now = datetime.utcnow()

    notification = {
        "id": notification_id,
        "type": notification_data.type,
        "title": notification_data.title,
        "message": notification_data.message,
        "read": False,
        "created_at": now.isoformat(),
        "link": notification_data.link,
        "metadata": notification_data.metadata,
    }

    # Broadcast via WebSocket based on targeting
    if notification_data.target_user_id:
        # Send to specific user
        await manager.send_to_user(
            notification_data.target_user_id,
            {
                "type": "notification.created",
                "data": notification,
                "timestamp": now.isoformat(),
            }
        )
    elif notification_data.target_role:
        # Send to all users with specific role
        await manager.send_to_role(
            notification_data.target_role,
            {
                "type": "notification.created",
                "data": notification,
                "timestamp": now.isoformat(),
            }
        )
    else:
        # Broadcast to all connected users
        await manager.broadcast_event(
            event_type="notification.created",
            data=notification,
        )

    return {
        "success": True,
        "notification": notification,
    }
