from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.schemas import (
    RequisitionIn,
    RequisitionOut,
    RequisitionPatch,
    RequisitionWithCountsOut,
)
from app.hr.recruiting.services import (
    applicant_counts_for_requisitions,
    close_requisition,
    create_requisition,
    list_requisitions,
    update_requisition,
)


recruiting_router = APIRouter(prefix="/recruiting", tags=["hr-recruiting"])


@recruiting_router.post(
    "/requisitions",
    response_model=RequisitionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    payload: RequisitionIn, db: DbSession, user: CurrentUser
) -> RequisitionOut:
    row = await create_requisition(db, payload, actor_user_id=user.id)
    await db.commit()
    return RequisitionOut.model_validate(row)


@recruiting_router.get("/requisitions", response_model=list[RequisitionWithCountsOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
) -> list[RequisitionWithCountsOut]:
    rows = await list_requisitions(db, status=status_filter)
    counts = await applicant_counts_for_requisitions(
        db, requisition_ids=[r.id for r in rows]
    )
    return [
        RequisitionWithCountsOut(
            **RequisitionOut.model_validate(r).model_dump(),
            applicant_count=counts.get(r.id, 0),
        )
        for r in rows
    ]


@recruiting_router.patch(
    "/requisitions/{requisition_id}", response_model=RequisitionOut
)
async def patch_(
    requisition_id: UUID,
    payload: RequisitionPatch,
    db: DbSession,
    user: CurrentUser,
) -> RequisitionOut:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    row = await update_requisition(
        db, requisition_id=requisition_id, patch=data, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    await db.commit()
    return RequisitionOut.model_validate(row)


@recruiting_router.delete(
    "/requisitions/{requisition_id}", response_model=RequisitionOut
)
async def delete_(
    requisition_id: UUID, db: DbSession, user: CurrentUser
) -> RequisitionOut:
    row = await close_requisition(
        db, requisition_id=requisition_id, actor_user_id=user.id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="requisition not found")
    await db.commit()
    return RequisitionOut.model_validate(row)
