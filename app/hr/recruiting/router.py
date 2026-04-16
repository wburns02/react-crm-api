from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.schemas import RequisitionIn, RequisitionOut
from app.hr.recruiting.services import create_requisition, list_requisitions


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


@recruiting_router.get("/requisitions", response_model=list[RequisitionOut])
async def list_(
    db: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(None, alias="status"),
) -> list[RequisitionOut]:
    rows = await list_requisitions(db, status=status_filter)
    return [RequisitionOut.model_validate(r) for r in rows]
