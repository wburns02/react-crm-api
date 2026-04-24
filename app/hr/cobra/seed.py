"""Seed COBRA demo rows: enrollments across buckets + payments + notices +
settings + pre-Rippling plans."""
from __future__ import annotations

from datetime import date, timedelta, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.cobra.models import (
    HrCobraEnrollment,
    HrCobraNotice,
    HrCobraPayment,
    HrCobraPreRipplingPlan,
    HrCobraSettings,
)


async def seed_cobra_demo(db: AsyncSession) -> dict:
    existing = (
        await db.execute(select(HrCobraEnrollment).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return {"seeded": False, "reason": "cobra already seeded"}

    today = date.today()

    current_rows = [
        ("Kristen Cruz", "Terminated", "Kristen Cruz", "pending_election", "Termination", today - timedelta(days=22), today + timedelta(days=520)),
        ("Dennis Ingram", None, "Kyle Bauer", "pending_election", "Loss of dependent child status", today - timedelta(days=24), today + timedelta(days=690)),
        ("Cassandra Oliver", None, "Gavin Friedman", "enrolled", "Loss of dependent child status", today - timedelta(days=24), today + timedelta(days=690)),
        ("Shane Thomas", "Terminated", "Shane Thomas", "pending_election", "Termination", today - timedelta(days=50), today + timedelta(days=500)),
    ]
    upcoming_rows = [
        ("Joshua Greer", "Terminated", "Joshua Greer", "pending_onboarding", "Termination", today + timedelta(days=30), today + timedelta(days=810)),
        ("Darren Holden", "Terminated", "Darren Holden", "enrolled", "Termination", today + timedelta(days=30), today + timedelta(days=810)),
        ("Jessica Johnson", "Terminated", "Jessica Johnson", "enrolled", "Termination", today + timedelta(days=30), today + timedelta(days=810)),
        ("Eric Lee", None, "Lisa Davis", "pending_election", "Divorce or legal separation", today + timedelta(days=50), today + timedelta(days=1000)),
        ("Ethan Maxwell", "Terminated", "Ethan Maxwell", "enrolled", "Termination", today + timedelta(days=30), today + timedelta(days=810)),
        ("Lisa Mcdowell", None, "Lisa Mcdowell", "pending_election", "Termination", today + timedelta(days=50), today + timedelta(days=950)),
    ]

    enrollments: list[HrCobraEnrollment] = []
    for name, label, bene, status, qe, elig, exh in current_rows:
        e = HrCobraEnrollment(
            employee_name=name,
            employee_label=label,
            beneficiary_name=bene,
            status=status,
            qualifying_event=qe,
            eligibility_date=elig,
            exhaustion_date=exh,
            bucket="current",
        )
        db.add(e)
        enrollments.append(e)
    for name, label, bene, status, qe, elig, exh in upcoming_rows:
        e = HrCobraEnrollment(
            employee_name=name,
            employee_label=label,
            beneficiary_name=bene,
            status=status,
            qualifying_event=qe,
            eligibility_date=elig,
            exhaustion_date=exh,
            bucket="upcoming",
        )
        db.add(e)
        enrollments.append(e)
    await db.flush()

    # Notices — one election notice per pending-election row
    notices_created = 0
    for e in enrollments:
        if e.status == "pending_election":
            db.add(
                HrCobraNotice(
                    enrollment_id=e.id,
                    employee_name=e.employee_name,
                    beneficiary_name=e.beneficiary_name,
                    type_of_notice="COBRA Election Notice",
                    addressed_to=e.beneficiary_name,
                    notice_url=f"https://example.com/notices/{e.id}.pdf",
                    tracking_status="In Production",
                    updated_on=today,
                )
            )
            notices_created += 1

    # Payments — a couple of months for Cassandra Oliver + Darren Holden (enrolled)
    enrolled = [e for e in enrollments if e.status == "enrolled"]
    payments_created = 0
    for e in enrolled[:4]:
        for m_offset in range(0, 3):
            month_date = (today.replace(day=1) - timedelta(days=30 * m_offset)).replace(day=1)
            db.add(
                HrCobraPayment(
                    enrollment_id=e.id,
                    employee_name=e.employee_name,
                    beneficiary_name=e.beneficiary_name,
                    month=month_date.strftime("%Y-%m"),
                    employee_charge_date=month_date + timedelta(days=3),
                    charged_amount=Decimal("620.00"),
                    company_reimbursement_date=month_date + timedelta(days=18),
                    reimbursement_amount=Decimal("620.00"),
                    status="paid" if m_offset > 0 else "pending",
                )
            )
            payments_created += 1

    # Settings
    db.add(
        HrCobraSettings(
            payment_method_label="ABC Inc. ****7890",
            bank_last4="7890",
            country_code="US",
            grace_period_days=30,
            election_window_days=60,
            send_election_notices_automatically=True,
        )
    )

    # Pre-Rippling plans
    db.add(HrCobraPreRipplingPlan(
        carrier="Aetna", plan_name="HMO Select (Legacy)", plan_kind="medical",
        monthly_premium=Decimal("520.00"),
        effective_from=date(2023, 1, 1), effective_to=date(2024, 12, 31),
        is_active=False,
    ))
    db.add(HrCobraPreRipplingPlan(
        carrier="Delta Dental", plan_name="PPO Premier (Legacy)", plan_kind="dental",
        monthly_premium=Decimal("48.00"),
        effective_from=date(2023, 1, 1), effective_to=date(2024, 12, 31),
        is_active=False,
    ))

    await db.commit()
    return {
        "seeded": True,
        "enrollments": len(enrollments),
        "notices": notices_created,
        "payments": payments_created,
        "pre_plans": 2,
    }
