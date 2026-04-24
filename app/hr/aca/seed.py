"""Seed ACA + benefit-settings demo rows."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.aca.models import (
    HrAcaEmployeeHours,
    HrAcaFiling,
    HrAcaLookbackPolicy,
    HrBenefitCompanySettings,
    HrBenefitSignatory,
)


async def seed_aca_and_settings(db: AsyncSession) -> dict:
    existing = (
        await db.execute(select(HrAcaFiling).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return {"seeded": False, "reason": "aca already seeded"}

    # Filings — 2024 filed, 2025 current, 2026 future
    db.add_all([
        HrAcaFiling(
            plan_year=2024,
            form_1094c_status="filed",
            form_1095c_count=42,
            irs_deadline=date(2025, 3, 31),
            employee_deadline=date(2025, 3, 2),
            filed_at=None,
            is_current=False,
            notes="Filed successfully. Final acknowledgement received.",
        ),
        HrAcaFiling(
            plan_year=2025,
            form_1094c_status="filed",
            form_1095c_count=46,
            irs_deadline=date(2026, 3, 31),
            employee_deadline=date(2026, 3, 2),
            is_current=True,
            notes=(
                "ACA filing season for the year 2025 is now over, and the "
                "period for any corrections has ended."
            ),
        ),
        HrAcaFiling(
            plan_year=2026,
            form_1094c_status="not_started",
            form_1095c_count=0,
            irs_deadline=date(2027, 3, 31),
            employee_deadline=date(2027, 3, 2),
            is_current=False,
            notes="Rippling will reach out toward the end of the year to help with 2026 filings.",
        ),
    ])

    # Lookback policy (not yet defined → is_active=False)
    db.add(HrAcaLookbackPolicy(is_active=False))

    # Employee hours sample (9 rows)
    sample = [
        ("Will Burns", "2025-11-04 → 2026-11-03", 2080, 40.0, True),
        ("Chandler Turney", "2025-11-04 → 2026-11-03", 2028, 39.0, True),
        ("John Harvey", "2025-11-04 → 2026-11-03", 2080, 40.0, True),
        ("Ronnie Ransom", "2025-11-04 → 2026-11-03", 1820, 35.0, True),
        ("Wade DeLoach", "2025-11-04 → 2026-11-03", 1560, 30.0, True),
        ("Danny Smith", "2025-11-04 → 2026-11-03", 1456, 28.0, False),
        ("Kristen Cruz", "2025-11-04 → 2026-11-03", 1040, 20.0, False),
        ("Shane Thomas", "2025-11-04 → 2026-11-03", 624, 12.0, False),
        ("Eric Lee", "2025-11-04 → 2026-11-03", 2184, 42.0, True),
    ]
    for name, period, hours, avg, eligible in sample:
        db.add(
            HrAcaEmployeeHours(
                employee_name=name,
                measurement_period=period,
                total_hours=Decimal(str(hours)),
                average_hours_per_week=Decimal(str(avg)),
                is_full_time_eligible=eligible,
            )
        )

    # Signatories (matches Rippling screenshot layout)
    db.add_all([
        HrBenefitSignatory(
            document_type="Summary plan description",
            signatory_name=None,
            signatory_department=None,
            status="signature_missing",
        ),
        HrBenefitSignatory(
            document_type="Premium only plan",
            signatory_name="Emily Burgess",
            signatory_department="Finance",
            status="signature_pending",
        ),
        HrBenefitSignatory(
            document_type="Employee Benefits Termination form",
            signatory_name="The person who terminated the employee",
            signatory_department=None,
            status="configured",
        ),
        HrBenefitSignatory(
            document_type="Open enrollment notice document",
            signatory_name=None,
            signatory_department=None,
            status="signature_missing",
        ),
    ])

    # Singleton company settings
    db.add(HrBenefitCompanySettings(
        class_codes="Class 1 — Full-time salaried · Class 2 — Full-time hourly · Class 3 — Part-time",
        benefit_admin_notification_user="Emily Burgess",
    ))

    await db.commit()
    return {
        "seeded": True,
        "filings": 3,
        "lookback_policy": 1,
        "employee_hours": len(sample),
        "signatories": 4,
        "company_settings": 1,
    }
