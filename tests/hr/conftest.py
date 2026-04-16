"""HR test fixtures.

Composes on top of the top-level tests/conftest.py fixtures (test_db, client,
authenticated_client, admin_client). HR-specific helpers only.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

# Ensure hr_router is mounted on the shared FastAPI app for every HR test.
# main.py gates registration on HR_MODULE_ENABLED which is not set at conftest
# import time, so tests would otherwise hit 404 on /api/v2/hr/* routes.
def _mount_hr_router_once() -> None:
    from app.hr.esign.router import esign_public_router
    from app.hr.router import hr_router
    from app.main import app as fastapi_app

    hr_mounted = any(
        getattr(r, "path", "").startswith("/api/v2/hr")
        for r in fastapi_app.routes
    )
    if not hr_mounted:
        fastapi_app.include_router(hr_router, prefix="/api/v2")

    public_mounted = any(
        getattr(r, "path", "").startswith("/api/v2/public/sign")
        for r in fastapi_app.routes
    )
    if not public_mounted:
        fastapi_app.include_router(esign_public_router, prefix="/api/v2/public")


_mount_hr_router_once()


@pytest_asyncio.fixture
async def authed_client(authenticated_client):
    """Plan-doc alias for the existing authenticated bearer-token client."""
    return authenticated_client


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
