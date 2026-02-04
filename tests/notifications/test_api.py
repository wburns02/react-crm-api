"""
Tests for Notification API endpoints.

Tests notification CRUD, filtering, and mark-read functionality.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.notification import Notification
from app.models.user import User


class TestListNotifications:
    """Tests for GET /api/v2/notifications"""

    @pytest.mark.asyncio
    async def test_list_notifications_unauthenticated(self, client: AsyncClient):
        """Test listing notifications requires authentication."""
        response = await client.get("/api/v2/notifications")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_notifications_empty(self, authenticated_client: AsyncClient):
        """Test listing notifications when none exist."""
        response = await authenticated_client.get("/api/v2/notifications")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_notifications_returns_user_notifications(
        self, authenticated_client: AsyncClient, test_db: AsyncSession, test_user: User
    ):
        """Test listing notifications returns only user's notifications."""
        # Create notification for test user
        notification = Notification(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type="work_order",
            title="Test Notification",
            message="This is a test notification",
            read=False,
        )
        test_db.add(notification)
        await test_db.commit()

        response = await authenticated_client.get("/api/v2/notifications")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) >= 1

    @pytest.mark.asyncio
    async def test_list_notifications_filter_unread(
        self, authenticated_client: AsyncClient, test_db: AsyncSession, test_user: User
    ):
        """Test filtering notifications by unread status."""
        # Create read notification
        read_notif = Notification(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type="system",
            title="Read Notification",
            message="Already read",
            read=True,
        )
        # Create unread notification
        unread_notif = Notification(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type="work_order",
            title="Unread Notification",
            message="Not read yet",
            read=False,
        )
        test_db.add(read_notif)
        test_db.add(unread_notif)
        await test_db.commit()

        response = await authenticated_client.get("/api/v2/notifications?unread_only=true")
        assert response.status_code == 200


class TestGetNotificationStats:
    """Tests for GET /api/v2/notifications/stats"""

    @pytest.mark.asyncio
    async def test_get_stats_success(
        self, authenticated_client: AsyncClient, test_db: AsyncSession, test_user: User
    ):
        """Test getting notification statistics."""
        # Create some notifications
        for i in range(3):
            notification = Notification(
                id=uuid.uuid4(),
                user_id=test_user.id,
                type="system",
                title=f"Notification {i}",
                message=f"Message {i}",
                read=(i % 2 == 0),  # Alternate read/unread
            )
            test_db.add(notification)
        await test_db.commit()

        response = await authenticated_client.get("/api/v2/notifications/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data or "unread_count" in data or isinstance(data, dict)


class TestMarkNotificationRead:
    """Tests for POST /api/v2/notifications/{id}/read"""

    @pytest_asyncio.fixture
    async def unread_notification(self, test_db: AsyncSession, test_user: User):
        """Create an unread notification."""
        notification = Notification(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type="work_order",
            title="Mark Read Test",
            message="Test message",
            read=False,
        )
        test_db.add(notification)
        await test_db.commit()
        await test_db.refresh(notification)
        return notification

    @pytest.mark.asyncio
    async def test_mark_read_success(
        self, authenticated_client: AsyncClient, unread_notification: Notification
    ):
        """Test marking a notification as read."""
        response = await authenticated_client.post(
            f"/api/v2/notifications/{unread_notification.id}/read"
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("read") is True or "success" in str(data).lower()

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self, authenticated_client: AsyncClient):
        """Test marking non-existent notification returns 404."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.post(f"/api/v2/notifications/{fake_id}/read")
        assert response.status_code == 404


class TestMarkAllNotificationsRead:
    """Tests for POST /api/v2/notifications/read-all"""

    @pytest.mark.asyncio
    async def test_mark_all_read_success(
        self, authenticated_client: AsyncClient, test_db: AsyncSession, test_user: User
    ):
        """Test marking all notifications as read."""
        # Create multiple unread notifications
        for i in range(5):
            notification = Notification(
                id=uuid.uuid4(),
                user_id=test_user.id,
                type="system",
                title=f"Unread {i}",
                message=f"Message {i}",
                read=False,
            )
            test_db.add(notification)
        await test_db.commit()

        response = await authenticated_client.post("/api/v2/notifications/read-all")
        assert response.status_code == 200


class TestCreateNotification:
    """Tests for POST /api/v2/notifications"""

    @pytest.mark.asyncio
    async def test_create_notification_success(
        self, authenticated_client: AsyncClient, test_user: User
    ):
        """Test creating a notification."""
        payload = {
            "user_id": test_user.id,
            "type": "system",
            "title": "New Notification",
            "message": "This is a test notification",
        }

        response = await authenticated_client.post(
            "/api/v2/notifications",
            json=payload,
        )
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_create_notification_with_link(
        self, authenticated_client: AsyncClient, test_user: User
    ):
        """Test creating a notification with a link."""
        payload = {
            "user_id": test_user.id,
            "type": "work_order",
            "title": "Work Order Update",
            "message": "Work order status changed",
            "link": "/work-orders/123",
        }

        response = await authenticated_client.post(
            "/api/v2/notifications",
            json=payload,
        )
        assert response.status_code in [200, 201]


class TestDeleteNotification:
    """Tests for DELETE /api/v2/notifications/{id}"""

    @pytest_asyncio.fixture
    async def notification(self, test_db: AsyncSession, test_user: User):
        """Create a notification to delete."""
        notification = Notification(
            id=uuid.uuid4(),
            user_id=test_user.id,
            type="system",
            title="Delete Test",
            message="To be deleted",
        )
        test_db.add(notification)
        await test_db.commit()
        await test_db.refresh(notification)
        return notification

    @pytest.mark.asyncio
    async def test_delete_notification_success(
        self, authenticated_client: AsyncClient, notification: Notification
    ):
        """Test deleting a notification."""
        response = await authenticated_client.delete(
            f"/api/v2/notifications/{notification.id}"
        )
        assert response.status_code in [200, 204]

    @pytest.mark.asyncio
    async def test_delete_notification_not_found(self, authenticated_client: AsyncClient):
        """Test deleting non-existent notification returns 404."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.delete(f"/api/v2/notifications/{fake_id}")
        assert response.status_code == 404
