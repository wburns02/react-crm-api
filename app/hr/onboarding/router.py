"""Admin-side onboarding/offboarding router.

Thin layer over the Plan 1 workflow engine: list instances filtered by
subject + category, fetch detail (instance + tasks + events), advance a
task, and spawn an offboarding instance on demand.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.employees.models import HrOnboardingToken
from app.hr.workflow.engine import advance_task, spawn_instance
from app.hr.workflow.models import (
    HrWorkflowInstance,
    HrWorkflowTask,
    HrWorkflowTemplate,
)
from app.hr.workflow.schemas import (
    AdvanceTaskRequest,
    InstanceOut,
    TaskOut,
)


onboarding_admin_router = APIRouter(prefix="/onboarding", tags=["hr-onboarding-admin"])


class InstanceDetailOut(BaseModel):
    instance: InstanceOut
    tasks: list[TaskOut]
    onboarding_token: str | None = None


class SpawnOffboardingIn(BaseModel):
    subject_id: str  # technician id
    started_by: int | None = None


@onboarding_admin_router.get(
    "/instances", response_model=list[InstanceOut]
)
async def list_instances(
    db: DbSession,
    user: CurrentUser,
    subject_id: UUID | None = Query(None),
    category: str | None = Query(None),
) -> list[InstanceOut]:
    stmt = select(HrWorkflowInstance).order_by(
        HrWorkflowInstance.started_at.desc()
    )
    if subject_id is not None:
        stmt = stmt.where(HrWorkflowInstance.subject_id == subject_id)
    if category is not None:
        # Join through template to filter by category.
        stmt = stmt.join(
            HrWorkflowTemplate, HrWorkflowInstance.template_id == HrWorkflowTemplate.id
        ).where(HrWorkflowTemplate.category == category)
    rows = (await db.execute(stmt)).scalars().all()
    return [InstanceOut.model_validate(r) for r in rows]


@onboarding_admin_router.get(
    "/instances/{instance_id}", response_model=InstanceDetailOut
)
async def get_instance(
    instance_id: UUID, db: DbSession, user: CurrentUser
) -> InstanceDetailOut:
    instance = (
        await db.execute(
            select(HrWorkflowInstance).where(HrWorkflowInstance.id == instance_id)
        )
    ).scalar_one_or_none()
    if instance is None:
        raise HTTPException(status_code=404, detail="instance not found")
    tasks = (
        await db.execute(
            select(HrWorkflowTask)
            .where(HrWorkflowTask.instance_id == instance_id)
            .order_by(HrWorkflowTask.position)
        )
    ).scalars().all()
    token_row = (
        await db.execute(
            select(HrOnboardingToken).where(
                HrOnboardingToken.instance_id == instance_id
            )
        )
    ).scalar_one_or_none()
    return InstanceDetailOut(
        instance=InstanceOut.model_validate(instance),
        tasks=[TaskOut.model_validate(t) for t in tasks],
        onboarding_token=token_row.token if token_row else None,
    )


@onboarding_admin_router.patch(
    "/instances/{instance_id}/tasks/{task_id}", response_model=TaskOut
)
async def advance_task_endpoint(
    instance_id: UUID,
    task_id: UUID,
    payload: AdvanceTaskRequest,
    db: DbSession,
    user: CurrentUser,
) -> TaskOut:
    try:
        task = await advance_task(
            db,
            task_id=task_id,
            new_status=payload.status,
            actor_user_id=user.id,
            reason=payload.reason,
            result=payload.result or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if task.instance_id != instance_id:
        raise HTTPException(status_code=400, detail="task does not belong to instance")
    await db.commit()
    return TaskOut.model_validate(task)


@onboarding_admin_router.post(
    "/spawn-offboarding", response_model=InstanceOut, status_code=status.HTTP_201_CREATED
)
async def spawn_offboarding(
    payload: SpawnOffboardingIn, db: DbSession, user: CurrentUser
) -> InstanceOut:
    template = (
        await db.execute(
            select(HrWorkflowTemplate).where(
                HrWorkflowTemplate.name == "Tech Separation",
                HrWorkflowTemplate.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=400, detail="offboarding template not seeded")
    try:
        instance = await spawn_instance(
            db,
            template_id=template.id,
            subject_type="employee",
            subject_id=UUID(payload.subject_id),
            started_by=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return InstanceOut.model_validate(instance)
