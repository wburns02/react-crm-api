from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.applicant_schemas import ApplicantIn
from app.hr.recruiting.applicant_services import (
    create_applicant,
    get_applicant,
    list_applicants,
)


@pytest.mark.asyncio
async def test_create_applicant_persists(db):
    a = await create_applicant(
        db,
        ApplicantIn(
            first_name="Jane",
            last_name="Doe",
            email="jane@example.com",
            source="manual",
        ),
        actor_user_id=None,
    )
    await db.commit()
    row = (await db.execute(select(HrApplicant).where(HrApplicant.id == a.id))).scalar_one()
    assert row.first_name == "Jane"
    assert row.email == "jane@example.com"


@pytest.mark.asyncio
async def test_get_applicant_returns_none_when_missing(db):
    assert await get_applicant(db, uuid4()) is None


@pytest.mark.asyncio
async def test_list_applicants_orders_newest_first(db):
    for e in ["a@x.com", "b@x.com", "c@x.com"]:
        await create_applicant(
            db, ApplicantIn(first_name="X", last_name="Y", email=e), actor_user_id=None
        )
    await db.commit()

    rows = await list_applicants(db, limit=10)
    assert [r.email for r in rows] == ["c@x.com", "b@x.com", "a@x.com"]
