from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.hr.benefits.models import (
    HrBenefitAccountStructure,
    HrBenefitCarrierIntegration,
    HrBenefitEnrollment,
    HrBenefitEoiRequest,
    HrBenefitEvent,
    HrBenefitHistory,
    HrBenefitScheduledDeduction,
)
from app.hr.benefits.schemas import (
    AccountStructureIn,
    AccountStructureOut,
    BenefitsOverviewOut,
    CarrierIntegrationOut,
    EnrollmentOut,
    EoiRequestOut,
    EventOut,
    HistoryOut,
    ScheduledDeductionOut,
    ScheduledDeductionPatch,
)
from app.hr.benefits.seed import (
    seed_benefits_demo,
    seed_integrations_and_deductions,
)


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


@benefits_router.post("/seed-integrations")
async def seed_integrations(db: DbSession, user: CurrentUser) -> dict:
    return await seed_integrations_and_deductions(db)


# ─── Integrations ───────────────────────────────────────────

@benefits_router.get(
    "/integrations", response_model=list[CarrierIntegrationOut]
)
async def list_integrations(
    db: DbSession,
    user: CurrentUser,
    upcoming: bool = Query(False),
    q: str | None = Query(None, max_length=128),
) -> list[CarrierIntegrationOut]:
    stmt = select(HrBenefitCarrierIntegration).where(
        HrBenefitCarrierIntegration.is_upcoming == upcoming
    )
    if q:
        stmt = stmt.where(
            func.lower(HrBenefitCarrierIntegration.carrier).like(
                f"%{q.strip().lower()}%"
            )
        )
    stmt = stmt.order_by(HrBenefitCarrierIntegration.carrier.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [CarrierIntegrationOut.model_validate(r) for r in rows]


@benefits_router.patch(
    "/integrations/{integration_id}/form-forwarding",
    response_model=CarrierIntegrationOut,
)
async def toggle_form_forwarding(
    integration_id: UUID,
    enabled: bool,
    db: DbSession,
    user: CurrentUser,
) -> CarrierIntegrationOut:
    row = (
        await db.execute(
            select(HrBenefitCarrierIntegration).where(
                HrBenefitCarrierIntegration.id == integration_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="integration not found")
    row.form_forwarding_enabled = enabled
    await db.commit()
    await db.refresh(row)
    return CarrierIntegrationOut.model_validate(row)


# ─── Account structure ──────────────────────────────────────

@benefits_router.get(
    "/account-structures", response_model=list[AccountStructureOut]
)
async def list_account_structures(
    db: DbSession, user: CurrentUser
) -> list[AccountStructureOut]:
    rows = (
        await db.execute(
            select(HrBenefitAccountStructure).order_by(
                HrBenefitAccountStructure.carrier.asc()
            )
        )
    ).scalars().all()
    return [AccountStructureOut.model_validate(r) for r in rows]


@benefits_router.post(
    "/account-structures",
    response_model=AccountStructureOut,
    status_code=201,
)
async def add_account_structure(
    payload: AccountStructureIn, db: DbSession, user: CurrentUser
) -> AccountStructureOut:
    row = HrBenefitAccountStructure(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return AccountStructureOut.model_validate(row)


@benefits_router.delete(
    "/account-structures/{structure_id}", status_code=204
)
async def delete_account_structure(
    structure_id: UUID, db: DbSession, user: CurrentUser
) -> None:
    row = (
        await db.execute(
            select(HrBenefitAccountStructure).where(
                HrBenefitAccountStructure.id == structure_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(row)
    await db.commit()


# ─── Scheduled deductions ───────────────────────────────────

@benefits_router.get(
    "/scheduled-deductions", response_model=list[ScheduledDeductionOut]
)
async def list_scheduled_deductions(
    db: DbSession,
    user: CurrentUser,
    benefit_type: str | None = Query(None),
    only_discrepancies: bool = Query(False),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[ScheduledDeductionOut]:
    stmt = select(HrBenefitScheduledDeduction).order_by(
        HrBenefitScheduledDeduction.employee_name.asc()
    )
    if benefit_type:
        stmt = stmt.where(HrBenefitScheduledDeduction.benefit_type == benefit_type)
    if q:
        stmt = stmt.where(
            func.lower(HrBenefitScheduledDeduction.employee_name).like(
                f"%{q.strip().lower()}%"
            )
        )
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    if only_discrepancies:
        rows = [r for r in rows if _has_discrepancy(r)]
    return [ScheduledDeductionOut.model_validate(r) for r in rows]


@benefits_router.post("/scheduled-deductions/push")
async def push_scheduled_deductions(
    db: DbSession,
    user: CurrentUser,
    benefit_type: str | None = Query(None),
) -> dict:
    """Resolve discrepancies by copying Rippling calc → in-payroll values."""
    stmt = select(HrBenefitScheduledDeduction)
    if benefit_type:
        stmt = stmt.where(HrBenefitScheduledDeduction.benefit_type == benefit_type)
    rows = (await db.execute(stmt)).scalars().all()
    fixed = 0
    for r in rows:
        if _has_discrepancy(r):
            r.ee_in_payroll = r.ee_rippling
            r.er_in_payroll = r.er_rippling
            r.taxable_in_payroll = r.taxable_rippling
            fixed += 1
    await db.commit()
    return {"pushed": fixed, "benefit_type": benefit_type}


@benefits_router.post("/scheduled-deductions/auto-manage-all")
async def auto_manage_all(
    db: DbSession,
    user: CurrentUser,
    benefit_type: str | None = Query(None),
) -> dict:
    stmt = select(HrBenefitScheduledDeduction).where(
        HrBenefitScheduledDeduction.auto_manage.is_(False)
    )
    if benefit_type:
        stmt = stmt.where(HrBenefitScheduledDeduction.benefit_type == benefit_type)
    rows = (await db.execute(stmt)).scalars().all()
    for r in rows:
        r.auto_manage = True
    await db.commit()
    return {"updated": len(rows), "benefit_type": benefit_type}


@benefits_router.patch(
    "/scheduled-deductions/{row_id}", response_model=ScheduledDeductionOut
)
async def patch_scheduled_deduction(
    row_id: UUID,
    patch: ScheduledDeductionPatch,
    db: DbSession,
    user: CurrentUser,
) -> ScheduledDeductionOut:
    row = (
        await db.execute(
            select(HrBenefitScheduledDeduction).where(
                HrBenefitScheduledDeduction.id == row_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    if patch.auto_manage is not None:
        row.auto_manage = patch.auto_manage
    if patch.ee_in_payroll is not None:
        row.ee_in_payroll = patch.ee_in_payroll
    if patch.er_in_payroll is not None:
        row.er_in_payroll = patch.er_in_payroll
    if patch.taxable_in_payroll is not None:
        row.taxable_in_payroll = patch.taxable_in_payroll
    await db.commit()
    await db.refresh(row)
    return ScheduledDeductionOut.model_validate(row)


def _has_discrepancy(r: HrBenefitScheduledDeduction) -> bool:
    """True if Rippling calc != in-payroll on any of the three pairs."""
    return (
        (r.ee_rippling or Decimal("0")) != (r.ee_in_payroll or Decimal("0"))
        or (r.er_rippling or Decimal("0")) != (r.er_in_payroll or Decimal("0"))
        or (r.taxable_rippling or Decimal("0")) != (r.taxable_in_payroll or Decimal("0"))
    )
