from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.hr.recruiting.applicant_models import HrApplication, HrApplicationEvent
from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicationIn
from app.hr.recruiting.applicant_services import create_applicant
from app.hr.recruiting.application_services import (
    ApplicationStateError,
    create_application,
    list_by_requisition,
    stage_counts_for_requisition,
    transition_stage,
)
from app.hr.recruiting.models import HrRequisition


@pytest_asyncio.fixture
async def requisition(db):
    r = HrRequisition(slug="q-tech", title="Tech", status="open", employment_type="full_time")
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest_asyncio.fixture
async def applicant(db):
    a = await create_applicant(
        db,
        ApplicantIn(first_name="A", last_name="B", email="ab@example.com"),
        actor_user_id=None,
    )
    await db.commit()
    return a


@pytest.mark.asyncio
async def test_create_application_starts_at_applied(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    assert app.stage == "applied"

    events = (
        await db.execute(
            select(HrApplicationEvent).where(HrApplicationEvent.application_id == app.id)
        )
    ).scalars().all()
    assert any(e.event_type == "created" for e in events)


@pytest.mark.asyncio
async def test_transition_advances_through_pipeline(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()

    for next_stage in ["screen", "ride_along", "offer", "hired"]:
        app = await transition_stage(
            db, application_id=app.id, new_stage=next_stage, actor_user_id=None
        )
        await db.commit()
        assert app.stage == next_stage


@pytest.mark.asyncio
async def test_cannot_transition_from_terminal(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    await transition_stage(
        db,
        application_id=app.id,
        new_stage="rejected",
        actor_user_id=None,
        reason="not a fit",
    )
    await db.commit()
    with pytest.raises(ApplicationStateError):
        await transition_stage(
            db, application_id=app.id, new_stage="screen", actor_user_id=None
        )


@pytest.mark.asyncio
async def test_rejection_requires_reason(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises(ApplicationStateError, match="reason"):
        await transition_stage(
            db, application_id=app.id, new_stage="rejected", actor_user_id=None
        )


@pytest.mark.asyncio
async def test_hired_emits_trigger(db, applicant, requisition, monkeypatch):
    from app.hr.workflow.triggers import trigger_bus

    seen = []

    @trigger_bus.on("hr.applicant.hired")
    async def _h(payload):
        seen.append(payload)

    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    for s in ["screen", "ride_along", "offer", "hired"]:
        await transition_stage(db, application_id=app.id, new_stage=s, actor_user_id=None)
        await db.commit()

    assert seen, "hr.applicant.hired did not fire"
    payload = seen[0]
    assert payload["application_id"] == str(app.id)
    assert payload["requisition_id"] == str(requisition.id)


@pytest.mark.asyncio
async def test_duplicate_application_rejected(db, applicant, requisition):
    await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    with pytest.raises(IntegrityError):
        await create_application(
            db,
            ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
            actor_user_id=None,
        )
        await db.commit()


@pytest.mark.asyncio
async def test_list_by_requisition_filters_by_stage(db, applicant, requisition):
    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()

    rows_applied = await list_by_requisition(db, requisition_id=requisition.id, stage="applied")
    rows_hired = await list_by_requisition(db, requisition_id=requisition.id, stage="hired")
    assert [r.id for r in rows_applied] == [app.id]
    assert rows_hired == []


@pytest.mark.asyncio
async def test_stage_counts(db, applicant, requisition):
    await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(requisition.id)),
        actor_user_id=None,
    )
    await db.commit()
    counts = await stage_counts_for_requisition(db, requisition_id=requisition.id)
    assert counts == {"applied": 1}
