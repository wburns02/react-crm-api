from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.aca.models import (
    HrAcaEmployeeHours,
    HrAcaFiling,
    HrAcaLookbackPolicy,
    HrBenefitCompanySettings,
    HrBenefitSignatory,
)
from app.hr.aca.schemas import (
    AcaFilingOut,
    BenefitSignatoryOut,
    BenefitSignatoryPatch,
    CompanySettingsOut,
    CompanySettingsPatch,
    EmployeeHoursOut,
    LookbackPolicyOut,
    LookbackPolicyPatch,
)
from app.hr.aca.seed import seed_aca_and_settings


aca_router = APIRouter(prefix="/aca", tags=["hr-aca"])


@aca_router.post("/seed-demo")
async def seed_demo(db: DbSession, user: CurrentUser) -> dict:
    return await seed_aca_and_settings(db)


@aca_router.get("/filings", response_model=list[AcaFilingOut])
async def list_filings(db: DbSession, user: CurrentUser) -> list[AcaFilingOut]:
    rows = (
        await db.execute(
            select(HrAcaFiling).order_by(HrAcaFiling.plan_year.desc())
        )
    ).scalars().all()
    return [AcaFilingOut.model_validate(r) for r in rows]


@aca_router.get("/lookback", response_model=LookbackPolicyOut)
async def get_lookback(db: DbSession, user: CurrentUser) -> LookbackPolicyOut:
    row = (
        await db.execute(select(HrAcaLookbackPolicy).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrAcaLookbackPolicy()
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return LookbackPolicyOut.model_validate(row)


@aca_router.patch("/lookback", response_model=LookbackPolicyOut)
async def patch_lookback(
    patch: LookbackPolicyPatch, db: DbSession, user: CurrentUser
) -> LookbackPolicyOut:
    row = (
        await db.execute(select(HrAcaLookbackPolicy).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrAcaLookbackPolicy()
        db.add(row)
        await db.flush()
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return LookbackPolicyOut.model_validate(row)


@aca_router.get("/employee-hours", response_model=list[EmployeeHoursOut])
async def list_hours(db: DbSession, user: CurrentUser) -> list[EmployeeHoursOut]:
    rows = (
        await db.execute(
            select(HrAcaEmployeeHours).order_by(
                HrAcaEmployeeHours.average_hours_per_week.desc()
            )
        )
    ).scalars().all()
    return [EmployeeHoursOut.model_validate(r) for r in rows]


# ─── Benefit settings (company-wide) ────────────────────────

benefit_settings_router = APIRouter(prefix="/benefit-company-settings", tags=["hr-benefit-settings"])


@benefit_settings_router.get("", response_model=CompanySettingsOut)
async def get_settings(db: DbSession, user: CurrentUser) -> CompanySettingsOut:
    row = (
        await db.execute(select(HrBenefitCompanySettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrBenefitCompanySettings()
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return CompanySettingsOut.model_validate(row)


@benefit_settings_router.patch("", response_model=CompanySettingsOut)
async def patch_settings(
    patch: CompanySettingsPatch, db: DbSession, user: CurrentUser
) -> CompanySettingsOut:
    row = (
        await db.execute(select(HrBenefitCompanySettings).limit(1))
    ).scalar_one_or_none()
    if row is None:
        row = HrBenefitCompanySettings()
        db.add(row)
        await db.flush()
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return CompanySettingsOut.model_validate(row)


@benefit_settings_router.get("/signatories", response_model=list[BenefitSignatoryOut])
async def list_signatories(db: DbSession, user: CurrentUser) -> list[BenefitSignatoryOut]:
    rows = (
        await db.execute(
            select(HrBenefitSignatory).order_by(HrBenefitSignatory.document_type.asc())
        )
    ).scalars().all()
    return [BenefitSignatoryOut.model_validate(r) for r in rows]


@benefit_settings_router.patch(
    "/signatories/{sig_id}", response_model=BenefitSignatoryOut
)
async def patch_signatory(
    sig_id: UUID, patch: BenefitSignatoryPatch, db: DbSession, user: CurrentUser
) -> BenefitSignatoryOut:
    row = (
        await db.execute(
            select(HrBenefitSignatory).where(HrBenefitSignatory.id == sig_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    for k, v in patch.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return BenefitSignatoryOut.model_validate(row)
