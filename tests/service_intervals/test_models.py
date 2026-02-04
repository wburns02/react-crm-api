"""
Tests for Service Interval models.

Tests model creation, validation, and relationships.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.service_interval import ServiceInterval, CustomerServiceSchedule, ServiceReminder
from app.models.customer import Customer


class TestServiceIntervalModel:
    """Tests for ServiceInterval model."""

    @pytest.mark.asyncio
    async def test_create_service_interval(self, test_db: AsyncSession):
        """Test creating a service interval."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="3-Year Septic Pumping",
            description="Standard septic tank pumping service",
            service_type="pumping",
            interval_months=36,
            reminder_days_before=[30, 14, 7],
            is_active=True,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)

        assert interval.id is not None
        assert interval.name == "3-Year Septic Pumping"
        assert interval.service_type == "pumping"
        assert interval.interval_months == 36
        assert interval.reminder_days_before == [30, 14, 7]
        assert interval.is_active is True

    @pytest.mark.asyncio
    async def test_service_interval_defaults(self, test_db: AsyncSession):
        """Test service interval default values."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Test Interval",
            service_type="inspection",
            interval_months=12,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)

        assert interval.is_active is True
        assert interval.reminder_days_before == [30, 14, 7]
        assert interval.created_at is not None

    @pytest.mark.asyncio
    async def test_service_interval_repr(self, test_db: AsyncSession):
        """Test service interval string representation."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Annual Inspection",
            service_type="inspection",
            interval_months=12,
        )
        test_db.add(interval)
        await test_db.commit()

        assert "Annual Inspection" in repr(interval)
        assert "12 months" in repr(interval)


class TestCustomerServiceScheduleModel:
    """Tests for CustomerServiceSchedule model."""

    @pytest_asyncio.fixture
    async def service_interval(self, test_db: AsyncSession):
        """Create a service interval for testing."""
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Test Pumping",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)
        return interval

    @pytest_asyncio.fixture
    async def customer(self, test_db: AsyncSession):
        """Create a customer for testing."""
        customer = Customer(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            phone="555-1234",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)
        return customer

    @pytest.mark.asyncio
    async def test_create_schedule(
        self, test_db: AsyncSession, service_interval: ServiceInterval, customer: Customer
    ):
        """Test creating a customer service schedule."""
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=service_interval.id,
            last_service_date=date.today() - timedelta(days=365),
            next_due_date=date.today() + timedelta(days=730),
            status="upcoming",
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        assert schedule.id is not None
        assert schedule.customer_id == customer.id
        assert schedule.service_interval_id == service_interval.id
        assert schedule.status == "upcoming"

    @pytest.mark.asyncio
    async def test_schedule_defaults(
        self, test_db: AsyncSession, service_interval: ServiceInterval, customer: Customer
    ):
        """Test schedule default values."""
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=service_interval.id,
            next_due_date=date.today() + timedelta(days=30),
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        assert schedule.status == "upcoming"
        assert schedule.reminder_sent is False
        assert schedule.scheduled_work_order_id is None

    @pytest.mark.asyncio
    async def test_schedule_relationship_to_interval(
        self, test_db: AsyncSession, service_interval: ServiceInterval, customer: Customer
    ):
        """Test schedule has relationship to service interval."""
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=service_interval.id,
            next_due_date=date.today() + timedelta(days=30),
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        # Query with relationship
        result = await test_db.execute(
            select(CustomerServiceSchedule).where(CustomerServiceSchedule.id == schedule.id)
        )
        loaded_schedule = result.scalar_one()

        # Refresh to load relationship
        await test_db.refresh(loaded_schedule)
        assert loaded_schedule.service_interval is not None
        assert loaded_schedule.service_interval.name == "Test Pumping"


class TestServiceReminderModel:
    """Tests for ServiceReminder model."""

    @pytest_asyncio.fixture
    async def schedule_with_customer(self, test_db: AsyncSession):
        """Create a schedule with customer for testing."""
        # Create customer
        customer = Customer(
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        # Create interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Test Interval",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)
        await test_db.commit()
        await test_db.refresh(interval)

        # Create schedule
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=7),
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        return schedule, customer

    @pytest.mark.asyncio
    async def test_create_reminder(self, test_db: AsyncSession, schedule_with_customer):
        """Test creating a service reminder."""
        schedule, customer = schedule_with_customer

        reminder = ServiceReminder(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            customer_id=customer.id,
            reminder_type="sms",
            days_before_due=7,
            status="sent",
        )
        test_db.add(reminder)
        await test_db.commit()
        await test_db.refresh(reminder)

        assert reminder.id is not None
        assert reminder.schedule_id == schedule.id
        assert reminder.customer_id == customer.id
        assert reminder.reminder_type == "sms"
        assert reminder.days_before_due == 7
        assert reminder.status == "sent"

    @pytest.mark.asyncio
    async def test_reminder_types(self, test_db: AsyncSession, schedule_with_customer):
        """Test different reminder types."""
        schedule, customer = schedule_with_customer

        for reminder_type in ["sms", "email", "push"]:
            reminder = ServiceReminder(
                id=uuid.uuid4(),
                schedule_id=schedule.id,
                customer_id=customer.id,
                reminder_type=reminder_type,
                status="sent",
            )
            test_db.add(reminder)
            await test_db.commit()
            await test_db.refresh(reminder)
            assert reminder.reminder_type == reminder_type

    @pytest.mark.asyncio
    async def test_failed_reminder(self, test_db: AsyncSession, schedule_with_customer):
        """Test failed reminder with error message."""
        schedule, customer = schedule_with_customer

        reminder = ServiceReminder(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            customer_id=customer.id,
            reminder_type="sms",
            status="failed",
            error_message="Invalid phone number",
        )
        test_db.add(reminder)
        await test_db.commit()
        await test_db.refresh(reminder)

        assert reminder.status == "failed"
        assert reminder.error_message == "Invalid phone number"
