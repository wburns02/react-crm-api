"""Admin onboarding/offboarding router."""
from uuid import uuid4

import pytest
import pytest_asyncio

from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn


@pytest_asyncio.fixture
async def onboarding_instance(db):
    t = await create_template(
        db,
        TemplateIn(
            name="Onb",
            category="onboarding",
            tasks=[
                TemplateTaskIn(position=1, name="Do it", kind="manual", assignee_role="hire"),
            ],
        ),
        created_by=None,
    )
    inst = await spawn_instance(
        db,
        template_id=t.id,
        subject_type="employee",
        subject_id=uuid4(),
        started_by=None,
    )
    await db.commit()
    return inst


@pytest.mark.asyncio
async def test_list_instances(authed_client, db, onboarding_instance):
    r = await authed_client.get(
        f"/api/v2/hr/onboarding/instances?subject_id={onboarding_instance.subject_id}"
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_get_instance_detail_with_tasks(authed_client, onboarding_instance):
    r = await authed_client.get(
        f"/api/v2/hr/onboarding/instances/{onboarding_instance.id}"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["instance"]["id"] == str(onboarding_instance.id)
    assert len(data["tasks"]) == 1


@pytest.mark.asyncio
async def test_advance_task_via_admin(authed_client, db, onboarding_instance):
    from app.hr.workflow.models import HrWorkflowTask
    from sqlalchemy import select

    task = (
        await db.execute(
            select(HrWorkflowTask).where(
                HrWorkflowTask.instance_id == onboarding_instance.id
            )
        )
    ).scalar_one()

    r = await authed_client.patch(
        f"/api/v2/hr/onboarding/instances/{onboarding_instance.id}/tasks/{task.id}",
        json={"status": "completed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_unknown_instance_404(authed_client):
    r = await authed_client.get(f"/api/v2/hr/onboarding/instances/{uuid4()}")
    assert r.status_code == 404
