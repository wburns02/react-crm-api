import pytest
from uuid import uuid4
from sqlalchemy import select

from app.hr.shared.audit import write_audit
from app.hr.shared.models import HrAuditLog


@pytest.mark.asyncio
async def test_write_audit_inserts_row(db, hr_test_user):
    entity_id = uuid4()
    await write_audit(
        db=db,
        entity_type="applicant",
        entity_id=entity_id,
        event="created",
        diff={"stage": [None, "applied"]},
        actor_user_id=hr_test_user.id,
        actor_ip="192.0.2.1",
        actor_user_agent="pytest",
        actor_location="Houston, TX, US",
    )
    await db.commit()

    rows = (
        await db.execute(select(HrAuditLog).where(HrAuditLog.entity_id == entity_id))
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.event == "created"
    assert row.diff == {"stage": [None, "applied"]}
    assert row.actor_user_id == hr_test_user.id
    assert row.actor_ip == "192.0.2.1"
    assert row.actor_location == "Houston, TX, US"


@pytest.mark.asyncio
async def test_write_audit_accepts_null_actor(db):
    entity_id = uuid4()
    await write_audit(
        db=db,
        entity_type="applicant",
        entity_id=entity_id,
        event="system_event",
        diff={},
    )
    await db.commit()
    rows = (
        await db.execute(select(HrAuditLog).where(HrAuditLog.entity_id == entity_id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_user_id is None
