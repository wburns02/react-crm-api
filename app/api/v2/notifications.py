"""Notifications API - User notification management.

Provides endpoints for fetching and managing user notifications.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
import uuid

from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.models.notification import Notification
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
    query = select(Notification).where(Notification.user_id == current_user.id)

    if unread_only:
        query = query.where(Notification.read == False)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    notifications = result.scalars().all()

    items = [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "message": n.message,
            "read": n.read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "link": n.link,
            "metadata": n.extra_data,
        }
        for n in notifications
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_notification_stats(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get notification statistics for the current user."""
    # Total count
    total_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == current_user.id)
    )
    total = total_result.scalar() or 0

    # Unread count
    unread_result = await db.execute(
        select(func.count(Notification.id)).where(
            and_(Notification.user_id == current_user.id, Notification.read == False)
        )
    )
    unread = unread_result.scalar() or 0

    return NotificationStats(total=total, unread=unread)


@router.post("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Mark a notification as read."""
    try:
        notif_uuid = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")

    result = await db.execute(
        select(Notification).where(and_(Notification.id == notif_uuid, Notification.user_id == current_user.id))
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read = True
    notification.read_at = datetime.utcnow()

    await db.commit()

    return {"success": True, "notification_id": notification_id}


@router.post("/read-all")
async def mark_all_notifications_read(
    current_user: CurrentUser,
    db: DbSession,
):
    """Mark all notifications as read."""
    now = datetime.utcnow()

    result = await db.execute(
        update(Notification)
        .where(and_(Notification.user_id == current_user.id, Notification.read == False))
        .values(read=True, read_at=now)
        .returning(Notification.id)
    )

    # Count how many were updated
    updated_ids = result.fetchall()
    count = len(updated_ids)

    await db.commit()

    return {"success": True, "count": count}


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
    now = datetime.utcnow()

    # Determine target user(s)
    target_user_id = notification_data.target_user_id

    # Create notification in database
    notification = Notification(
        user_id=target_user_id or current_user.id,  # Default to sender if no target
        type=notification_data.type,
        title=notification_data.title,
        message=notification_data.message,
        link=notification_data.link,
        extra_data=notification_data.metadata,
        source="user",
    )

    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    notification_dict = {
        "id": str(notification.id),
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "read": notification.read,
        "created_at": notification.created_at.isoformat() if notification.created_at else now.isoformat(),
        "link": notification.link,
        "metadata": notification.extra_data,
    }

    # Broadcast via WebSocket based on targeting
    if notification_data.target_user_id:
        # Send to specific user
        await manager.send_to_user(
            notification_data.target_user_id,
            {
                "type": "notification.created",
                "data": notification_dict,
                "timestamp": now.isoformat(),
            },
        )
    elif notification_data.target_role:
        # Send to all users with specific role
        await manager.send_to_role(
            notification_data.target_role,
            {
                "type": "notification.created",
                "data": notification_dict,
                "timestamp": now.isoformat(),
            },
        )
    else:
        # Broadcast to all connected users
        await manager.broadcast_event(
            event_type="notification.created",
            data=notification_dict,
        )

    return {
        "success": True,
        "notification": notification_dict,
    }


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete a notification."""
    try:
        notif_uuid = UUID(notification_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid notification ID format")

    result = await db.execute(
        select(Notification).where(and_(Notification.id == notif_uuid, Notification.user_id == current_user.id))
    )
    notification = result.scalar_one_or_none()

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.delete(notification)
    await db.commit()

    return {"success": True, "notification_id": notification_id}
