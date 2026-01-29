"""
Technician test factory.

Generates realistic technician data for testing.
"""

import factory
from faker import Faker

fake = Faker()

CERTIFICATIONS = [
    "NAWT Certified Installer",
    "NAWT Certified Inspector",
    "NAWT Certified Operator",
    "State Licensed Pumper",
    "CDL Class A",
    "CDL Class B",
    "OSHA 10",
    "OSHA 30",
]


class TechnicianFactory(factory.Factory):
    """
    Factory for generating Technician test data.

    Usage:
        tech = TechnicianFactory()
        tech = TechnicianFactory(is_active=False)
        techs = TechnicianFactory.create_batch(5)
    """

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    first_name = factory.LazyFunction(fake.first_name)
    last_name = factory.LazyFunction(fake.last_name)
    email = factory.LazyFunction(lambda: fake.email().lower())
    phone = factory.LazyFunction(lambda: fake.phone_number()[:20])
    hire_date = factory.LazyFunction(lambda: fake.date_this_decade().isoformat())
    is_active = True
    hourly_rate = factory.LazyFunction(
        lambda: round(fake.pyfloat(min_value=15.0, max_value=45.0), 2)
    )
    certifications = factory.LazyFunction(
        lambda: fake.random_elements(CERTIFICATIONS, unique=True, length=fake.random_int(min=0, max=4))
    )
    notes = factory.LazyFunction(
        lambda: fake.sentence() if fake.boolean(chance_of_getting_true=30) else None
    )
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class InactiveTechnicianFactory(TechnicianFactory):
    """Factory for inactive technicians."""

    is_active = False


class SeniorTechnicianFactory(TechnicianFactory):
    """Factory for senior technicians with higher rates and more certs."""

    hourly_rate = factory.LazyFunction(
        lambda: round(fake.pyfloat(min_value=35.0, max_value=55.0), 2)
    )
    certifications = factory.LazyFunction(
        lambda: fake.random_elements(CERTIFICATIONS, unique=True, length=fake.random_int(min=3, max=6))
    )
