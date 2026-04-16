import secrets
from uuid import uuid4

import pytest

from app.hr.shared.models import HrRoleAssignment
from app.hr.shared.role_resolver import resolve_role
from app.models.user import User


@pytest.mark.asyncio
async def test_resolve_role_returns_user_id(db, hr_test_user):
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()

    resolved = await resolve_role(db, role="hr")
    assert resolved == hr_test_user.id


@pytest.mark.asyncio
async def test_resolve_role_prefers_higher_priority(db, hr_test_user):
    other = User(
        email=f"o{secrets.token_hex(4)}@ex.com",
        first_name="x",
        last_name="y",
        hashed_password="x",
        is_active=True,
    )
    db.add(other)
    await db.commit()
    await db.refresh(other)

    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    db.add(HrRoleAssignment(role="hr", user_id=other.id, priority=10, active=True))
    await db.commit()

    resolved = await resolve_role(db, role="hr")
    assert resolved == other.id


@pytest.mark.asyncio
async def test_resolve_role_ignores_inactive(db, hr_test_user):
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=False))
    await db.commit()
    resolved = await resolve_role(db, role="hr")
    assert resolved is None


@pytest.mark.asyncio
async def test_resolve_role_hire_returns_subject_id(db):
    subject_id = uuid4()
    resolved = await resolve_role(db, role="hire", subject_id=subject_id)
    assert resolved == subject_id


@pytest.mark.asyncio
async def test_resolve_role_employee_returns_subject_id(db):
    subject_id = uuid4()
    resolved = await resolve_role(db, role="employee", subject_id=subject_id)
    assert resolved == subject_id
