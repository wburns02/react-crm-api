"""
Work Order test factory.

Generates realistic work order data for testing.
"""

import factory
from faker import Faker
from datetime import datetime, timedelta

fake = Faker()

SERVICE_TYPES = [
    "Septic Pumping",
    "Septic Inspection",
    "Drain Cleaning",
    "Grease Trap Service",
    "System Repair",
    "New Installation",
    "Maintenance",
]


class WorkOrderFactory(factory.Factory):
    """
    Factory for generating WorkOrder test data.

    Usage:
        work_order = WorkOrderFactory()
        work_order = WorkOrderFactory(status="completed")
        work_orders = WorkOrderFactory.create_batch(10, status="scheduled")
    """

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    customer_id = factory.LazyFunction(lambda: fake.random_int(min=1, max=100))
    technician_id = factory.LazyFunction(
        lambda: fake.random_int(min=1, max=20) if fake.boolean() else None
    )
    title = factory.LazyFunction(lambda: fake.random_element(SERVICE_TYPES))
    description = factory.LazyFunction(fake.sentence)
    service_type = factory.LazyFunction(lambda: fake.random_element(SERVICE_TYPES))
    status = factory.LazyFunction(
        lambda: fake.random_element(["pending", "scheduled", "in_progress", "completed"])
    )
    priority = factory.LazyFunction(
        lambda: fake.random_element(["low", "normal", "high", "urgent"])
    )
    scheduled_date = factory.LazyFunction(
        lambda: (datetime.now() + timedelta(days=fake.random_int(min=1, max=14))).strftime("%Y-%m-%d")
    )
    scheduled_time = factory.LazyFunction(
        lambda: fake.random_element(["08:00", "10:00", "13:00", "15:00"])
    )
    completed_at = None
    address = factory.LazyFunction(fake.street_address)
    city = factory.LazyFunction(fake.city)
    state = factory.LazyFunction(lambda: fake.state_abbr())
    zip_code = factory.LazyFunction(fake.zipcode)
    notes = factory.LazyFunction(
        lambda: fake.sentence() if fake.boolean(chance_of_getting_true=40) else None
    )
    estimated_duration = factory.LazyFunction(
        lambda: fake.random_element([30, 60, 90, 120, 180])
    )
    actual_duration = None
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class PendingWorkOrderFactory(WorkOrderFactory):
    """Factory for pending work orders."""

    status = "pending"
    technician_id = None
    scheduled_date = None
    scheduled_time = None


class ScheduledWorkOrderFactory(WorkOrderFactory):
    """Factory for scheduled work orders."""

    status = "scheduled"
    technician_id = factory.LazyFunction(lambda: fake.random_int(min=1, max=20))


class CompletedWorkOrderFactory(WorkOrderFactory):
    """Factory for completed work orders."""

    status = "completed"
    technician_id = factory.LazyFunction(lambda: fake.random_int(min=1, max=20))
    completed_at = factory.LazyFunction(lambda: fake.date_time_this_month().isoformat())
    actual_duration = factory.LazyFunction(lambda: fake.random_int(min=30, max=240))
