from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.payroll.models import HrPayrollPeopleStatus, HrPayRun
from app.hr.payroll.schemas import (
    PayRunOut,
    PayRunPatch,
    PayrollPeopleOut,
    PayrollPeoplePatch,
)
from app.hr.payroll.seed import seed_payroll_demo


payroll_router = APIRouter(prefix="/payroll", tags=["hr-payroll"])


@payroll_router.post("/seed-demo")
async def seed_demo(db: DbSession, user: CurrentUser) -> dict:
    return await seed_payroll_demo(db)


@payroll_router.get("/pay-runs", response_model=list[PayRunOut])
async def list_pay_runs(
    db: DbSession,
    user: CurrentUser,
    status: str | None = Query(None),
) -> list[PayRunOut]:
    stmt = select(HrPayRun).order_by(
        HrPayRun.pay_date.desc().nullslast()
    )
    if status:
        stmt = stmt.where(HrPayRun.status == status)
    rows = (await db.execute(stmt)).scalars().all()
    return [PayRunOut.model_validate(r) for r in rows]


@payroll_router.patch("/pay-runs/{run_id}", response_model=PayRunOut)
async def patch_pay_run(
    run_id: UUID, patch: PayRunPatch, db: DbSession, user: CurrentUser
) -> PayRunOut:
    row = (
        await db.execute(select(HrPayRun).where(HrPayRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pay run not found")
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return PayRunOut.model_validate(row)


@payroll_router.post("/pay-runs/{run_id}/approve", response_model=PayRunOut)
async def approve_pay_run(
    run_id: UUID, db: DbSession, user: CurrentUser
) -> PayRunOut:
    row = (
        await db.execute(select(HrPayRun).where(HrPayRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pay run not found")
    row.status = "paid"
    row.funding_method = row.funding_method or "ACH"
    row.action_text = "Make Changes"
    await db.commit()
    await db.refresh(row)
    return PayRunOut.model_validate(row)


@payroll_router.post("/pay-runs/{run_id}/archive", response_model=PayRunOut)
async def archive_pay_run(
    run_id: UUID, db: DbSession, user: CurrentUser
) -> PayRunOut:
    row = (
        await db.execute(select(HrPayRun).where(HrPayRun.id == run_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="pay run not found")
    row.status = "archived"
    row.archived_by = "Admin"
    row.action_text = "Unarchive"
    await db.commit()
    await db.refresh(row)
    return PayRunOut.model_validate(row)


@payroll_router.get("/people", response_model=list[PayrollPeopleOut])
async def list_people(
    db: DbSession,
    user: CurrentUser,
    bucket: str | None = Query(None),
) -> list[PayrollPeopleOut]:
    stmt = select(HrPayrollPeopleStatus).order_by(
        HrPayrollPeopleStatus.critical_missing_count.desc(),
        HrPayrollPeopleStatus.employee_name.asc(),
    )
    if bucket:
        stmt = stmt.where(HrPayrollPeopleStatus.bucket == bucket)
    rows = (await db.execute(stmt)).scalars().all()
    return [PayrollPeopleOut.model_validate(r) for r in rows]


@payroll_router.patch("/people/{person_id}", response_model=PayrollPeopleOut)
async def patch_person(
    person_id: UUID, patch: PayrollPeoplePatch, db: DbSession, user: CurrentUser
) -> PayrollPeopleOut:
    row = (
        await db.execute(
            select(HrPayrollPeopleStatus).where(HrPayrollPeopleStatus.id == person_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return PayrollPeopleOut.model_validate(row)


@payroll_router.post("/people/{person_id}/request-info")
async def request_missing_info(
    person_id: UUID, db: DbSession, user: CurrentUser
) -> dict:
    row = (
        await db.execute(
            select(HrPayrollPeopleStatus).where(HrPayrollPeopleStatus.id == person_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    # Mark as "request sent" — not completion, but visible state change
    row.status = "request_sent"
    await db.commit()
    return {"requested": True, "employee": row.employee_name}
