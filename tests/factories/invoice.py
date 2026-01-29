"""
Invoice test factory.

Generates realistic invoice data for testing.
"""

import factory
from faker import Faker
from datetime import datetime, timedelta

fake = Faker()

SERVICE_DESCRIPTIONS = [
    "Septic Tank Pumping",
    "Septic Inspection",
    "Drain Cleaning",
    "Grease Trap Cleaning",
    "Emergency Service Call",
    "System Repair - Labor",
    "System Repair - Parts",
    "Maintenance Service",
]


class LineItemFactory(factory.Factory):
    """Factory for invoice line items."""

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    description = factory.LazyFunction(lambda: fake.random_element(SERVICE_DESCRIPTIONS))
    quantity = factory.LazyFunction(lambda: fake.random_int(min=1, max=5))
    unit_price = factory.LazyFunction(
        lambda: round(fake.pyfloat(min_value=50.0, max_value=500.0), 2)
    )

    @factory.lazy_attribute
    def total(self):
        return round(self.quantity * self.unit_price, 2)


class InvoiceFactory(factory.Factory):
    """
    Factory for generating Invoice test data.

    Usage:
        invoice = InvoiceFactory()
        invoice = InvoiceFactory(status="paid")
        invoices = InvoiceFactory.create_batch(10)
    """

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    invoice_number = factory.LazyAttribute(lambda obj: f"INV-{obj.id:05d}")
    customer_id = factory.LazyFunction(lambda: fake.random_int(min=1, max=100))
    work_order_id = factory.LazyFunction(
        lambda: fake.random_int(min=1, max=100) if fake.boolean() else None
    )
    status = factory.LazyFunction(
        lambda: fake.random_element(["draft", "sent", "paid", "overdue"])
    )

    @factory.lazy_attribute
    def line_items(self):
        count = fake.random_int(min=1, max=3)
        return [dict(LineItemFactory()) for _ in range(count)]

    @factory.lazy_attribute
    def subtotal(self):
        return round(sum(item["total"] for item in self.line_items), 2)

    tax_rate = 0.0825

    @factory.lazy_attribute
    def tax_amount(self):
        return round(self.subtotal * self.tax_rate, 2)

    @factory.lazy_attribute
    def total(self):
        return round(self.subtotal + self.tax_amount, 2)

    @factory.lazy_attribute
    def amount_paid(self):
        if self.status == "paid":
            return self.total
        return 0.0

    @factory.lazy_attribute
    def balance_due(self):
        return round(self.total - self.amount_paid, 2)

    issue_date = factory.LazyFunction(
        lambda: fake.date_this_month().isoformat()
    )

    @factory.lazy_attribute
    def due_date(self):
        issue = datetime.fromisoformat(self.issue_date)
        return (issue + timedelta(days=30)).strftime("%Y-%m-%d")

    @factory.lazy_attribute
    def paid_at(self):
        if self.status == "paid":
            return fake.date_time_this_month().isoformat()
        return None

    notes = factory.LazyFunction(
        lambda: fake.sentence() if fake.boolean(chance_of_getting_true=30) else None
    )
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class DraftInvoiceFactory(InvoiceFactory):
    """Factory for draft invoices."""

    status = "draft"


class PaidInvoiceFactory(InvoiceFactory):
    """Factory for paid invoices."""

    status = "paid"


class OverdueInvoiceFactory(InvoiceFactory):
    """Factory for overdue invoices."""

    status = "overdue"
    issue_date = factory.LazyFunction(
        lambda: (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
    )
