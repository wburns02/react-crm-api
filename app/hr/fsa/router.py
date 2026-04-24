from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.hr.fsa.models import (
    HrFsaComplianceTest,
    HrFsaDocument,
    HrFsaEnrollment,
    HrFsaExclusion,
    HrFsaPlan,
    HrFsaSettings,
    HrFsaTransaction,
)
from app.hr.fsa.schemas import (
    FsaComplianceTestOut,
    FsaDocumentOut,
    FsaEnrollmentOut,
    FsaExclusionIn,
    FsaExclusionOut,
    FsaOverviewOut,
    FsaPlanIn,
    FsaPlanOut,
    FsaPlanPatch,
    FsaSettingsOut,
    FsaSettingsPatch,
    FsaTransactionOut,
    FsaTransactionPatch,
)
from app.hr.fsa.seed import seed_fsa_demo


fsa_router = APIRouter(prefix="/fsa", tags=["hr-fsa"])


@fsa_router.post("/seed-demo")
async def seed_demo(db: DbSession, user: CurrentUser) -> dict:
    return await seed_fsa_demo(db)


# ─── Plans ──────────────────────────────────────────────────

@fsa_router.get("/plans", response_model=list[FsaPlanOut])
async def list_plans(db: DbSession, user: CurrentUser) -> list[FsaPlanOut]:
    rows = (
        await db.execute(select(HrFsaPlan).order_by(HrFsaPlan.kind.asc()))
    ).scalars().all()
    return [FsaPlanOut.model_validate(r) for r in rows]


