from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplication
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
        row.opened_at = datetime.utcnow()
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


async def update_requisition(
    db: AsyncSession,
    *,
    requisition_id: UUID,
    patch: dict,
    actor_user_id: int | None,
) -> HrRequisition | None:
    row = (
        await db.execute(select(HrRequisition).where(HrRequisition.id == requisition_id))
    ).scalar_one_or_none()
    if row is None:
        return None
    diff: dict[str, list] = {}
    for key, value in patch.items():
        current = getattr(row, key)
        if current != value:
            diff[key] = [current, value]
            setattr(row, key, value)
    if "status" in diff:
        new_status = diff["status"][1]
        if new_status == "open" and row.opened_at is None:
            row.opened_at = datetime.utcnow()
        if new_status == "closed":
            row.closed_at = datetime.utcnow()
    await db.flush()
    if diff:
        await write_audit(
            db,
            entity_type="requisition",
            entity_id=row.id,
            event="updated",
            diff={
                k: [str(a) if a is not None else None, str(b) if b is not None else None]
                for k, (a, b) in diff.items()
            },
            actor_user_id=actor_user_id,
        )
    return row


async def close_requisition(
    db: AsyncSession, *, requisition_id: UUID, actor_user_id: int | None
) -> HrRequisition | None:
    return await update_requisition(
        db,
        requisition_id=requisition_id,
        patch={"status": "closed"},
        actor_user_id=actor_user_id,
    )


async def applicant_counts_for_requisitions(
    db: AsyncSession, *, requisition_ids: list[UUID]
) -> dict[UUID, int]:
    if not requisition_ids:
        return {}
    rows = (
        await db.execute(
            select(HrApplication.requisition_id, func.count(HrApplication.id))
            .where(HrApplication.requisition_id.in_(requisition_ids))
            .group_by(HrApplication.requisition_id)
        )
    ).all()
    return {rid: n for rid, n in rows}
