"""Seed demo benefits data so the Benefits section has content on first load.

Idempotent: if any enrollment row already exists we no-op.  Uses a small
hand-curated list of Mac Septic / H-Man Electrical employees mixed with
realistic Blue Shield / Guardian / MetLife plan structures.  This is NOT
a live Rippling sync — it mocks enough rows to drive the UI.  Swap for a
real Rippling client when credentials land.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.benefits.models import (
    HrBenefitEnrollment,
    HrBenefitEoiRequest,
    HrBenefitEvent,
    HrBenefitHistory,
    HrBenefitPlan,
)


_PLANS = [
    ("medical", "Blue Shield", "Platinum Full PPO 250/15", 620, 620 * 0.55, 620 * 0.45),
    ("medical", "Blue Shield", "Gold Full PPO 500/20", 540, 540 * 0.55, 540 * 0.45),
    ("medical", "Blue Shield", "Silver Full PPO 1750/35", 440, 440 * 0.55, 440 * 0.45),
    ("medical", "Blue Shield", "Bronze Full PPO Savings 4300/40%", 360, 360 * 0.55, 360 * 0.45),
    ("dental", "Guardian", "DentalGuard Preferred High", 58, 58 * 0.5, 58 * 0.5),
    ("dental", "Guardian", "DentalGuard Preferred Low", 40, 40 * 0.5, 40 * 0.5),
    ("vision", "VSP", "VSP Vision Choice", 18, 18, 0),
    ("life", "MetLife", "MetLife Basic Life AD&D", 12, 0, 12),
    ("life", "MetLife", "MetLife Voluntary Life", 35, 35, 0),
    ("fsa", "WageWorks", "Healthcare FSA", 0, 0, 0),
    ("hsa", "HealthEquity", "HealthEquity HSA", 0, 0, 0),
    ("std", "MetLife", "Short Term Disability", 22, 0, 22),
    ("ltd", "MetLife", "Long Term Disability", 28, 0, 28),
]


_EMPLOYEES = [
    ("Adam Rodriguez", "Database Manager, Marketing"),
    ("Amanda Garcia", "Customer Support Associate, Support"),
    ("Cassandra Oliver", "Account Executive, Enterprise"),
    ("Christopher Webster", "Controller, Finance"),
    ("Colleen Kelley", "VP Marketing, Marketing"),
    ("Cynthia Nunez", "HR Generalist, People"),
    ("Daniel Melendez", "VP Sales, Sales"),
    ("Dennis Ingram", "Solutions Architect, Engineering"),
    ("Donna Walker", "Customer Success Manager, CS"),
    ("Edgar Rodriguez", "Marketo Manager, Marketing"),
    ("Edward Moore", "Sales Development Rep, SMB"),
    ("Elizabeth Hill", "Account Executive, Enterprise"),
    ("Eric Lee", "Field Technician, Operations"),
    ("Jane Aguirre", "Implementation Manager, CS"),
    ("Jessica Myers", "HR Director, Finance"),
    ("Kathryn Williams", "Accounts Payable, Finance"),
    ("Kristen Cruz", "Dispatcher, Operations"),
    ("Lisa Mcdowell", "Office Manager, Operations"),
    ("Shane Thomas", "Lead Technician, Operations"),
    ("Matt Carter", "President, Executive"),
    ("Doug Carter", "EVP, Executive"),
    ("Marvin Carter", "Founder / SME, Executive"),
    ("Natalie Hustek", "Chief of Staff, Executive"),
    ("Will Burns", "San Marcos Office, Operations"),
    ("Ronnie Ransom", "San Marcos VTO, Operations"),
    ("Chandler Turney", "Columbia VTO, Operations"),
    ("John Harvey", "Nashville VTO, Operations"),
    ("Wade DeLoach", "Electrical Service Tech, SC Midlands"),
    ("Danny Smith", "Technical Reference / SME, Rock Hill"),
]


_CHANGE_TYPES = [
    "COBRA Initial Enrollment",
    "Qualifying Life Event",
    "Qualifying Life Event",
    "Termination/Loss of Benefits Eligibility",
    "COBRA Qualifying Life Event",
]


_EVENT_TYPES = [
    ("Demographic Change", "pending"),
    ("New Hire", "pending"),
    ("Termination", "completed"),
    ("COBRA Enrollment", "pending"),
    ("Qualified Life Event (QLE)", "completed"),
]


async def seed_benefits_demo(db: AsyncSession) -> dict:
    """Populate demo rows.  No-ops if enrollments already exist."""
    existing = (
        await db.execute(select(HrBenefitEnrollment).limit(1))
    ).scalar_one_or_none()
    if existing is not None:
        return {"seeded": False, "reason": "enrollments already present"}

    # Plans
    plans: dict[tuple[str, str], HrBenefitPlan] = {}
    for kind, carrier, name, cost, ee, er in _PLANS:
        p = HrBenefitPlan(
            kind=kind,
            carrier=carrier,
            name=name,
            monthly_cost=Decimal(str(round(cost, 2))),
            employee_contribution=Decimal(str(round(ee, 2))),
            employer_contribution=Decimal(str(round(er, 2))),
        )
        db.add(p)
        plans[(kind, name)] = p
    await db.flush()

    # Enrollments — medical for most, dental + vision for ~half, life for a
    # few executives, waived for one or two for variety.
    today = date.today()
    enrollments_created = 0
    for idx, (name, title) in enumerate(_EMPLOYEES):
        # Medical
        if idx % 9 == 3:
            db.add(
                HrBenefitEnrollment(
                    employee_name=name,
                    employee_title=title,
                    plan_name="Waived",
                    carrier=None,
                    benefit_type="medical",
                    status="waived",
                    effective_date=today.replace(month=1, day=1),
                    monthly_cost=Decimal("0"),
                    monthly_deduction=Decimal("0"),
                )
            )
        else:
            med_plan = list(plans.values())[idx % 4]
            db.add(
                HrBenefitEnrollment(
                    employee_name=name,
                    employee_title=title,
                    plan_id=med_plan.id,
                    plan_name=med_plan.name,
                    carrier=med_plan.carrier,
                    benefit_type="medical",
                    status="active",
                    effective_date=today.replace(month=1, day=1) - timedelta(days=(idx * 7) % 45),
                    monthly_cost=med_plan.monthly_cost,
                    monthly_deduction=med_plan.employee_contribution,
                )
            )
        enrollments_created += 1

        # Dental for every other
        if idx % 2 == 0:
            d_plan = plans.get(("dental", "DentalGuard Preferred High"))
            if d_plan:
                db.add(
                    HrBenefitEnrollment(
                        employee_name=name,
                        employee_title=title,
                        plan_id=d_plan.id,
                        plan_name=d_plan.name,
                        carrier=d_plan.carrier,
                        benefit_type="dental",
                        status="active",
                        effective_date=today.replace(month=1, day=1),
                        monthly_cost=d_plan.monthly_cost,
                        monthly_deduction=d_plan.employee_contribution,
                    )
                )
                enrollments_created += 1

        # Vision for every third
        if idx % 3 == 0:
            v_plan = plans.get(("vision", "VSP Vision Choice"))
            if v_plan:
                db.add(
                    HrBenefitEnrollment(
                        employee_name=name,
                        employee_title=title,
                        plan_id=v_plan.id,
                        plan_name=v_plan.name,
                        carrier=v_plan.carrier,
                        benefit_type="vision",
                        status="active",
                        effective_date=today.replace(month=1, day=1),
                        monthly_cost=v_plan.monthly_cost,
                        monthly_deduction=v_plan.employee_contribution,
                    )
                )
                enrollments_created += 1

    # Upcoming events — 12 across mixed statuses
    events_created = 0
    for i, (name, title) in enumerate(_EMPLOYEES[:14]):
        evt_type, evt_status = _EVENT_TYPES[i % len(_EVENT_TYPES)]
        eff = today + timedelta(days=((i * 3) % 20) - 5)
        comp = eff - timedelta(days=7) if evt_status == "completed" else None
        db.add(
            HrBenefitEvent(
                employee_name=name,
                employee_title=title,
                event_type=evt_type,
                status=evt_status,
                effective_date=eff,
                completion_date=comp,
            )
        )
        events_created += 1

    # Enrollment history — 12 rows
    history_created = 0
    for i, (name, title) in enumerate(_EMPLOYEES[:12]):
        change = _CHANGE_TYPES[i % len(_CHANGE_TYPES)]
        completed = today - timedelta(days=(i * 2) % 25)
        effective = completed + timedelta(days=(i * 3) % 18)
        db.add(
            HrBenefitHistory(
                employee_name=name,
                change_type=change,
                affected_lines=1 + (i % 5) * 3,
                completed_date=completed,
                effective_date=effective,
                changed_by=None,
                is_terminated=change.startswith("Termination")
                or change.startswith("COBRA Qualifying"),
            )
        )
        history_created += 1

    # EOI requests — 3 pending, 2 approved (for the Rippling-style status mix)
    eoi_created = 0
    voluntary_life = plans.get(("life", "MetLife Voluntary Life"))
    ltd = plans.get(("ltd", "Long Term Disability"))
    eoi_rows = [
        ("Cassandra Oliver", "Cassandra Oliver", "employee", "life", voluntary_life, "pending"),
        ("Dennis Ingram", "Dennis Ingram", "employee", "life", voluntary_life, "pending"),
        ("Edward Moore", "Sarah Moore", "spouse", "life", voluntary_life, "pending"),
        ("Amanda Garcia", "Amanda Garcia", "employee", "ltd", ltd, "approved"),
        ("Colleen Kelley", "Colleen Kelley", "employee", "ltd", ltd, "approved"),
    ]
    for emp_name, member_name, member_type, benefit_type, plan, status in eoi_rows:
        if plan is None:
            continue
        db.add(
            HrBenefitEoiRequest(
                employee_name=emp_name,
                member_name=member_name,
                member_type=member_type,
                benefit_type=benefit_type,
                plan_name=plan.name,
                status=status,
                enrollment_created_at=today - timedelta(days=30),
                enrollment_ends_at=today + timedelta(days=335),
            )
        )
        eoi_created += 1

    await db.commit()
    return {
        "seeded": True,
        "plans": len(_PLANS),
        "enrollments": enrollments_created,
        "events": events_created,
        "history": history_created,
        "eoi": eoi_created,
    }
