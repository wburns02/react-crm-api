"""
Tests for Service Interval API endpoints.

Tests CRUD operations for service interval templates.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.models.service_interval import ServiceInterval


class TestListServiceIntervals:
    """Tests for GET /api/v2/service-intervals/"""

    @pytest.mark.asyncio
    async def test_list_intervals_unauthenticated(self, client: AsyncClient):
        """Test listing intervals requires authentication."""
        response = await client.get("/api/v2/service-intervals/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_intervals_empty(self, authenticated_client: AsyncClient):
        """Test listing intervals when none exist."""
        response = await authenticated_client.get("/api/v2/service-intervals/")
        assert response.status_code == 200
        data = response.json()
        assert "intervals" in data
        assert isinstance(data["intervals"], list)

    @pytest.mark.asyncio
    async def test_list_intervals_with_data(
        self, authenticated_client: AsyncClient, test_db: AsyncSession
    ):
        """Test listing intervals returns data."""
        # Create test interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Test Pumping",
            service_type="pumping",
            interval_months=36,
            is_active=True,
        )
        test_db.add(interval)
        await test_db.commit()

        response = await authenticated_client.get("/api/v2/service-intervals/")
        assert response.status_code == 200
        data = response.json()
        assert len(data["intervals"]) >= 1


class TestCreateServiceInterval:
    """Tests for POST /api/v2/service-intervals/"""

    @pytest.mark.asyncio
    async def test_create_interval_success(self, authenticated_client: AsyncClient):
        """Test creating a service interval."""
        payload = {
            "name": "Annual Inspection",
            "description": "Yearly septic system inspection",
            "service_type": "inspection",
            "interval_months": 12,
            "reminder_days_before": [30, 14, 7],
        }

        response = await authenticated_client.post(
            "/api/v2/service-intervals/",
            json=payload,
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Annual Inspection"
        assert data["service_type"] == "inspection"
        assert data["interval_months"] == 12

    @pytest.mark.asyncio
    async def test_create_interval_minimal(self, authenticated_client: AsyncClient):
        """Test creating interval with minimal required fields."""
        payload = {
            "name": "Quick Service",
            "service_type": "maintenance",
            "interval_months": 6,
        }

        response = await authenticated_client.post(
            "/api/v2/service-intervals/",
            json=payload,
        )
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "Quick Service"

    @pytest.mark.asyncio
    async def test_create_interval_unauthenticated(self, client: AsyncClient):
        """Test creating interval requires authentication."""
        payload = {
            "name": "Test",
            "service_type": "pumping",
            "interval_months": 12,
        }
        response = await client.post("/api/v2/service-intervals/", json=payload)
        assert response.status_code == 401


class TestGetServiceInterval:
    """Tests for GET /api/v2/service-intervals/{id}"""

    @pytest_asyncio.fixture
    async def test_interval(self, test_db: AsyncSession):
        """Create a test interval."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Get Test Interval",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)
        return interval

    @pytest.mark.asyncio
    async def test_get_interval_success(
        self, authenticated_client: AsyncClient, test_interval: ServiceInterval
    ):
        """Test getting a specific interval."""
        response = await authenticated_client.get(
            f"/api/v2/service-intervals/{test_interval.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Interval"

    @pytest.mark.asyncio
    async def test_get_interval_not_found(self, authenticated_client: AsyncClient):
        """Test getting non-existent interval returns 404."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.get(f"/api/v2/service-intervals/{fake_id}")
        assert response.status_code == 404


class TestUpdateServiceInterval:
    """Tests for PUT /api/v2/service-intervals/{id}"""

    @pytest_asyncio.fixture
    async def test_interval(self, test_db: AsyncSession):
        """Create a test interval."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Update Test Interval",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)
        return interval

    @pytest.mark.asyncio
    async def test_update_interval_success(
        self, authenticated_client: AsyncClient, test_interval: ServiceInterval
    ):
        """Test updating a service interval."""
        payload = {
            "name": "Updated Name",
            "interval_months": 24,
        }
        response = await authenticated_client.put(
            f"/api/v2/service-intervals/{test_interval.id}",
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["interval_months"] == 24

    @pytest.mark.asyncio
    async def test_update_interval_not_found(self, authenticated_client: AsyncClient):
        """Test updating non-existent interval returns 404."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.put(
            f"/api/v2/service-intervals/{fake_id}",
            json={"name": "Test"},
        )
        assert response.status_code == 404


class TestDeleteServiceInterval:
    """Tests for DELETE /api/v2/service-intervals/{id}"""

    @pytest_asyncio.fixture
    async def test_interval(self, test_db: AsyncSession):
        """Create a test interval."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Delete Test Interval",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)
        return interval

    @pytest.mark.asyncio
    async def test_delete_interval_success(
        self, authenticated_client: AsyncClient, test_interval: ServiceInterval
    ):
        """Test deleting a service interval."""
        response = await authenticated_client.delete(
            f"/api/v2/service-intervals/{test_interval.id}"
        )
        assert response.status_code in [200, 204]

        # Verify deleted
        get_response = await authenticated_client.get(
            f"/api/v2/service-intervals/{test_interval.id}"
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_interval_not_found(self, authenticated_client: AsyncClient):
        """Test deleting non-existent interval returns 404."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.delete(
            f"/api/v2/service-intervals/{fake_id}"
        )
        assert response.status_code == 404
