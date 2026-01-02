"""Notifications API - User notification management.

Provides endpoints for fetching and managing user notifications.
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

from app.api.deps import CurrentUser, DbSession

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
