from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.applicant_schemas import ApplicantIn, ApplicantOut
from app.hr.recruiting.applicant_services import (
    create_applicant,
    get_applicant,
    list_applicants,
    search_applicants,
)


applicants_router = APIRouter(prefix="/applicants", tags=["hr-applicants"])


@applicants_router.post(
    "", response_model=ApplicantOut, status_code=status.HTTP_201_CREATED
)
async def create(
    payload: ApplicantIn, db: DbSession, user: CurrentUser
) -> ApplicantOut:
    row = await create_applicant(db, payload, actor_user_id=user.id)
    await db.commit()
    return ApplicantOut.model_validate(row)


@applicants_router.get("", response_model=list[ApplicantOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, min_length=1, max_length=128),
    requisition_id: UUID | None = Query(None),
    stage: str | None = Query(None),
    source: str | None = Query(None),
    since_days: int | None = Query(None, ge=1, le=365),
) -> list[ApplicantOut]:
    if q or requisition_id or stage or source or since_days:
        rows = await search_applicants(
            db,
            q=q,
            requisition_id=requisition_id,
            stage=stage,
            source=source,
            since_days=since_days,
            limit=limit,
            offset=offset,
        )
    else:
        rows = await list_applicants(db, limit=limit, offset=offset)
    return [ApplicantOut.model_validate(r) for r in rows]


@applicants_router.get("/{applicant_id}", response_model=ApplicantOut)
async def detail(
    applicant_id: UUID, db: DbSession, user: CurrentUser
) -> ApplicantOut:
    row = await get_applicant(db, applicant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="applicant not found")
    return ApplicantOut.model_validate(row)
