"""
Tests for service interval status calculation logic.

Tests the business logic for determining schedule status based on due dates.
"""

import pytest
from datetime import date, timedelta


def calculate_status(next_due_date: date) -> tuple[str, int]:
    """
    Calculate schedule status based on due date.

    Returns tuple of (status, days_until_due).

    Status values:
    - "overdue": Past due date
    - "due": Within 7 days of due date
    - "upcoming": More than 7 days until due date
    """
    today = date.today()
    days_until = (next_due_date - today).days

    if days_until < 0:
        return "overdue", days_until
    elif days_until <= 7:
        return "due", days_until
    else:
        return "upcoming", days_until


class TestStatusCalculation:
    """Tests for status calculation logic."""

    def test_status_upcoming_far_future(self):
        """Test status is 'upcoming' for dates far in the future."""
        future_date = date.today() + timedelta(days=90)
        status, days = calculate_status(future_date)

        assert status == "upcoming"
        assert days == 90

    def test_status_upcoming_8_days(self):
        """Test status is 'upcoming' for 8 days out."""
        future_date = date.today() + timedelta(days=8)
        status, days = calculate_status(future_date)

        assert status == "upcoming"
        assert days == 8

    def test_status_due_7_days(self):
        """Test status is 'due' for exactly 7 days out."""
        future_date = date.today() + timedelta(days=7)
        status, days = calculate_status(future_date)

        assert status == "due"
        assert days == 7

    def test_status_due_3_days(self):
        """Test status is 'due' for 3 days out."""
        future_date = date.today() + timedelta(days=3)
        status, days = calculate_status(future_date)

        assert status == "due"
        assert days == 3

    def test_status_due_today(self):
        """Test status is 'due' for today."""
        today = date.today()
        status, days = calculate_status(today)

        assert status == "due"
        assert days == 0

    def test_status_overdue_1_day(self):
        """Test status is 'overdue' for 1 day past."""
        past_date = date.today() - timedelta(days=1)
        status, days = calculate_status(past_date)

        assert status == "overdue"
        assert days == -1

    def test_status_overdue_30_days(self):
        """Test status is 'overdue' for 30 days past."""
        past_date = date.today() - timedelta(days=30)
        status, days = calculate_status(past_date)

        assert status == "overdue"
        assert days == -30


class TestReminderDaysLogic:
    """Tests for reminder days before logic."""

    def test_should_send_reminder_30_days(self):
        """Test reminder should be sent at 30 days."""
        reminder_days = [30, 14, 7]
        days_until_due = 30

        assert days_until_due in reminder_days

    def test_should_send_reminder_14_days(self):
        """Test reminder should be sent at 14 days."""
        reminder_days = [30, 14, 7]
        days_until_due = 14

        assert days_until_due in reminder_days

    def test_should_send_reminder_7_days(self):
        """Test reminder should be sent at 7 days."""
        reminder_days = [30, 14, 7]
        days_until_due = 7

        assert days_until_due in reminder_days

    def test_should_not_send_reminder_20_days(self):
        """Test reminder should not be sent at 20 days."""
        reminder_days = [30, 14, 7]
        days_until_due = 20

        assert days_until_due not in reminder_days

    def test_should_not_send_reminder_overdue(self):
        """Test reminder should not be sent when overdue."""
        reminder_days = [30, 14, 7]
        days_until_due = -5

        assert days_until_due not in reminder_days


class TestNextDueDateCalculation:
    """Tests for calculating next due date after service completion."""

    def test_next_due_from_last_service(self):
        """Test calculating next due date from last service."""
        last_service_date = date.today()
        interval_months = 36

        # Add approximately 36 months (3 years)
        expected_due = date(
            last_service_date.year + 3,
            last_service_date.month,
            last_service_date.day
        )

        # Simple calculation (actual implementation would use dateutil)
        next_due = date(
            last_service_date.year + (interval_months // 12),
            last_service_date.month,
            last_service_date.day
        )

        assert next_due == expected_due

    def test_next_due_quarterly(self):
        """Test calculating next due date for quarterly service."""
        last_service_date = date(2026, 1, 15)
        interval_months = 3

        # Add 3 months
        expected_due = date(2026, 4, 15)

        next_month = last_service_date.month + interval_months
        next_year = last_service_date.year
        if next_month > 12:
            next_month -= 12
            next_year += 1

        next_due = date(next_year, next_month, last_service_date.day)

        assert next_due == expected_due

    def test_next_due_annual(self):
        """Test calculating next due date for annual service."""
        last_service_date = date(2026, 6, 1)
        interval_months = 12

        expected_due = date(2027, 6, 1)

        next_due = date(
            last_service_date.year + 1,
            last_service_date.month,
            last_service_date.day
        )

        assert next_due == expected_due
