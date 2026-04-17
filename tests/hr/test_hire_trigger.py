"""Hire trigger: promote applicant → spawn onboarding instance."""
import uuid

import pytest
from sqlalchemy import select

from app.hr.employees.models import HrOnboardingToken
from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
)
from app.hr.recruiting.models import HrRequisition
from app.hr.workflow.models import HrWorkflowInstance, HrWorkflowTask


@pytest.mark.asyncio
async def test_hired_promotes_applicant_to_technician_and_spawns_onboarding(db):
    """Full flow: applicant + application + seeded onboarding template
    → transition to hired → verify technician row + workflow instance +
    onboarding token created."""
    from app.hr.onboarding.seed import ONBOARDING_TEMPLATE
    from app.hr.recruiting.applicant_schemas import ApplicationIn
    from app.hr.recruiting.application_services import (
        create_application,
        transition_stage,
    )
    from app.hr.workflow.engine import create_template
    from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn
    from app.models.technician import Technician

    # Seed the onboarding template (matches migration 104).
    template_tasks = [
        TemplateTaskIn(
            position=t["position"],
            stage=t.get("stage"),
            name=t["name"],
            kind=t["kind"],
            assignee_role=t["assignee_role"],
            due_offset_days=t.get("due_offset_days", 0),
            required=t.get("required", True),
            config=t.get("config", {}),
            depends_on_positions=t.get("depends_on", []),
        )
        for t in ONBOARDING_TEMPLATE["tasks"]
    ]
    await create_template(
        db,
        TemplateIn(
            name=ONBOARDING_TEMPLATE["name"],
            category=ONBOARDING_TEMPLATE["category"],
            tasks=template_tasks,
        ),
        created_by=None,
    )
    await db.commit()

    # Build applicant + requisition + application manually.
    req = HrRequisition(
        slug="hire-trigger-req",
        title="Field Tech",
        status="open",
        employment_type="full_time",
    )
    applicant = HrApplicant(
        first_name="Trigger",
        last_name="Test",
        email="trigger-test@example.com",
    )
    db.add(req)
    db.add(applicant)
    await db.commit()
    await db.refresh(req)
    await db.refresh(applicant)

    app = await create_application(
        db,
        ApplicationIn(
            applicant_id=str(applicant.id),
            requisition_id=str(req.id),
        ),
        actor_user_id=None,
    )
    await db.commit()

    # Advance through the pipeline to hired.
    for stage in ["screen", "ride_along", "offer", "hired"]:
        await transition_stage(
            db, application_id=app.id, new_stage=stage, actor_user_id=None
        )
        await db.commit()

    # The trigger handler opens its own session and commits; re-read from ours.
    await db.commit()

    # Technician row created.
    tech = (
        await db.execute(
            select(Technician).where(Technician.email == "trigger-test@example.com")
        )
    ).scalar_one_or_none()
    assert tech is not None
    assert tech.is_active is True

    # Onboarding instance spawned.
    instances = (
        await db.execute(
            select(HrWorkflowInstance).where(HrWorkflowInstance.subject_id == tech.id)
        )
    ).scalars().all()
    assert len(instances) == 1
    instance = instances[0]
    assert instance.subject_type == "employee"

    # 23 tasks cloned.
    tasks = (
        await db.execute(
            select(HrWorkflowTask).where(HrWorkflowTask.instance_id == instance.id)
        )
    ).scalars().all()
    assert len(tasks) == 23

    # Token created.
    token = (
        await db.execute(
            select(HrOnboardingToken).where(
                HrOnboardingToken.instance_id == instance.id
            )
        )
    ).scalar_one()
    assert len(token.token) >= 32


@pytest.mark.asyncio
async def test_hired_reuses_existing_technician_when_email_matches(db):
    from app.hr.onboarding.seed import ONBOARDING_TEMPLATE
    from app.hr.recruiting.applicant_schemas import ApplicationIn
    from app.hr.recruiting.application_services import (
        create_application,
        transition_stage,
    )
    from app.hr.workflow.engine import create_template
    from app.hr.workflow.schemas import TemplateIn, TemplateTaskIn
    from app.models.technician import Technician

    # Pre-existing technician with same email.
    existing = Technician(
        first_name="Prior", last_name="Tech", email="prior@example.com"
    )
    db.add(existing)
    await db.commit()
    await db.refresh(existing)

    # Seed template.
    template_tasks = [
        TemplateTaskIn(
            position=t["position"],
            stage=t.get("stage"),
            name=t["name"],
            kind=t["kind"],
            assignee_role=t["assignee_role"],
            due_offset_days=t.get("due_offset_days", 0),
            required=t.get("required", True),
            config=t.get("config", {}),
            depends_on_positions=t.get("depends_on", []),
        )
        for t in ONBOARDING_TEMPLATE["tasks"]
    ]
    await create_template(
        db,
        TemplateIn(
            name=ONBOARDING_TEMPLATE["name"],
            category=ONBOARDING_TEMPLATE["category"],
            tasks=template_tasks,
        ),
        created_by=None,
    )

    req = HrRequisition(
        slug="reuse-tech",
        title="Field Tech",
        status="open",
        employment_type="full_time",
    )
    applicant = HrApplicant(
        first_name="Prior",
        last_name="Tech",
        email="prior@example.com",
    )
    db.add(req)
    db.add(applicant)
    await db.commit()
    await db.refresh(req)
    await db.refresh(applicant)

    app = await create_application(
        db,
        ApplicationIn(applicant_id=str(applicant.id), requisition_id=str(req.id)),
        actor_user_id=None,
    )
    await db.commit()

    for stage in ["screen", "ride_along", "offer", "hired"]:
        await transition_stage(
            db, application_id=app.id, new_stage=stage, actor_user_id=None
        )
        await db.commit()

    techs = (
        await db.execute(
            select(Technician).where(Technician.email == "prior@example.com")
        )
    ).scalars().all()
    assert len(techs) == 1  # reused, no duplicate
