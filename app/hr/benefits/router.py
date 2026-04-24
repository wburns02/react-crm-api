from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.hr.benefits.models import (
    HrBenefitEnrollment,
    HrBenefitEoiRequest,
    HrBenefitEvent,
    HrBenefitHistory,
)
from app.hr.benefits.schemas import (
    BenefitsOverviewOut,
    EnrollmentOut,
    EoiRequestOut,
    EventOut,
    HistoryOut,
)
from app.hr.benefits.seed import seed_benefits_demo


benefits_router = APIRouter(prefix="/benefits", tags=["hr-benefits"])


@benefits_router.get("/enrollments", response_model=list[EnrollmentOut])
async def list_enrollments(
    db: DbSession,
    user: CurrentUser,
    benefit_type: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[EnrollmentOut]:
    stmt = select(HrBenefitEnrollment).order_by(
        HrBenefitEnrollment.employee_name.asc()
    )
    if benefit_type:
        stmt = stmt.where(HrBenefitEnrollment.benefit_type == benefit_type)
    if status:
        stmt = stmt.where(HrBenefitEnrollment.status == status)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(HrBenefitEnrollment.employee_name).like(needle),
                func.lower(HrBenefitEnrollment.plan_name).like(needle),
                func.lower(HrBenefitEnrollment.carrier).like(needle),
            )
        )
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [EnrollmentOut.model_validate(r) for r in rows]


@benefits_router.get("/events", response_model=list[EventOut])
async def list_events(
    db: DbSession,
    user: CurrentUser,
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    include_archived: bool = Query(False),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[EventOut]:
    stmt = select(HrBenefitEvent).order_by(
        HrBenefitEvent.effective_date.asc().nullslast()
    )
    if event_type:
        stmt = stmt.where(HrBenefitEvent.event_type == event_type)
    if status:
        stmt = stmt.where(HrBenefitEvent.status == status)
    if not include_archived:
        stmt = stmt.where(HrBenefitEvent.is_archived.is_(False))
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(HrBenefitEvent.employee_name).like(needle))
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [EventOut.model_validate(r) for r in rows]


@benefits_router.get("/eoi", response_model=list[EoiRequestOut])
async def list_eoi(
    db: DbSession,
    user: CurrentUser,
    benefit_type: str | None = Query(None),
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[EoiRequestOut]:
    stmt = select(HrBenefitEoiRequest).order_by(
        HrBenefitEoiRequest.created_at.desc()
    )
    if benefit_type:
        stmt = stmt.where(HrBenefitEoiRequest.benefit_type == benefit_type)
    if status:
        stmt = stmt.where(HrBenefitEoiRequest.status == status)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(HrBenefitEoiRequest.employee_name).like(needle),
                func.lower(HrBenefitEoiRequest.member_name).like(needle),
            )
        )
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [EoiRequestOut.model_validate(r) for r in rows]


@benefits_router.get("/history", response_model=list[HistoryOut])
async def list_history(
    db: DbSession,
    user: CurrentUser,
    change_type: str | None = Query(None),
    since: date | None = Query(None),
    until: date | None = Query(None),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[HistoryOut]:
    stmt = select(HrBenefitHistory).order_by(
        HrBenefitHistory.completed_date.desc().nullslast()
    )
    if change_type:
        stmt = stmt.where(HrBenefitHistory.change_type == change_type)
    if since:
        stmt = stmt.where(HrBenefitHistory.completed_date >= since)
    if until:
        stmt = stmt.where(HrBenefitHistory.completed_date <= until)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(func.lower(HrBenefitHistory.employee_name).like(needle))
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [HistoryOut.model_validate(r) for r in rows]


@benefits_router.get("/overview", response_model=BenefitsOverviewOut)
async def overview(db: DbSession, user: CurrentUser) -> BenefitsOverviewOut:
    enrollments = (await db.execute(select(HrBenefitEnrollment))).scalars().all()
    events = (await db.execute(select(HrBenefitEvent))).scalars().all()
    eoi = (await db.execute(select(HrBenefitEoiRequest))).scalars().all()

    by_type: dict[str, int] = {}
    total_cost = Decimal("0")
    total_ded = Decimal("0")
    active = waived = terminated = 0
    for e in enrollments:
        by_type[e.benefit_type] = by_type.get(e.benefit_type, 0) + 1
        if e.status == "active":
            active += 1
            if e.monthly_cost:
                total_cost += Decimal(e.monthly_cost)
            if e.monthly_deduction:
                total_ded += Decimal(e.monthly_deduction)
        elif e.status == "waived":
            waived += 1
        elif e.status == "terminated":
            terminated += 1

    pending_events = sum(1 for x in events if x.status == "pending" and not x.is_archived)
    pending_eoi = sum(1 for x in eoi if x.status == "pending")

    return BenefitsOverviewOut(
        total_enrollments=len(enrollments),
        active_enrollments=active,
        waived=waived,
        terminated=terminated,
        pending_events=pending_events,
        pending_eoi=pending_eoi,
        by_benefit_type=by_type,
        total_monthly_cost=total_cost,
        total_monthly_deduction=total_ded,
        generated_at=datetime.now(timezone.utc),
    )


@benefits_router.post("/seed-demo")
async def seed_demo(db: DbSession, user: CurrentUser) -> dict:
    return await seed_benefits_demo(db)
