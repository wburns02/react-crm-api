"""
WebSocket Connection Manager

Manages WebSocket connections for real-time updates.
Supports:
- Broadcasting to all connected clients
- Sending to specific users
- Sending to users by role
- Connection heartbeat tracking
"""

from fastapi import WebSocket
from typing import Dict, Set, Optional, Any
from datetime import datetime
import logging
import asyncio
import json

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and message broadcasting.

    Tracks connections by user_id for targeted messaging
    and maintains heartbeat timestamps for connection health monitoring.
    """

    def __init__(self):
        # Maps user_id to set of WebSocket connections (supports multiple tabs/devices)
        self._connections: Dict[int, Set[WebSocket]] = {}
        # Maps WebSocket to user_id for reverse lookup
        self._websocket_to_user: Dict[WebSocket, int] = {}
        # Maps user_id to their role for role-based broadcasting
        self._user_roles: Dict[int, str] = {}
        # Heartbeat tracking: WebSocket -> last ping timestamp
        self._heartbeats: Dict[WebSocket, datetime] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        user_role: Optional[str] = None
    ) -> None:
        """
        Accept a WebSocket connection and register it.

        Args:
            websocket: The WebSocket connection to register
            user_id: The authenticated user's ID
            user_role: Optional role for role-based messaging
        """
        await websocket.accept()

        async with self._lock:
            # Initialize set for this user if first connection
            if user_id not in self._connections:
                self._connections[user_id] = set()

            self._connections[user_id].add(websocket)
            self._websocket_to_user[websocket] = user_id
            self._heartbeats[websocket] = datetime.utcnow()

            if user_role:
                self._user_roles[user_id] = user_role

        logger.info(
            f"WebSocket connected: user_id={user_id}, "
            f"total_connections={self.total_connections}"
        )

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: The WebSocket connection to remove
            user_id: The user's ID
        """
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)

            # Clean up empty user sets
            if not self._connections[user_id]:
                del self._connections[user_id]
                if user_id in self._user_roles:
                    del self._user_roles[user_id]

        self._websocket_to_user.pop(websocket, None)
        self._heartbeats.pop(websocket, None)

        logger.info(
            f"WebSocket disconnected: user_id={user_id}, "
            f"total_connections={self.total_connections}"
        )

    def update_heartbeat(self, websocket: WebSocket) -> None:
        """Update the heartbeat timestamp for a connection."""
        self._heartbeats[websocket] = datetime.utcnow()

    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return len(self._websocket_to_user)

    @property
    def connected_users(self) -> Set[int]:
        """Get set of connected user IDs."""
        return set(self._connections.keys())

    async def send_to_user(self, user_id: int, message: dict) -> int:
        """
        Send a message to all connections for a specific user.

        Args:
            user_id: The target user's ID
            message: The message dict to send

        Returns:
            Number of connections the message was sent to
        """
        if user_id not in self._connections:
            return 0

        sent_count = 0
        dead_connections = []

        for websocket in self._connections[user_id]:
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to user {user_id}: {e}")
                dead_connections.append(websocket)

        # Clean up dead connections
        for ws in dead_connections:
            self.disconnect(ws, user_id)

        return sent_count

    async def send_to_role(self, role: str, message: dict) -> int:
        """
        Send a message to all users with a specific role.

        Args:
            role: The target role (e.g., 'admin', 'technician', 'manager')
            message: The message dict to send

        Returns:
            Number of users the message was sent to
        """
        target_users = [
            user_id for user_id, user_role in self._user_roles.items()
            if user_role == role
        ]

        sent_count = 0
        for user_id in target_users:
            count = await self.send_to_user(user_id, message)
            if count > 0:
                sent_count += 1

        return sent_count

    async def broadcast(self, message: dict, exclude_user: Optional[int] = None) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: The message dict to send
            exclude_user: Optional user_id to exclude from broadcast

        Returns:
            Number of connections the message was sent to
        """
        sent_count = 0

        for user_id in list(self._connections.keys()):
            if exclude_user and user_id == exclude_user:
                continue

            count = await self.send_to_user(user_id, message)
            sent_count += count

        logger.debug(f"Broadcast sent to {sent_count} connections")
        return sent_count

    async def broadcast_event(
        self,
        event_type: str,
        data: dict,
        target_users: Optional[Set[int]] = None,
        target_role: Optional[str] = None,
        exclude_user: Optional[int] = None
    ) -> int:
        """
        Broadcast a typed event with data payload.

        Args:
            event_type: Type of event (e.g., 'work_order.updated', 'payment.received')
            data: Event data payload
            target_users: Optional set of specific user IDs to target
            target_role: Optional role to target
            exclude_user: Optional user to exclude

        Returns:
            Number of connections the message was sent to
        """
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if target_users:
            sent_count = 0
            for user_id in target_users:
                if exclude_user and user_id == exclude_user:
                    continue
                count = await self.send_to_user(user_id, message)
                sent_count += count
            return sent_count

        if target_role:
            return await self.send_to_role(target_role, message)

        return await self.broadcast(message, exclude_user=exclude_user)

    async def check_stale_connections(self, timeout_seconds: int = 120) -> int:
        """
        Check for and clean up stale connections.

        Args:
            timeout_seconds: Seconds since last heartbeat to consider stale

        Returns:
            Number of stale connections cleaned up
        """
        now = datetime.utcnow()
        stale = []

        async with self._lock:
            for websocket, last_heartbeat in self._heartbeats.items():
                if (now - last_heartbeat).total_seconds() > timeout_seconds:
                    stale.append((websocket, self._websocket_to_user.get(websocket)))

        for websocket, user_id in stale:
            if user_id is not None:
                try:
                    await websocket.close(code=4002, reason="Connection timeout")
                except Exception:
                    pass
                self.disconnect(websocket, user_id)

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale WebSocket connections")

        return len(stale)

    def get_connection_stats(self) -> dict:
        """Get statistics about current connections."""
        return {
            "total_connections": self.total_connections,
            "unique_users": len(self._connections),
            "connections_by_role": self._count_by_role(),
        }

    def _count_by_role(self) -> Dict[str, int]:
        """Count connections grouped by role."""
        counts: Dict[str, int] = {}
        for user_id, role in self._user_roles.items():
            if user_id in self._connections:
                counts[role] = counts.get(role, 0) + len(self._connections[user_id])
        return counts


# Global manager instance
manager = ConnectionManager()
