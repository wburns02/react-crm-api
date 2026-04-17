from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplicant, HrApplication
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


async def search_applicants(
    db: AsyncSession,
    *,
    q: str | None = None,
    requisition_id: UUID | None = None,
    stage: str | None = None,
    source: str | None = None,
    since_days: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[HrApplicant]:
    """Paginated search + filter for the applicant inbox.

    Joins HrApplication only when requisition / stage filters are active.
    """
    needs_app_join = requisition_id is not None or stage is not None

    stmt = select(HrApplicant).order_by(HrApplicant.created_at.desc())

    if needs_app_join:
        stmt = stmt.join(HrApplication, HrApplication.applicant_id == HrApplicant.id).distinct()
        if requisition_id is not None:
            stmt = stmt.where(HrApplication.requisition_id == requisition_id)
        if stage is not None:
            stmt = stmt.where(HrApplication.stage == stage)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                HrApplicant.email.ilike(like),
                HrApplicant.first_name.ilike(like),
                HrApplicant.last_name.ilike(like),
                HrApplicant.phone.ilike(like),
            )
        )
    if source is not None:
        stmt = stmt.where(HrApplicant.source == source)
    if since_days is not None:
        since = datetime.utcnow() - timedelta(days=since_days)
        stmt = stmt.where(HrApplicant.created_at >= since)

    stmt = stmt.limit(limit).offset(offset)
    return list((await db.execute(stmt)).scalars().all())
