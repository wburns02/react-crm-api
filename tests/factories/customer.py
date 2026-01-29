"""
Customer test factory.

Generates realistic customer data for testing.
"""

import factory
from faker import Faker

fake = Faker()


class CustomerFactory(factory.Factory):
    """
    Factory for generating Customer test data.

    Usage:
        customer = CustomerFactory()
        customer = CustomerFactory(customer_type="commercial")
        customers = CustomerFactory.create_batch(20)
    """

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    first_name = factory.LazyFunction(fake.first_name)
    last_name = factory.LazyFunction(fake.last_name)
    email = factory.LazyFunction(lambda: fake.email().lower())
    phone = factory.LazyFunction(lambda: fake.phone_number()[:20])
    address = factory.LazyFunction(fake.street_address)
    city = factory.LazyFunction(fake.city)
    state = factory.LazyFunction(lambda: fake.state_abbr())
    zip_code = factory.LazyFunction(fake.zipcode)
    customer_type = factory.LazyFunction(
        lambda: fake.random_element(["residential", "commercial"])
    )
    is_active = True
    notes = factory.LazyFunction(
        lambda: fake.sentence() if fake.boolean(chance_of_getting_true=30) else None
    )
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class ResidentialCustomerFactory(CustomerFactory):
    """Factory for residential customers."""

    customer_type = "residential"


class CommercialCustomerFactory(CustomerFactory):
    """Factory for commercial customers."""

    customer_type = "commercial"


class InactiveCustomerFactory(CustomerFactory):
    """Factory for inactive customers."""

    is_active = False
