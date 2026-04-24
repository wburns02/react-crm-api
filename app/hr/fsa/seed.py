"""Seed demo FSA data: 3 plans, ~18 enrollments, ~40 transactions, 1 settings
row, 4 documents, 4 compliance tests, 2 exclusions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.fsa.models import (
    HrFsaComplianceTest,
    HrFsaDocument,
    HrFsaEnrollment,
    HrFsaExclusion,
    HrFsaPlan,
    HrFsaSettings,
    HrFsaTransaction,
)


_EMPLOYEES = [
    "Adam Rodriguez", "Amanda Garcia", "Cassandra Oliver", "Christopher Webster",
    "Colleen Kelley", "Cynthia Nunez", "Daniel Melendez", "Dennis Ingram",
    "Donna Walker", "Edgar Rodriguez", "Edward Moore", "Elizabeth Hill",
    "Eric Lee", "Jane Aguirre", "Jessica Myers", "Kathryn Williams",
    "Kristen Cruz", "Lisa Mcdowell", "Shane Thomas",
]


_MERCHANTS = [
    ("CVS Pharmacy #12408", "Rx / OTC"),
    ("Walgreens #7152", "Rx / OTC"),
    ("LabCorp", "Medical labs"),
    ("Quest Diagnostics", "Medical labs"),
    ("Austin Family Dental", "Dental"),
    ("LensCrafters", "Vision"),
    ("Target Pharmacy", "Rx / OTC"),
    ("Baby's Grove Daycare", "Dependent care"),
    ("Little Learners Academy", "Dependent care"),
    ("Austin Regional Clinic", "Office visit"),
    ("Amazon Pharmacy", "Rx / OTC"),
    ("Walmart Health Center", "Office visit"),
    ("Dermatology Associates", "Office visit"),
    ("PharmaCare Compounding", "Rx / OTC"),
    ("Physical Therapy Partners", "PT / Chiro"),
]


async def seed_fsa_demo(db: AsyncSession) -> dict:
    existing = (await db.execute(select(HrFsaPlan).limit(1))).scalar_one_or_none()
    if existing is not None:
        return {"seeded": False, "reason": "fsa plans already present"}

    today = date.today()
    year_start = today.replace(month=1, day=1)
    year_end = today.replace(month=12, day=31)

    # Plans
    plans_data = [
        ("healthcare", "Healthcare FSA", Decimal("3300"), None, False, 0, True, Decimal("660")),
        ("dependent_care", "Dependent Care FSA", Decimal("5000"), Decimal("5000"), True, 2, False, None),
        ("limited_purpose", "Limited Purpose FSA", Decimal("3300"), None, False, 0, True, Decimal("660")),
    ]
    plan_rows: dict[str, HrFsaPlan] = {}
    for kind, name, emp, fam, grace_on, grace_m, ro_on, ro_max in plans_data:
        p = HrFsaPlan(
            kind=kind,
            name=name,
            annual_limit_employee=emp,
            annual_limit_family=fam,
            plan_year_start=year_start,
            plan_year_end=year_end,
            grace_period_enabled=grace_on,
            grace_period_months=grace_m,
            rollover_enabled=ro_on,
            rollover_max=ro_max,
            runout_days=90,
        )
        db.add(p)
        plan_rows[kind] = p
    await db.flush()

    # Enrollments — mix of active / pending / declined across 3 plan kinds
    statuses = ["active"] * 11 + ["pending"] * 4 + ["declined"] * 3
    plan_kinds = ["healthcare", "healthcare", "healthcare", "dependent_care",
                  "dependent_care", "limited_purpose"] * 4
    rnd = random.Random(42)
    enroll_count = 0
    for idx, emp in enumerate(_EMPLOYEES):
        kind = plan_kinds[idx % len(plan_kinds)]
        status = statuses[idx % len(statuses)]
        plan = plan_rows[kind]
        election = Decimal(
            rnd.choice([1200, 1800, 2400, 2500, 3000, 3300]) if kind != "dependent_care"
            else rnd.choice([2000, 3500, 5000])
        )
        ytd_contrib = (
            election * Decimal("0.35") if status == "active" else Decimal("0")
        )
        ytd_spent = (
            ytd_contrib * Decimal(str(rnd.uniform(0.15, 0.9)))
            if status == "active" else Decimal("0")
        )
        db.add(
            HrFsaEnrollment(
                employee_name=emp,
                plan_id=plan.id,
                plan_kind=kind,
                annual_election=election,
                ytd_contributed=ytd_contrib.quantize(Decimal("0.01")),
                ytd_spent=ytd_spent.quantize(Decimal("0.01")),
                status=status,
                enrolled_at=year_start + timedelta(days=rnd.randint(0, 30)),
            )
        )
        enroll_count += 1

    # Transactions — ~40 rows
    tx_count = 0
    tx_statuses = ["approved"] * 18 + ["pending"] * 6 + ["substantiation_required"] * 4 + ["denied"] * 2
    tx_kinds = ["card_swipe"] * 22 + ["reimbursement"] * 8
    for i in range(40):
        emp = rnd.choice(_EMPLOYEES)
        merch, cat = rnd.choice(_MERCHANTS)
        plan_kind = "dependent_care" if "daycare" in merch.lower() or "academy" in merch.lower() else "healthcare"
        amt = Decimal(str(round(rnd.uniform(18, 380), 2)))
        status = rnd.choice(tx_statuses)
        kind = rnd.choice(tx_kinds)
        tx_date = today - timedelta(days=rnd.randint(0, 85))
        db.add(
            HrFsaTransaction(
                employee_name=emp,
                plan_kind=plan_kind,
                transaction_date=tx_date,
                merchant=merch,
                category=cat,
                amount=amt,
                kind=kind,
                status=status,
                notes=(
                    "Receipt needed — please upload substantiation."
                    if status == "substantiation_required" else None
                ),
            )
        )
        tx_count += 1

    # Settings
    db.add(
        HrFsaSettings(
            bank_name="Pacific Western Bank",
            bank_account_last4="4472",
            bank_routing_last4="9081",
            bank_account_type="checking",
            eligibility_waiting_days=30,
            eligibility_min_hours=30,
            eligibility_rule="Employees classified as full-time (>=30 hrs/wk) after 30-day waiting period.",
            debit_card_enabled=True,
            auto_substantiation_enabled=True,
        )
    )

    # Documents
    for title, kind_ in [
        ("Summary Plan Description (SPD) — Healthcare FSA", "spd"),
        ("Plan Document — Healthcare FSA 2026", "plan_document"),
        ("Dependent Care FSA Eligibility Notice", "notice"),
        ("FSA Amendment #2 — Rollover Increase", "amendment"),
    ]:
        db.add(HrFsaDocument(title=title, kind=kind_, description=title, url="https://example.com/fsa.pdf"))

    # Compliance tests — current year, all passed
    for tk in [
        "eligibility",
        "benefits_contributions",
        "key_employee_concentration",
        "55_percent_average_benefits",
    ]:
        db.add(
            HrFsaComplianceTest(
                test_kind=tk,
                plan_year=today.year,
                status="passed",
                highly_compensated_count=3,
                non_highly_compensated_count=16,
            )
        )

    # Exclusions — 2 examples
    db.add(
        HrFsaExclusion(
            employee_name="Shane Thomas",
            reason="Terminated — no longer eligible",
            excluded_from="all",
        )
    )
    db.add(
        HrFsaExclusion(
            employee_name="Kristen Cruz",
            reason="Union-negotiated coverage under separate plan",
            excluded_from="healthcare",
        )
    )

    await db.commit()
    return {
        "seeded": True,
        "plans": 3,
        "enrollments": enroll_count,
        "transactions": tx_count,
        "documents": 4,
        "compliance_tests": 4,
        "exclusions": 2,
    }
