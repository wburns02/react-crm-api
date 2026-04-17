"""Public MyOnboarding token flow — verify state + own-task advance."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.hr.employees.models import HrOnboardingToken
from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.models import HrWorkflowTask
from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn


async def _build_instance_and_token(db) -> tuple[str, str]:
    template = await create_template(
        db,
        TemplateIn(
            name="Test Onboarding",
            category="onboarding",
            tasks=[
                TemplateTaskIn(
                    position=1, name="Sign stuff", kind="form_sign",
                    assignee_role="hire", due_offset_days=0,
                ),
                TemplateTaskIn(
                    position=2, name="HR verifies", kind="verify",
                    assignee_role="hr", due_offset_days=0, depends_on_positions=[1],
                ),
            ],
        ),
        created_by=None,
    )
    await db.commit()

    subject = uuid4()
    instance = await spawn_instance(
        db,
        template_id=template.id,
        subject_type="employee",
        subject_id=subject,
        started_by=None,
    )
    await db.commit()

    token = HrOnboardingToken(
        instance_id=instance.id,
        token="tok-" + uuid4().hex,
        expires_at=datetime.utcnow() + timedelta(days=30),
    )
    db.add(token)
    await db.commit()
    return token.token, str(instance.id)


@pytest.mark.asyncio
async def test_get_state_returns_instance_and_progress(client, db):
    token, instance_id = await _build_instance_and_token(db)
    r = await client.get(f"/api/v2/public/onboarding/{token}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["instance_id"] == instance_id
    assert len(data["tasks"]) == 2
    assert data["progress_pct"] == 0


@pytest.mark.asyncio
async def test_advance_own_task(client, db):
    token, instance_id = await _build_instance_and_token(db)
    # Load tasks to find the hire-role task id.
    tasks = (
        await db.execute(
            select(HrWorkflowTask).where(
                HrWorkflowTask.assignee_role == "hire",
            )
        )
    ).scalars().all()
    task_id = str(tasks[0].id)

    r = await client.post(
        f"/api/v2/public/onboarding/{token}/tasks/{task_id}/advance",
        json={"status": "completed"},
    )
    assert r.status_code == 200, r.text

    # Progress should be 50%
    r = await client.get(f"/api/v2/public/onboarding/{token}")
    assert r.json()["progress_pct"] == 50


@pytest.mark.asyncio
async def test_cannot_advance_hr_task(client, db):
    token, instance_id = await _build_instance_and_token(db)
    tasks = (
        await db.execute(
            select(HrWorkflowTask).where(HrWorkflowTask.assignee_role == "hr")
        )
    ).scalars().all()
    task_id = str(tasks[0].id)
    r = await client.post(
        f"/api/v2/public/onboarding/{token}/tasks/{task_id}/advance",
        json={"status": "completed"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_invalid_token_returns_404(client, db):
    r = await client.get("/api/v2/public/onboarding/does-not-exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_expired_token_404(client, db):
    from app.hr.workflow.engine import create_template, spawn_instance
    tpl = await create_template(
        db,
        TemplateIn(
            name="Expired test",
            category="onboarding",
            tasks=[
                TemplateTaskIn(
                    position=1, name="X", kind="manual", assignee_role="hire",
                ),
            ],
        ),
        created_by=None,
    )
    await db.commit()
    inst = await spawn_instance(
        db,
        template_id=tpl.id,
        subject_type="employee",
        subject_id=uuid4(),
        started_by=None,
    )
    await db.commit()
    token = HrOnboardingToken(
        instance_id=inst.id,
        token="expired-" + uuid4().hex,
        expires_at=datetime.utcnow() - timedelta(days=1),
    )
    db.add(token)
    await db.commit()

    r = await client.get(f"/api/v2/public/onboarding/{token.token}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_ssr_page_loads(client, db):
    token, _ = await _build_instance_and_token(db)
    r = await client.get(f"/onboarding/{token}")
    assert r.status_code == 200
    assert "Welcome to Mac Septic" in r.text
    assert f'"{token}"' in r.text or f"'{token}'" in r.text
