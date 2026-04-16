from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.applicant_schemas import (
    ApplicantOut,
    ApplicationIn,
    ApplicationOut,
    ApplicationWithApplicantOut,
    StageTransitionIn,
)
from app.hr.recruiting.application_services import (
    ApplicationStateError,
    create_application,
    get_application,
    list_by_requisition,
    stage_counts_for_requisition,
    transition_stage,
)


applications_router = APIRouter(prefix="/applications", tags=["hr-applications"])


@applications_router.post(
    "", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED
)
async def create(
    payload: ApplicationIn, db: DbSession, user: CurrentUser
) -> ApplicationOut:
    try:
        row = await create_application(db, payload, actor_user_id=user.id)
    except ApplicationStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ApplicationOut.model_validate(row)


@applications_router.get("/counts", response_model=dict[str, int])
async def counts(
    db: DbSession, user: CurrentUser, requisition_id: UUID = Query(...)
) -> dict[str, int]:
    return await stage_counts_for_requisition(db, requisition_id=requisition_id)


@applications_router.get("", response_model=list[ApplicationWithApplicantOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    requisition_id: UUID = Query(...),
    stage: str | None = Query(None),
) -> list[ApplicationWithApplicantOut]:
    rows = await list_by_requisition(db, requisition_id=requisition_id, stage=stage)
    if not rows:
        return []
    applicant_ids = [r.applicant_id for r in rows]
    applicants = {
        a.id: a
        for a in (
            await db.execute(select(HrApplicant).where(HrApplicant.id.in_(applicant_ids)))
        ).scalars().all()
    }
    return [
        ApplicationWithApplicantOut(
            **ApplicationOut.model_validate(r).model_dump(),
            applicant=ApplicantOut.model_validate(applicants[r.applicant_id]),
        )
        for r in rows
    ]


@applications_router.get("/{application_id}", response_model=ApplicationWithApplicantOut)
async def detail(
    application_id: UUID, db: DbSession, user: CurrentUser
) -> ApplicationWithApplicantOut:
    row = await get_application(db, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="application not found")
    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.id == row.applicant_id))
    ).scalar_one()
    return ApplicationWithApplicantOut(
        **ApplicationOut.model_validate(row).model_dump(),
        applicant=ApplicantOut.model_validate(applicant),
    )


@applications_router.patch(
    "/{application_id}/stage", response_model=ApplicationOut
)
async def patch_stage(
    application_id: UUID,
    payload: StageTransitionIn,
    db: DbSession,
    user: CurrentUser,
) -> ApplicationOut:
    try:
        row = await transition_stage(
            db,
            application_id=application_id,
            new_stage=payload.stage,
            actor_user_id=user.id,
            reason=payload.rejection_reason,
            note=payload.note,
        )
    except ApplicationStateError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return ApplicationOut.model_validate(row)
