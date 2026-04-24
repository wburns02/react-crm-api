from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, DbSession
from app.hr.cobra.models import (
    HrCobraEnrollment,
    HrCobraNotice,
    HrCobraPayment,
    HrCobraPreRipplingPlan,
    HrCobraSettings,
)
from app.hr.cobra.schemas import (
    CobraEnrollmentIn,
    CobraEnrollmentOut,
    CobraEnrollmentPatch,
    CobraNoticeOut,
    CobraPaymentOut,
    CobraPreRipplingPlanIn,
    CobraPreRipplingPlanOut,
    CobraSettingsOut,
    CobraSettingsPatch,
)
from app.hr.cobra.seed import seed_cobra_demo


cobra_router = APIRouter(prefix="/cobra", tags=["hr-cobra"])


@cobra_router.post("/seed-demo")
async def seed_demo(db: DbSession, user: CurrentUser) -> dict:
    return await seed_cobra_demo(db)


# Enrollments
@cobra_router.get("/enrollments", response_model=list[CobraEnrollmentOut])
async def list_enrollments(
    db: DbSession,
    user: CurrentUser,
    bucket: str | None = Query(None),
    q: str | None = Query(None, max_length=128),
) -> list[CobraEnrollmentOut]:
    stmt = select(HrCobraEnrollment).order_by(HrCobraEnrollment.employee_name.asc())
    if bucket:
        stmt = stmt.where(HrCobraEnrollment.bucket == bucket)
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(HrCobraEnrollment.employee_name).like(needle),
                func.lower(HrCobraEnrollment.beneficiary_name).like(needle),
            )
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [CobraEnrollmentOut.model_validate(r) for r in rows]


@cobra_router.post(
    "/enrollments", response_model=CobraEnrollmentOut, status_code=201
)
async def add_enrollment(
    payload: CobraEnrollmentIn, db: DbSession, user: CurrentUser
) -> CobraEnrollmentOut:
    row = HrCobraEnrollment(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CobraEnrollmentOut.model_validate(row)


@cobra_router.patch(
    "/enrollments/{enrollment_id}", response_model=CobraEnrollmentOut
)
async def patch_enrollment(
    enrollment_id: UUID,
    patch: CobraEnrollmentPatch,
    db: DbSession,
    user: CurrentUser,
) -> CobraEnrollmentOut:
    row = (
        await db.execute(
            select(HrCobraEnrollment).where(HrCobraEnrollment.id == enrollment_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return CobraEnrollmentOut.model_validate(row)


@cobra_router.post("/enrollments/{enrollment_id}/send-notice")
async def send_notice(
    enrollment_id: UUID, db: DbSession, user: CurrentUser
) -> dict:
    enr = (
        await db.execute(
            select(HrCobraEnrollment).where(HrCobraEnrollment.id == enrollment_id)
        )
    ).scalar_one_or_none()
    if enr is None:
        raise HTTPException(status_code=404, detail="not found")
    notice = HrCobraNotice(
        enrollment_id=enr.id,
        employee_name=enr.employee_name,
        beneficiary_name=enr.beneficiary_name,
        type_of_notice="COBRA Election Notice",
        addressed_to=enr.beneficiary_name,
        notice_url=f"https://example.com/notices/{enr.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.pdf",
        tracking_status="In Production",
        updated_on=date.today(),
    )
    db.add(notice)
    enr.notice_sent_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notice)
    return {"notice_id": str(notice.id), "status": notice.tracking_status}


# Payments
@cobra_router.get("/payments", response_model=list[CobraPaymentOut])
async def list_payments(
    db: DbSession,
    user: CurrentUser,
    status: str | None = Query(None),
    q: str | None = Query(None, max_length=128),
) -> list[CobraPaymentOut]:
    stmt = select(HrCobraPayment).order_by(HrCobraPayment.month.desc())
    if status:
        stmt = stmt.where(HrCobraPayment.status == status)
    if q:
        stmt = stmt.where(
            func.lower(HrCobraPayment.employee_name).like(f"%{q.strip().lower()}%")
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [CobraPaymentOut.model_validate(r) for r in rows]


# Notices
@cobra_router.get("/notices", response_model=list[CobraNoticeOut])
async def list_notices(
    db: DbSession,
    user: CurrentUser,
    q: str | None = Query(None, max_length=128),
) -> list[CobraNoticeOut]:
    stmt = select(HrCobraNotice).order_by(HrCobraNotice.created_at.desc())
    if q:
        stmt = stmt.where(
            func.lower(HrCobraNotice.employee_name).like(f"%{q.strip().lower()}%")
        )
    rows = (await db.execute(stmt)).scalars().all()
    return [CobraNoticeOut.model_validate(r) for r in rows]


# Settings
@cobra_router.get("/settings", response_model=CobraSettingsOut)
async def get_settings(db: DbSession, user: CurrentUser) -> CobraSettingsOut:
    row = (
        await db.execute(select(HrCobraSettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrCobraSettings()
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return CobraSettingsOut.model_validate(row)


@cobra_router.patch("/settings", response_model=CobraSettingsOut)
async def patch_settings(
    patch: CobraSettingsPatch, db: DbSession, user: CurrentUser
) -> CobraSettingsOut:
    row = (
        await db.execute(select(HrCobraSettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrCobraSettings()
        db.add(row)
        await db.flush()
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return CobraSettingsOut.model_validate(row)


# Pre-Rippling plans
@cobra_router.get(
    "/pre-plans", response_model=list[CobraPreRipplingPlanOut]
)
async def list_pre_plans(
    db: DbSession, user: CurrentUser
) -> list[CobraPreRipplingPlanOut]:
    rows = (
        await db.execute(
            select(HrCobraPreRipplingPlan).order_by(
                HrCobraPreRipplingPlan.effective_from.desc().nullslast()
            )
        )
    ).scalars().all()
    return [CobraPreRipplingPlanOut.model_validate(r) for r in rows]


@cobra_router.post(
    "/pre-plans", response_model=CobraPreRipplingPlanOut, status_code=201
)
async def add_pre_plan(
    payload: CobraPreRipplingPlanIn, db: DbSession, user: CurrentUser
) -> CobraPreRipplingPlanOut:
    row = HrCobraPreRipplingPlan(**payload.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CobraPreRipplingPlanOut.model_validate(row)


@cobra_router.delete("/pre-plans/{plan_id}", status_code=204)
async def delete_pre_plan(plan_id: UUID, db: DbSession, user: CurrentUser) -> None:
    row = (
        await db.execute(
            select(HrCobraPreRipplingPlan).where(HrCobraPreRipplingPlan.id == plan_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(row)
    await db.commit()