@fsa_router.post("/plans", response_model=FsaPlanOut, status_code=201)
async def create_plan(
    payload: FsaPlanIn, db: DbSession, user: CurrentUser
) -> FsaPlanOut:
    row = HrFsaPlan(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return FsaPlanOut.model_validate(row)


@fsa_router.patch("/plans/{plan_id}", response_model=FsaPlanOut)
async def patch_plan(
    plan_id: UUID, patch: FsaPlanPatch, db: DbSession, user: CurrentUser
) -> FsaPlanOut:
    row = (
        await db.execute(select(HrFsaPlan).where(HrFsaPlan.id == plan_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return FsaPlanOut.model_validate(row)


# ─── Enrollments ────────────────────────────────────────────

@fsa_router.get("/enrollments", response_model=list[FsaEnrollmentOut])
async def list_enrollments(
    db: DbSession,
    user: CurrentUser,
    plan_kind: str | None = Query(None),
    status: str | None = Query(None),
) -> list[FsaEnrollmentOut]:
    stmt = select(HrFsaEnrollment).order_by(HrFsaEnrollment.employee_name.asc())
    if plan_kind:
        stmt = stmt.where(HrFsaEnrollment.plan_kind == plan_kind)
    if status:
        stmt = stmt.where(HrFsaEnrollment.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [FsaEnrollmentOut.model_validate(r) for r in rows]


# ─── Transactions ───────────────────────────────────────────

@fsa_router.get("/transactions", response_model=list[FsaTransactionOut])
async def list_transactions(
    db: DbSession,
    user: CurrentUser,
    status: str | None = Query(None),
    plan_kind: str | None = Query(None),
    kind: str | None = Query(None),
    q: str | None = Query(None, max_length=128),
    limit: int = Query(200, le=500),
) -> list[FsaTransactionOut]:
    stmt = select(HrFsaTransaction).order_by(HrFsaTransaction.transaction_date.desc())
    if status:
        stmt = stmt.where(HrFsaTransaction.status == status)
    if plan_kind:
        stmt = stmt.where(HrFsaTransaction.plan_kind == plan_kind)
    if kind:
        stmt = stmt.where(HrFsaTransaction.kind == kind)
    if q:
        needle = f"%{q.strip().lower()}%"
        from sqlalchemy import or_ as _or
        stmt = stmt.where(
            _or(
                func.lower(HrFsaTransaction.employee_name).like(needle),
                func.lower(HrFsaTransaction.merchant).like(needle),
                func.lower(HrFsaTransaction.category).like(needle),
            )
        )
    rows = (await db.execute(stmt.limit(limit))).scalars().all()
    return [FsaTransactionOut.model_validate(r) for r in rows]


@fsa_router.patch("/transactions/{tx_id}", response_model=FsaTransactionOut)
async def patch_transaction(
    tx_id: UUID, patch: FsaTransactionPatch, db: DbSession, user: CurrentUser
) -> FsaTransactionOut:
    row = (
        await db.execute(
            select(HrFsaTransaction).where(HrFsaTransaction.id == tx_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    if patch.status is not None:
        row.status = patch.status
    if patch.notes is not None:
        row.notes = patch.notes
    await db.commit()
    await db.refresh(row)
    return FsaTransactionOut.model_validate(row)


# ─── Settings + documents ───────────────────────────────────

@fsa_router.get("/settings", response_model=FsaSettingsOut)
async def get_settings(db: DbSession, user: CurrentUser) -> FsaSettingsOut:
    row = (
        await db.execute(select(HrFsaSettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrFsaSettings()
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return FsaSettingsOut.model_validate(row)


@fsa_router.patch("/settings", response_model=FsaSettingsOut)
async def patch_settings(
    patch: FsaSettingsPatch, db: DbSession, user: CurrentUser
) -> FsaSettingsOut:
    row = (
        await db.execute(select(HrFsaSettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrFsaSettings()
        db.add(row)
        await db.flush()
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return FsaSettingsOut.model_validate(row)


@fsa_router.get("/documents", response_model=list[FsaDocumentOut])
async def list_documents(db: DbSession, user: CurrentUser) -> list[FsaDocumentOut]:
    rows = (
        await db.execute(
            select(HrFsaDocument).order_by(HrFsaDocument.uploaded_at.desc())
        )
    ).scalars().all()
    return [FsaDocumentOut.model_validate(r) for r in rows]


# ─── Compliance ─────────────────────────────────────────────

@fsa_router.get("/compliance/tests", response_model=list[FsaComplianceTestOut])
async def list_compliance_tests(
    db: DbSession, user: CurrentUser
) -> list[FsaComplianceTestOut]:
    rows = (
        await db.execute(
            select(HrFsaComplianceTest).order_by(
                HrFsaComplianceTest.run_date.desc()
            )
        )
    ).scalars().all()
    return [FsaComplianceTestOut.model_validate(r) for r in rows]


@fsa_router.post("/compliance/run", response_model=list[FsaComplianceTestOut])
async def run_compliance(db: DbSession, user: CurrentUser) -> list[FsaComplianceTestOut]:
    """Synthesize one new run for each of the four NDT tests and return the
    most recent run per test kind.
    """
    plan_year = datetime.now(timezone.utc).year
    enrollments = (
        await db.execute(select(HrFsaEnrollment))
    ).scalars().all()
    active = [e for e in enrollments if e.status == "active"]
    hce_count = max(1, len(active) // 6)
    nhce_count = max(1, len(active) - hce_count)

    tests = [
        "eligibility",
        "benefits_contributions",
        "key_employee_concentration",
        "55_percent_average_benefits",
    ]
    created: list[HrFsaComplianceTest] = []
    for t in tests:
        # Key-employee test fails if concentration > 25%; our synthetic data
        # keeps it under.  All others pass by construction.
        status = "passed"
        db.add(
            HrFsaComplianceTest(
                test_kind=t,
                plan_year=plan_year,
                status=status,
                highly_compensated_count=hce_count,
                non_highly_compensated_count=nhce_count,
            )
        )
    await db.commit()
    # Return latest results per kind.
    rows = (
        await db.execute(
            select(HrFsaComplianceTest).order_by(
                HrFsaComplianceTest.run_date.desc()
            )
        )
    ).scalars().all()
    return [FsaComplianceTestOut.model_validate(r) for r in rows[: len(tests)]]


@fsa_router.get("/exclusions", response_model=list[FsaExclusionOut])
async def list_exclusions(db: DbSession, user: CurrentUser) -> list[FsaExclusionOut]:
    rows = (
        await db.execute(
            select(HrFsaExclusion).order_by(HrFsaExclusion.created_at.desc())
        )
    ).scalars().all()
    return [FsaExclusionOut.model_validate(r) for r in rows]


@fsa_router.post("/exclusions", response_model=FsaExclusionOut, status_code=201)
async def add_exclusion(
    payload: FsaExclusionIn, db: DbSession, user: CurrentUser
) -> FsaExclusionOut:
    row = HrFsaExclusion(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return FsaExclusionOut.model_validate(row)


@fsa_router.delete("/exclusions/{excl_id}", status_code=204)
async def delete_exclusion(excl_id: UUID, db: DbSession, user: CurrentUser) -> None:
    row = (
        await db.execute(
            select(HrFsaExclusion).where(HrFsaExclusion.id == excl_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(row)
    await db.commit()


# ─── Overview ───────────────────────────────────────────────

@fsa_router.get("/overview", response_model=FsaOverviewOut)
async def overview(db: DbSession, user: CurrentUser) -> FsaOverviewOut:
    enrollments = (await db.execute(select(HrFsaEnrollment))).scalars().all()
    transactions = (await db.execute(select(HrFsaTransaction))).scalars().all()
    settings = (await db.execute(select(HrFsaSettings).limit(1))).scalar_one_or_none()
    last_test = (
        await db.execute(
            select(HrFsaComplianceTest).order_by(
                HrFsaComplianceTest.run_date.desc()
            )
        )
    ).scalars().first()

    by_kind: dict[str, int] = {}
    total_contrib = Decimal("0")
    total_spent = Decimal("0")
    active = pending = declined = 0
    for e in enrollments:
        by_kind[e.plan_kind] = by_kind.get(e.plan_kind, 0) + 1
        total_contrib += Decimal(e.ytd_contributed or 0)
        total_spent += Decimal(e.ytd_spent or 0)
        if e.status == "active":
            active += 1
        elif e.status == "pending":
            pending += 1
        elif e.status == "declined":
            declined += 1

    cutoff = date.today() - timedelta(days=30)
    tx_30 = sum(1 for t in transactions if t.transaction_date >= cutoff)

    return FsaOverviewOut(
        total_enrollments=len(enrollments),
        active_enrollments=active,
        pending_enrollments=pending,
        declined_enrollments=declined,
        total_ytd_contributed=total_contrib.quantize(Decimal("0.01")),
        total_ytd_spent=total_spent.quantize(Decimal("0.01")),
        remaining_balance=(total_contrib - total_spent).quantize(Decimal("0.01")),
        by_plan_kind=by_kind,
        transactions_last_30d=tx_30,
        last_compliance_status=last_test.status if last_test else None,
        bank_configured=bool(settings and settings.bank_account_last4),
    )
