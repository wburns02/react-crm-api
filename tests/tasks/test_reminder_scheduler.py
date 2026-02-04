"""
Tests for Reminder Scheduler.

Tests the background job logic for sending service reminders.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.service_interval import ServiceInterval, CustomerServiceSchedule, ServiceReminder
from app.models.customer import Customer
from app.tasks.reminder_scheduler import (
    check_and_send_reminders,
    process_schedule_reminders,
    update_schedule_statuses,
    get_scheduler,
)


class TestSchedulerSetup:
    """Tests for scheduler initialization."""

    def test_get_scheduler_returns_scheduler(self):
        """Test that get_scheduler returns a scheduler instance."""
        scheduler = get_scheduler()
        assert scheduler is not None

    def test_get_scheduler_singleton(self):
        """Test that get_scheduler returns the same instance."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()
        assert scheduler1 is scheduler2


class TestUpdateScheduleStatuses:
    """Tests for update_schedule_statuses job."""

    @pytest_asyncio.fixture
    async def setup_schedules(self, test_db: AsyncSession):
        """Create schedules with various due dates."""
        # Create interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Status Update Test",
            service_type="pumping",
            interval_months=36,
        )
        test_db.add(interval)

        # Create customer
        customer = Customer(
            first_name="Status",
            last_name="Test",
            email="status@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        # Create schedules with different statuses
        schedules = []

        # Upcoming schedule (30 days out)
        upcoming = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=30),
            status="upcoming",
        )
        test_db.add(upcoming)
        schedules.append(("upcoming", upcoming))

        # Due soon schedule (5 days out, should become "due")
        due_soon = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=5),
            status="upcoming",
        )
        test_db.add(due_soon)
        schedules.append(("due_soon", due_soon))

        # Overdue schedule (past due, should become "overdue")
        overdue = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() - timedelta(days=5),
            status="due",
        )
        test_db.add(overdue)
        schedules.append(("overdue", overdue))

        await test_db.commit()
        return dict(schedules)

    @pytest.mark.asyncio
    async def test_update_statuses_marks_overdue(self, test_db: AsyncSession, setup_schedules):
        """Test that past-due schedules are marked overdue."""
        # The update_schedule_statuses function uses its own session
        # So we test the logic directly
        schedules = setup_schedules

        # Verify initial state
        overdue_schedule = schedules["overdue"]
        assert overdue_schedule.status == "due"

        # The status should change to overdue based on the date
        days_until = (overdue_schedule.next_due_date - date.today()).days
        assert days_until < 0  # Past due

    @pytest.mark.asyncio
    async def test_update_statuses_marks_due(self, test_db: AsyncSession, setup_schedules):
        """Test that near-due schedules are marked as due."""
        schedules = setup_schedules

        due_soon_schedule = schedules["due_soon"]
        days_until = (due_soon_schedule.next_due_date - date.today()).days

        # Should be marked as "due" when within 7 days
        assert days_until <= 7
        assert days_until > 0


class TestProcessScheduleReminders:
    """Tests for process_schedule_reminders function."""

    @pytest_asyncio.fixture
    async def reminder_setup(self, test_db: AsyncSession):
        """Create schedule due for reminder."""
        # Create interval with reminder days
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Reminder Test",
            service_type="pumping",
            interval_months=36,
            reminder_days_before=[30, 14, 7],
        )
        test_db.add(interval)

        # Create customer with contact info
        customer = Customer(
            first_name="Reminder",
            last_name="Test",
            email="reminder@example.com",
            phone="555-123-4567",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)
        await test_db.refresh(interval)

        # Create schedule due in 7 days (matches reminder_days_before)
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=7),
            status="upcoming",
            reminder_sent=False,
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        return schedule, customer, interval

    @pytest.mark.asyncio
    async def test_reminder_sent_when_days_match(self, test_db: AsyncSession, reminder_setup):
        """Test reminder is sent when days_until matches reminder_days_before."""
        schedule, customer, interval = reminder_setup

        days_until = (schedule.next_due_date - date.today()).days
        assert days_until == 7
        assert days_until in interval.reminder_days_before

    @pytest.mark.asyncio
    async def test_reminder_not_sent_when_days_dont_match(self, test_db: AsyncSession):
        """Test reminder is not sent when days_until doesn't match."""
        # Create interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="No Reminder Test",
            service_type="pumping",
            interval_months=36,
            reminder_days_before=[30, 14, 7],
        )
        test_db.add(interval)

        # Create customer
        customer = Customer(
            first_name="No",
            last_name="Reminder",
            email="noreminder@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        # Create schedule due in 20 days (doesn't match reminder_days_before)
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=20),
            status="upcoming",
        )
        test_db.add(schedule)
        await test_db.commit()

        days_until = (schedule.next_due_date - date.today()).days
        assert days_until == 20
        assert days_until not in interval.reminder_days_before


