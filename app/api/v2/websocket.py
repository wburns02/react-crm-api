"""
WebSocket Endpoint

Provides real-time communication for the CRM frontend.
Supports:
- Authentication via JWT token query parameter
- Ping/pong heartbeat
- Subscription to specific event types
- Real-time event streaming
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from datetime import datetime
from typing import Optional, Set
import logging
import json

from app.api.deps import get_current_user_ws
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT access token"),
):
    """
    WebSocket endpoint for real-time updates.

    Connection URL: ws://host/api/v2/ws?token=<jwt_token>

    Message Protocol:
    - Client -> Server:
        - {"type": "ping"} - Heartbeat ping
        - {"type": "subscribe", "events": ["work_order.*", "payment.*"]} - Subscribe to events
        - {"type": "unsubscribe", "events": ["work_order.*"]} - Unsubscribe from events

    - Server -> Client:
        - {"type": "pong", "timestamp": "..."} - Heartbeat response
        - {"type": "connected", "user_id": 123} - Connection confirmation
        - {"type": "work_order.updated", "data": {...}, "timestamp": "..."} - Event notification
        - {"type": "error", "message": "..."} - Error message

    Events:
        - work_order.created
        - work_order.updated
        - work_order.status_changed
        - work_order.assigned
        - notification.created
        - schedule.updated
        - payment.received
    """
    # Authenticate the connection
    user = await get_current_user_ws(token)

    if not user:
        logger.warning("WebSocket connection rejected: invalid token")
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Get user role for role-based messaging
    user_role = None
    if hasattr(user, "is_superuser") and user.is_superuser:
        user_role = "admin"
    # Add more role detection logic as needed

    # Register the connection
    await manager.connect(websocket, user.id, user_role)

    # Track subscribed event types (empty = all events)
    subscriptions: Set[str] = set()

    try:
        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user.id,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Message handling loop
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                    }
                )
                continue

            message_type = data.get("type")

            if message_type == "ping":
                # Heartbeat response
                manager.update_heartbeat(websocket)
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

            elif message_type == "subscribe":
                # Subscribe to event types
                events = data.get("events", [])
                if isinstance(events, list):
                    subscriptions.update(events)
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "events": list(subscriptions),
                        }
                    )

            elif message_type == "unsubscribe":
                # Unsubscribe from event types
                events = data.get("events", [])
                if isinstance(events, list):
                    subscriptions -= set(events)
                    await websocket.send_json(
                        {
                            "type": "unsubscribed",
                            "events": events,
                        }
                    )

            elif message_type == "get_stats":
                # Admin only: get connection stats
                if user_role == "admin":
                    stats = manager.get_connection_stats()
                    await websocket.send_json(
                        {
                            "type": "stats",
                            "data": stats,
                        }
                    )
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Permission denied",
                        }
                    )

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user_id={user.id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}")
    finally:
        manager.disconnect(websocket, user.id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics.

    Returns connection counts and user information.
    Useful for monitoring and debugging.
    """
    return manager.get_connection_stats()
