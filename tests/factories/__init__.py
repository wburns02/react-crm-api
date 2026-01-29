"""
Test factories for generating realistic test data.

Uses factory_boy for declarative test data generation.
"""

from .user import UserFactory
from .customer import CustomerFactory
from .work_order import WorkOrderFactory
from .technician import TechnicianFactory
from .invoice import InvoiceFactory

__all__ = [
    "UserFactory",
    "CustomerFactory",
    "WorkOrderFactory",
    "TechnicianFactory",
    "InvoiceFactory",
]