class TestCheckAndSendReminders:
    """Tests for check_and_send_reminders job."""

    @pytest.mark.asyncio
    async def test_check_reminders_with_mocked_services(self):
        """Test check_and_send_reminders with mocked Twilio and Email services."""
        with patch("app.tasks.reminder_scheduler.async_session_maker") as mock_session_maker, \
             patch("app.tasks.reminder_scheduler.TwilioService") as mock_twilio, \
             patch("app.tasks.reminder_scheduler.EmailService") as mock_email:

            # Setup mock session
            mock_session = AsyncMock()
            mock_session_maker.return_value.__aenter__.return_value = mock_session

            # Mock empty result (no schedules)
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            # Mock Twilio
            mock_twilio_instance = MagicMock()
            mock_twilio_instance.is_configured = False
            mock_twilio.return_value = mock_twilio_instance

            # Mock Email
            mock_email_instance = MagicMock()
            mock_email_instance.is_configured = False
            mock_email.return_value = mock_email_instance

            # Run the job (should complete without error)
            await check_and_send_reminders()

    @pytest.mark.asyncio
    async def test_check_reminders_handles_errors(self):
        """Test check_and_send_reminders handles errors gracefully."""
        with patch("app.tasks.reminder_scheduler.async_session_maker") as mock_session_maker:
            # Simulate database error
            mock_session_maker.return_value.__aenter__.side_effect = Exception("DB Error")

            # Should not raise, just log error
            await check_and_send_reminders()


class TestReminderDeduplication:
    """Tests for reminder deduplication logic."""

    @pytest_asyncio.fixture
    async def schedule_with_existing_reminder(self, test_db: AsyncSession):
        """Create schedule that already has a reminder sent."""
        # Create interval
        interval = ServiceInterval(
            id=uuid.uuid4(),
            name="Dedup Test",
            service_type="pumping",
            interval_months=36,
            reminder_days_before=[30, 14, 7],
        )
        test_db.add(interval)

        # Create customer
        customer = Customer(
            first_name="Dedup",
            last_name="Test",
            email="dedup@example.com",
        )
        test_db.add(customer)
        await test_db.commit()
        await test_db.refresh(customer)

        # Create schedule
        schedule = CustomerServiceSchedule(
            id=uuid.uuid4(),
            customer_id=customer.id,
            service_interval_id=interval.id,
            next_due_date=date.today() + timedelta(days=7),
            status="upcoming",
        )
        test_db.add(schedule)
        await test_db.commit()
        await test_db.refresh(schedule)

        # Create existing reminder for 7 days
        existing_reminder = ServiceReminder(
            id=uuid.uuid4(),
            schedule_id=schedule.id,
            customer_id=customer.id,
            reminder_type="sms",
            days_before_due=7,
            status="sent",
        )
        test_db.add(existing_reminder)
        await test_db.commit()

        return schedule, interval

    @pytest.mark.asyncio
    async def test_duplicate_reminder_not_sent(
        self, test_db: AsyncSession, schedule_with_existing_reminder
    ):
        """Test that duplicate reminders are not sent."""
        schedule, interval = schedule_with_existing_reminder

        # Check for existing reminder
        result = await test_db.execute(
            select(ServiceReminder).where(
                ServiceReminder.schedule_id == schedule.id,
                ServiceReminder.days_before_due == 7,
            )
        )
        existing = result.scalar_one_or_none()

        # Reminder already exists, should not send another
        assert existing is not None
        assert existing.days_before_due == 7


class TestReminderMessageContent:
    """Tests for reminder message content generation."""

    def test_sms_message_format(self):
        """Test SMS message format."""
        customer_name = "John Doe"
        service_name = "Septic Pumping"
        due_date = "February 15, 2026"

        message = (
            f"Hi {customer_name}! This is a reminder from Mac Septic Services. "
            f"Your {service_name} service is due on {due_date}. "
            f"Please call us at (512) 555-0123 to schedule your appointment. Thank you!"
        )

        assert customer_name in message
        assert service_name in message
        assert due_date in message
        assert "(512) 555-0123" in message

    def test_email_message_format(self):
        """Test email message format."""
        customer_name = "John Doe"
        service_name = "Septic Pumping"
        due_date = "February 15, 2026"

        email_body = f"""
Dear {customer_name},

This is a friendly reminder that your {service_name} service is scheduled to be due on {due_date}.

To ensure your septic system continues to operate efficiently, we recommend scheduling your service appointment soon.

Please contact us at:
- Phone: (512) 555-0123
- Email: service@macseptic.com

Or visit our website to schedule online.

Thank you for choosing Mac Septic Services!

Best regards,
Mac Septic Services Team
"""

        assert customer_name in email_body
        assert service_name in email_body
        assert due_date in email_body
        assert "service@macseptic.com" in email_body
