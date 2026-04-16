from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.shared.models import HrRoleAssignment
from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.models import HrWorkflowTask
from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn


def _simple_template(name: str = "T1") -> TemplateIn:
    return TemplateIn(
        name=name,
        category="onboarding",
        tasks=[
            TemplateTaskIn(position=0, name="Sign agreement", kind="form_sign", assignee_role="hire"),
            TemplateTaskIn(
                position=1,
                name="Verify I-9",
                kind="verify",
                assignee_role="hr",
                depends_on_positions=[0],
            ),
        ],
    )


@pytest.mark.asyncio
async def test_create_template_persists(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    await db.commit()
    assert t.id is not None
    assert t.version == 1
    await db.refresh(t, ["tasks"])
    assert len(t.tasks) == 2


@pytest.mark.asyncio
async def test_spawn_instance_clones_tasks(db, hr_test_user):
    t = await create_template(db, _simple_template(), created_by=hr_test_user.id)
    db.add(HrRoleAssignment(role="hr", user_id=hr_test_user.id, priority=0, active=True))
    await db.commit()

    subject = uuid4()
    inst = await spawn_instance(
        db,
        template_id=t.id,
        subject_type="applicant",
        subject_id=subject,
        started_by=hr_test_user.id,
    )
    await db.commit()

    tasks = (
        await db.execute(
            select(HrWorkflowTask)
            .where(HrWorkflowTask.instance_id == inst.id)
            .order_by(HrWorkflowTask.position)
        )
    ).scalars().all()
    assert len(tasks) == 2

    # Task 0: "hire" role — subject-based, so assignee_user_id stays NULL and
    # assignee_subject_id holds the subject UUID.  Has no deps → ready.
    assert tasks[0].status == "ready"
    assert tasks[0].assignee_user_id is None
    assert tasks[0].assignee_subject_id == subject

    # Task 1: "hr" role — resolved to a real api_users row.  Has a dep → blocked.
    assert tasks[1].status == "blocked"
    assert tasks[1].assignee_user_id == hr_test_user.id
    assert tasks[1].assignee_subject_id is None


@pytest.mark.asyncio
async def test_spawn_missing_template_raises(db, hr_test_user):
    with pytest.raises(ValueError):
        await spawn_instance(
            db,
            template_id=uuid4(),
            subject_type="applicant",
            subject_id=uuid4(),
            started_by=hr_test_user.id,
        )


@pytest.mark.asyncio
async def test_spawn_with_start_date_offsets_due(db, hr_test_user):
    t_in = TemplateIn(
        name="Offset",
        category="onboarding",
        tasks=[
            TemplateTaskIn(
                position=0, name="D1", kind="manual", assignee_role="hire", due_offset_days=5
            ),
        ],
    )
    t = await create_template(db, t_in, created_by=hr_test_user.id)
    await db.commit()

    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    inst = await spawn_instance(
        db,
        template_id=t.id,
        subject_type="applicant",
        subject_id=uuid4(),
        started_by=hr_test_user.id,
        start_date=start,
    )
    await db.commit()

    task = (
        await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.instance_id == inst.id))
    ).scalar_one()
    assert task.due_at.date() == (start + timedelta(days=5)).date()
