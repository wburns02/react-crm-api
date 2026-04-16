from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.models import HrRequisition
from app.hr.recruiting.schemas import RequisitionIn
from app.hr.shared.audit import write_audit


async def create_requisition(
    db: AsyncSession,
    payload: RequisitionIn,
    *,
    actor_user_id: int | None,
) -> HrRequisition:
    data = payload.model_dump()
    row = HrRequisition(**data, created_by=actor_user_id)
    if payload.status == "open":
        row.opened_at = datetime.now(timezone.utc)
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="requisition",
        entity_id=row.id,
        event="created",
        diff={k: [None, str(v) if v is not None else None] for k, v in data.items()},
        actor_user_id=actor_user_id,
    )
    return row


async def list_requisitions(
    db: AsyncSession, *, status: str | None = None
) -> list[HrRequisition]:
    stmt = select(HrRequisition).order_by(HrRequisition.created_at.desc())
    if status is not None:
        stmt = stmt.where(HrRequisition.status == status)
    return list((await db.execute(stmt)).scalars().all())


async def get_requisition_by_slug(db: AsyncSession, slug: str) -> HrRequisition | None:
    return (
        await db.execute(select(HrRequisition).where(HrRequisition.slug == slug))
    ).scalar_one_or_none()
