"""HR test fixtures.

Composes on top of the top-level tests/conftest.py fixtures (test_db, client,
authenticated_client, admin_client). HR-specific helpers only.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest_asyncio.fixture
async def db(test_db: AsyncSession) -> AsyncSession:
    """Alias so HR test code can depend on `db` without renaming."""
    return test_db


@pytest_asyncio.fixture
async def hr_test_user(db: AsyncSession) -> User:
    """A second user distinct from the default `test_user` fixture.

    Useful when a test needs to assert behaviour around actor identity while
    `test_user`/`authenticated_client` are being used elsewhere in the same test.
    """
    user = User(
        email="hr-test@example.com",
        first_name="HR",
        last_name="Test",
        hashed_password="x",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
