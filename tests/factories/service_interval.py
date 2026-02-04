"""
Service Interval test factories.

Generates realistic service interval, schedule, and reminder data for testing.
"""

import factory
from faker import Faker
from datetime import date, timedelta
import uuid

fake = Faker()


class ServiceIntervalFactory(factory.Factory):
    """
    Factory for generating ServiceInterval test data.

    Usage:
        interval = ServiceIntervalFactory()
        interval = ServiceIntervalFactory(service_type="pumping")
        intervals = ServiceIntervalFactory.create_batch(5)
    """

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    name = factory.LazyFunction(
        lambda: fake.random_element([
            "Annual Septic Pumping",
            "Quarterly Grease Trap",
            "Annual Inspection",
            "3-Year Septic Pumping",
            "Monthly Maintenance",
        ])
    )
    description = factory.LazyFunction(fake.sentence)
    service_type = factory.LazyFunction(
        lambda: fake.random_element(["pumping", "grease_trap", "inspection", "maintenance"])
    )
    interval_months = factory.LazyFunction(
        lambda: fake.random_element([3, 6, 12, 24, 36])
    )
    reminder_days_before = [30, 14, 7]
    is_active = True
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class PumpingIntervalFactory(ServiceIntervalFactory):
    """Factory for pumping service intervals."""

    name = "Septic Pumping"
    service_type = "pumping"
    interval_months = 36


class GreaseTrapIntervalFactory(ServiceIntervalFactory):
    """Factory for grease trap service intervals."""

    name = "Grease Trap Cleaning"
    service_type = "grease_trap"
    interval_months = 3


class InspectionIntervalFactory(ServiceIntervalFactory):
    """Factory for inspection service intervals."""

    name = "Annual Inspection"
    service_type = "inspection"
    interval_months = 12


class CustomerServiceScheduleFactory(factory.Factory):
    """
    Factory for generating CustomerServiceSchedule test data.

    Usage:
        schedule = CustomerServiceScheduleFactory()
        schedule = CustomerServiceScheduleFactory(status="overdue")
    """

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    customer_id = factory.Sequence(lambda n: n + 1)
    service_interval_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    last_service_date = factory.LazyFunction(
        lambda: (date.today() - timedelta(days=fake.random_int(min=30, max=365))).isoformat()
    )
    next_due_date = factory.LazyFunction(
        lambda: (date.today() + timedelta(days=fake.random_int(min=-30, max=90))).isoformat()
    )
    status = factory.LazyFunction(
        lambda: fake.random_element(["upcoming", "due", "overdue", "scheduled"])
    )
    scheduled_work_order_id = None
    reminder_sent = False
    last_reminder_sent_at = None
    notes = factory.LazyFunction(
        lambda: fake.sentence() if fake.boolean(chance_of_getting_true=20) else None
    )
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class UpcomingScheduleFactory(CustomerServiceScheduleFactory):
    """Factory for upcoming schedules (due in future)."""

    status = "upcoming"
    next_due_date = factory.LazyFunction(
        lambda: (date.today() + timedelta(days=fake.random_int(min=30, max=90))).isoformat()
    )


class DueScheduleFactory(CustomerServiceScheduleFactory):
    """Factory for due schedules (due within 7 days)."""

    status = "due"
    next_due_date = factory.LazyFunction(
        lambda: (date.today() + timedelta(days=fake.random_int(min=1, max=7))).isoformat()
    )


class OverdueScheduleFactory(CustomerServiceScheduleFactory):
    """Factory for overdue schedules (past due date)."""

    status = "overdue"
    next_due_date = factory.LazyFunction(
        lambda: (date.today() - timedelta(days=fake.random_int(min=1, max=30))).isoformat()
    )


class ServiceReminderFactory(factory.Factory):
    """
    Factory for generating ServiceReminder test data.

    Usage:
        reminder = ServiceReminderFactory()
        reminder = ServiceReminderFactory(reminder_type="email")
    """

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    schedule_id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    customer_id = factory.Sequence(lambda n: n + 1)
    reminder_type = factory.LazyFunction(
        lambda: fake.random_element(["sms", "email", "push"])
    )
    days_before_due = factory.LazyFunction(
        lambda: fake.random_element([30, 14, 7])
    )
    status = "sent"
    error_message = None
    message_id = None
    sent_at = factory.LazyFunction(lambda: fake.date_time_this_month().isoformat())
    delivered_at = None


class SMSReminderFactory(ServiceReminderFactory):
    """Factory for SMS reminders."""

    reminder_type = "sms"


class EmailReminderFactory(ServiceReminderFactory):
    """Factory for email reminders."""

    reminder_type = "email"


class FailedReminderFactory(ServiceReminderFactory):
    """Factory for failed reminders."""

    status = "failed"
    error_message = factory.LazyFunction(fake.sentence)
