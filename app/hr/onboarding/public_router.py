"""Public MyOnboarding API.

Unauthenticated endpoints gated by a 32-byte URL-safe token.  A new hire
gets a link to ``/onboarding/<token>`` via SMS/email after they are marked
hired in the pipeline (Plan 3).  These endpoints let them inspect their
workflow state and advance tasks that belong to the `hire` assignee_role.
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession
from app.hr.employees.models import HrOnboardingToken
from app.hr.workflow.engine import advance_task
from app.hr.workflow.models import HrWorkflowInstance, HrWorkflowTask
from app.hr.workflow.schemas import TaskOut


onboarding_public_router = APIRouter(prefix="/onboarding", tags=["hr-onboarding-public"])


class TokenTaskOut(BaseModel):
    id: str
    position: int
    stage: str | None
    name: str
    kind: str
    assignee_role: str
    status: str
    due_at: datetime | None
    config: dict


class OnboardingStateOut(BaseModel):
    instance_id: str
    subject_type: str
    subject_id: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    tasks: list[TokenTaskOut]
    progress_pct: int


class AdvanceIn(BaseModel):
    status: str  # "completed" typically; "in_progress" also allowed
    result: dict | None = None


async def _resolve_token(db, token: str) -> HrOnboardingToken:
    row = (
        await db.execute(
            select(HrOnboardingToken).where(HrOnboardingToken.token == token)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="token not found")
    expires = row.expires_at
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    if expires < datetime.utcnow():
        raise HTTPException(status_code=404, detail="onboarding link expired")
    return row


@onboarding_public_router.get("/{token}", response_model=OnboardingStateOut)
async def get_state(
    token: str, db: DbSession, request: Request
) -> OnboardingStateOut:
    token_row = await _resolve_token(db, token)

    # Mark as viewed on first GET (idempotent).
    if token_row.viewed_at is None:
        token_row.viewed_at = datetime.utcnow()
        await db.flush()
        await db.commit()

    instance = (
        await db.execute(
            select(HrWorkflowInstance).where(
                HrWorkflowInstance.id == token_row.instance_id
            )
        )
    ).scalar_one()
    tasks = (
        await db.execute(
            select(HrWorkflowTask)
            .where(HrWorkflowTask.instance_id == instance.id)
            .order_by(HrWorkflowTask.position)
        )
    ).scalars().all()

    total = len(tasks) or 1
    done = sum(1 for t in tasks if t.status in {"completed", "skipped"})
    pct = int((done / total) * 100)

    return OnboardingStateOut(
        instance_id=str(instance.id),
        subject_type=instance.subject_type,
        subject_id=str(instance.subject_id),
        started_at=instance.started_at,
        completed_at=instance.completed_at,
        status=instance.status,
        progress_pct=pct,
        tasks=[
            TokenTaskOut(
                id=str(t.id),
                position=t.position,
                stage=t.stage,
                name=t.name,
                kind=t.kind,
                assignee_role=t.assignee_role,
                status=t.status,
                due_at=t.due_at,
                config=t.config or {},
            )
            for t in tasks
        ],
    )


@onboarding_public_router.post(
    "/{token}/tasks/{task_id}/advance", status_code=status.HTTP_200_OK
)
async def advance_own_task(
    token: str,
    task_id: UUID,
    payload: AdvanceIn,
    db: DbSession,
) -> dict:
    token_row = await _resolve_token(db, token)

    task = (
        await db.execute(select(HrWorkflowTask).where(HrWorkflowTask.id == task_id))
    ).scalar_one_or_none()
    if task is None or task.instance_id != token_row.instance_id:
        raise HTTPException(status_code=404, detail="task not found")

    # Only let the hire advance their own tasks (role=hire).
    if task.assignee_role != "hire":
        raise HTTPException(
            status_code=403, detail="this task is not assigned to you"
        )
    if payload.status not in {"completed", "in_progress"}:
        raise HTTPException(status_code=400, detail="invalid status")

    try:
        await advance_task(
            db,
            task_id=task_id,
            new_status=payload.status,
            actor_user_id=None,
            result=payload.result,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return {"ok": True}
