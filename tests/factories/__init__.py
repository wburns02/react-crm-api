"""
Test factories for generating realistic test data.

Uses factory_boy for declarative test data generation.
"""

from .user import UserFactory
from .customer import CustomerFactory
from .work_order import WorkOrderFactory
from .technician import TechnicianFactory
from .invoice import InvoiceFactory
from .service_interval import (
    ServiceIntervalFactory,
    PumpingIntervalFactory,
    GreaseTrapIntervalFactory,
    InspectionIntervalFactory,
    CustomerServiceScheduleFactory,
    UpcomingScheduleFactory,
    DueScheduleFactory,
    OverdueScheduleFactory,
    ServiceReminderFactory,
    SMSReminderFactory,
    EmailReminderFactory,
)
from .notification import (
    NotificationFactory,
    WorkOrderNotificationFactory,
    PaymentNotificationFactory,
    SystemNotificationFactory,
    ReadNotificationFactory,
    UnreadNotificationFactory,
)

__all__ = [
    "UserFactory",
    "CustomerFactory",
    "WorkOrderFactory",
    "TechnicianFactory",
    "InvoiceFactory",
    # Service Intervals
    "ServiceIntervalFactory",
    "PumpingIntervalFactory",
    "GreaseTrapIntervalFactory",
    "InspectionIntervalFactory",
    "CustomerServiceScheduleFactory",
    "UpcomingScheduleFactory",
    "DueScheduleFactory",
    "OverdueScheduleFactory",
    "ServiceReminderFactory",
    "SMSReminderFactory",
    "EmailReminderFactory",
    # Notifications
    "NotificationFactory",
    "WorkOrderNotificationFactory",
    "PaymentNotificationFactory",
    "SystemNotificationFactory",
    "ReadNotificationFactory",
    "UnreadNotificationFactory",
]
