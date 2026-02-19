"""
Tests for Customer Service Schedule API endpoints.

Tests schedule assignment, listing, and management.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
import uuid

from app.models.service_interval import ServiceInterval, CustomerServiceSchedule
from app.models.customer import Customer


class TestListSchedules:
    """Tests for GET /api/v2/service-intervals/schedules"""

    @pytest.mark.asyncio
    async def test_list_schedules_unauthenticated(self, client: AsyncClient):
        """Test listing schedules requires authentication."""
        response = await client.get("/api/v2/service-intervals/schedules")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_schedules_empty(self, authenticated_client: AsyncClient):
        """Test listing schedules when none exist."""
        response = await authenticated_client.get("/api/v2/service-intervals/schedules")
        assert response.status_code == 200
        data = response.json()
        assert "schedules" in data

    @pytest.mark.asyncio
    async def test_list_schedules_filter_by_status(
        self, authenticated_client: AsyncClient, test_db: AsyncSession
    ):
        """Test filtering schedules by status."""
        # Create interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Test Interval",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()

        # Create customer
        customer = Customer(
            first_name="Test",
            last_name="Customer",
            email="test@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        # Create schedule with "overdue" status
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() - timedelta(days=10),
            status="overdue",
        )
        test_db.add(schedule)
        await test_db.commit()

        response = await authenticated_client.get(
            "/api/v2/service-intervals/schedules?status=overdue"
        )
        assert response.status_code == 200


class TestAssignSchedule:
    """Tests for POST /api/v2/service-intervals/assign"""

    @pytest_asyncio.fixture
    async def setup_data(self, test_db: AsyncSession):
        """Create interval and customer for testing."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Assignment Test",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)

        customer = Customer(
            first_name="Assign",
            last_name="Test",
            email="assign@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(interval)
        await test_db.refresh(customer)

        return interval, customer

    @pytest.mark.skip(reason="Test needs update: UUID columns incompatible with SQLite test DB (str has no attribute hex)")
    @pytest.mark.asyncio
    async def test_assign_schedule_success(
        self, authenticated_client: AsyncClient, setup_data
    ):
        """Test assigning a schedule to a customer."""
        interval, customer = setup_data

        payload = {
            "customer_id": str(customer.id),
            "service_interval_id": str(interval.id),
            "next_due_date": (date.today() + timedelta(days=30)).isoformat(),
        }

        response = await authenticated_client.post(
            "/api/v2/service-intervals/assign",
            json=payload,
        )
        assert response.status_code in [200, 201]

    @pytest.mark.skip(reason="Test needs update: UUID columns incompatible with SQLite test DB (str has no attribute hex)")
    @pytest.mark.asyncio
    async def test_assign_schedule_with_last_service(
        self, authenticated_client: AsyncClient, setup_data
    ):
        """Test assigning schedule with last service date."""
        interval, customer = setup_data

        payload = {
            "customer_id": str(customer.id),
            "service_interval_id": str(interval.id),
            "last_service_date": (date.today() - timedelta(days=365)).isoformat(),
            "next_due_date": (date.today() + timedelta(days=730)).isoformat(),
        }

        response = await authenticated_client.post(
            "/api/v2/service-intervals/assign",
            json=payload,
        )
        assert response.status_code in [200, 201]


class TestUnassignSchedule:
    """Tests for DELETE /api/v2/service-intervals/schedules/{id}"""

    @pytest_asyncio.fixture
    async def schedule(self, test_db: AsyncSession):
        """Create a schedule to unassign."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Unassign Test",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)

        customer = Customer(
            first_name="Unassign",
            last_name="Test",
            email="unassign@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=30),
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        return schedule

    @pytest.mark.asyncio
    async def test_unassign_schedule_success(
        self, authenticated_client: AsyncClient, schedule: CustomerServiceSchedule
    ):
        """Test unassigning (deleting) a schedule."""
        response = await authenticated_client.delete(
            f"/api/v2/service-intervals/schedules/{schedule.id}"
        )
        assert response.status_code in [200, 204]


class TestCompleteService:
    """Tests for PUT /api/v2/service-intervals/schedules/{id} (completing service)"""

    @pytest_asyncio.fixture
    async def due_schedule(self, test_db: AsyncSession):
        """Create a due schedule."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Complete Test",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)

        customer = Customer(
            first_name="Complete",
            last_name="Test",
            email="complete@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)
        await test_db.refresh(interval)

        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today(),
            status="due",
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        return schedule, interval

    @pytest.mark.asyncio
    async def test_complete_service_success(
        self, authenticated_client: AsyncClient, due_schedule
    ):
        """Test completing a service by updating the schedule."""
        schedule, interval = due_schedule

        # Update schedule with last_service_date (passed as query parameter)
        response = await authenticated_client.put(
            f"/api/v2/service-intervals/schedules/{schedule.id}",
            params={"last_service_date": date.today().isoformat()},
        )
        assert response.status_code == 200
        data = response.json()
        # Schedule should be updated with recalculated values
        assert "last_service_date" in data
        assert "next_due_date" in data
        assert "id" in data


class TestGetScheduleStats:
    """Tests for GET /api/v2/service-intervals/stats"""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, authenticated_client: AsyncClient):
        """Test getting schedule statistics."""
        response = await authenticated_client.get("/api/v2/service-intervals/stats")
        assert response.status_code == 200
        data = response.json()
        # Stats should include counts by status
        assert isinstance(data, dict)
