from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.recruiting.applicant_models import (
    HrApplicationEvent,
    HrRecruitingMessageTemplate,
)


async def _seed(db, *, sms_consent: bool):
    from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicationIn
    from app.hr.recruiting.applicant_services import create_applicant
    from app.hr.recruiting.application_services import create_application
    from app.hr.recruiting.models import HrRequisition

    req = HrRequisition(
        slug=f"q-{uuid4().hex[:6]}",
        title="Tech",
        status="open",
        employment_type="full_time",
    )
    db.add(req)
    db.add(
        HrRecruitingMessageTemplate(
            stage="screen",
            channel="sms",
            body="Hi {first_name}, about {requisition_title}.",
            active=True,
        )
    )
    await db.commit()

    a = await create_applicant(
        db,
        ApplicantIn(
            first_name="Jane", last_name="Doe", email="j@x.com", phone="+15555550100"
        ),
        actor_user_id=None,
    )
    await db.commit()
    if sms_consent:
        a.sms_consent_given = True
        await db.commit()

    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(a.id), requisition_id=str(req.id)),
        actor_user_id=None,
    )
    await db.commit()
    return a, app


@pytest.mark.asyncio
async def test_sms_fires_on_stage_change_when_consented(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=True)
    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert len(calls) == 1
    assert calls[0]["to"] == "+15555550100"
    assert "Jane" in calls[0]["body"]
    events = (
        await db.execute(
            select(HrApplicationEvent).where(
                HrApplicationEvent.application_id == app.id,
                HrApplicationEvent.event_type == "message_sent",
            )
        )
    ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_sms_skipped_when_no_consent(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=False)
    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert calls == []


@pytest.mark.asyncio
async def test_sms_skipped_when_no_phone(db, monkeypatch):
    from app.hr.recruiting import notifications

    calls = []

    async def fake_send(to, body):
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=True)
    a.phone = None
    await db.commit()

    from app.hr.recruiting.application_services import transition_stage

    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    assert calls == []


@pytest.mark.asyncio
async def test_sms_error_recorded_as_event(db, monkeypatch):
    from app.hr.recruiting import notifications

    async def fake_send(to, body):
        raise RuntimeError("twilio down")

    monkeypatch.setattr(notifications, "_send_sms", fake_send)

    a, app = await _seed(db, sms_consent=True)
    from app.hr.recruiting.application_services import transition_stage

    # Should NOT raise; error recorded as event
    await transition_stage(db, application_id=app.id, new_stage="screen", actor_user_id=None)
    await db.commit()

    events = (
        await db.execute(
            select(HrApplicationEvent).where(
                HrApplicationEvent.application_id == app.id,
                HrApplicationEvent.event_type == "message_sent",
            )
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].payload["status"] == "error"
