"""
User test factory.

Generates realistic user data for testing authentication and authorization.
"""

import factory
from faker import Faker

fake = Faker()


class UserFactory(factory.Factory):
    """
    Factory for generating User test data.

    Usage:
        user = UserFactory()
        user = UserFactory(email="custom@example.com")
        users = UserFactory.create_batch(10)
    """

    class Meta:
        model = dict

    id = factory.Sequence(lambda n: n + 1)
    email = factory.LazyFunction(lambda: fake.email().lower())
    first_name = factory.LazyFunction(fake.first_name)
    last_name = factory.LazyFunction(fake.last_name)
    hashed_password = "$2b$12$test.hash.for.testing.only"  # noqa: S105
    is_active = True
    is_superuser = False
    created_at = factory.LazyFunction(lambda: fake.date_time_this_year().isoformat())
    updated_at = factory.LazyAttribute(lambda obj: obj.created_at)


class AdminUserFactory(UserFactory):
    """Factory for admin users."""

    is_superuser = True


class InactiveUserFactory(UserFactory):
    """Factory for inactive users."""

    is_active = False
