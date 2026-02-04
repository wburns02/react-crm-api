"""
Notification test factory.

Generates realistic notification data for testing.
"""

import factory
from faker import Faker
import uuid

fake = Faker()


class NotificationFactory(factory.Factory):
    """
    Factory for generating Notification test data.

    Usage:
        notification = NotificationFactory()
        notification = NotificationFactory(type="payment")
        notifications = NotificationFactory.create_batch(10)
    """

    class Meta:
        model = dict

    id = factory.LazyFunction(lambda: str(uuid.uuid4()))
    user_id = factory.Sequence(lambda n: n + 1)
    type = factory.LazyFunction(
        lambda: fake.random_element(["work_order", "payment", "customer", "system", "schedule", "alert"])
    )
    title = factory.LazyFunction(
        lambda: fake.random_element([
            "New Work Order Assigned",
            "Payment Received",
            "Customer Update",
            "System Maintenance",
            "Schedule Reminder",
            "Service Due Soon",
        ])
    )
    message = factory.LazyFunction(fake.paragraph)
    read = False
    read_at = None
    link = factory.LazyFunction(
        lambda: f"/work-orders/{fake.random_int(min=1, max=1000)}" if fake.boolean(chance_of_getting_true=50) else None
    )
    metadata = factory.LazyFunction(
        lambda: {"source": fake.random_element(["system", "user", "scheduler"])}
    )
    source = factory.LazyFunction(
        lambda: fake.random_element(["system", "user", "scheduler"])
    )
    created_at = factory.LazyFunction(lambda: fake.date_time_this_month().isoformat())


class WorkOrderNotificationFactory(NotificationFactory):
    """Factory for work order notifications."""

    type = "work_order"
    title = "New Work Order Assigned"
    link = factory.LazyFunction(lambda: f"/work-orders/{fake.random_int(min=1, max=1000)}")


class PaymentNotificationFactory(NotificationFactory):
    """Factory for payment notifications."""

    type = "payment"
    title = "Payment Received"
    link = factory.LazyFunction(lambda: f"/payments/{fake.random_int(min=1, max=1000)}")


class SystemNotificationFactory(NotificationFactory):
    """Factory for system notifications."""

    type = "system"
    title = "System Notification"
    source = "system"


class ReadNotificationFactory(NotificationFactory):
    """Factory for read notifications."""

    read = True
    read_at = factory.LazyFunction(lambda: fake.date_time_this_month().isoformat())


class UnreadNotificationFactory(NotificationFactory):
    """Factory for unread notifications."""

    read = False
    read_at = None
