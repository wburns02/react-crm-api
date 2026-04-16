from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.applicant_schemas import ApplicantIn
from app.hr.shared.audit import write_audit


async def create_applicant(
    db: AsyncSession, payload: ApplicantIn, *, actor_user_id: int | None
) -> HrApplicant:
    row = HrApplicant(**payload.model_dump())
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        entity_type="applicant",
        entity_id=row.id,
        event="created",
        diff={"email": [None, row.email], "source": [None, row.source]},
        actor_user_id=actor_user_id,
    )
    return row


async def get_applicant(db: AsyncSession, applicant_id: UUID) -> HrApplicant | None:
    return (
        await db.execute(select(HrApplicant).where(HrApplicant.id == applicant_id))
    ).scalar_one_or_none()


async def list_applicants(
    db: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[HrApplicant]:
    stmt = (
        select(HrApplicant)
        .order_by(HrApplicant.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list((await db.execute(stmt)).scalars().all())
