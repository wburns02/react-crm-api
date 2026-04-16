from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.hr.workflow.engine import create_template, spawn_instance
from app.hr.workflow.schemas import (
    InstanceOut,
    SpawnRequest,
    TemplateIn,
    TemplateOut,
)


workflow_router = APIRouter(prefix="/workflows", tags=["hr-workflows"])


@workflow_router.post(
    "/templates",
    response_model=TemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_template_endpoint(
    payload: TemplateIn,
    db: DbSession,
    user: CurrentUser,
) -> TemplateOut:
    try:
        template = await create_template(db, payload, created_by=user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return TemplateOut.model_validate(template)


@workflow_router.post(
    "/instances",
    response_model=InstanceOut,
    status_code=status.HTTP_201_CREATED,
)
async def spawn_instance_endpoint(
    payload: SpawnRequest,
    db: DbSession,
    user: CurrentUser,
) -> InstanceOut:
    try:
        instance = await spawn_instance(
            db,
            template_id=UUID(payload.template_id),
            subject_type=payload.subject_type,
            subject_id=UUID(payload.subject_id),
            started_by=user.id,
            start_date=payload.start_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return InstanceOut.model_validate(instance)
