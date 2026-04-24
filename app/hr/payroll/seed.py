"""Seed demo payroll data — pay runs across all 4 buckets + people status."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.payroll.models import HrPayrollPeopleStatus, HrPayRun


_SCHED = "Semi-monthly pay schedule for 000000000"
_ENT = "Entity - US"


async def seed_payroll_demo(db: AsyncSession) -> dict:
    existing = (await db.execute(select(HrPayRun).limit(1))).scalar_one_or_none()
    if existing is not None:
        return {"seeded": False, "reason": "payroll already seeded"}

    today = date.today()
    now = datetime.utcnow()

    # Upcoming (1 row needing approval, matching the action banner shape)
    db.add(HrPayRun(
        label="Apr 6th - Apr 20th: Entity - US",
        pay_schedule_name=_SCHED,
        entity=_ENT,
        pay_run_type="regular",
        pay_date=today + timedelta(days=5),
        approve_by=(now + timedelta(hours=7)).replace(microsecond=0),
        funding_method=None,
        status="upcoming",
        action_text="Run payroll",
        failure_reason=None,
    ))

    # Paid (2 rows)
    db.add_all([
        HrPayRun(
            label="Mar 21st - Apr 5th: Entity - US",
            pay_schedule_name=_SCHED,
            entity=_ENT,
            pay_run_type="regular",
            pay_date=today - timedelta(days=7),
            funding_method="ACH",
            status="paid",
            action_text="Make Changes",
        ),
        HrPayRun(
            label="Mar 6th - Mar 20th: Entity - US",
            pay_schedule_name=_SCHED,
            entity=_ENT,
            pay_run_type="regular",
            pay_date=today - timedelta(days=21),
            funding_method="ACH",
            status="paid",
            action_text="Make Changes",
        ),
    ])

    # Archived (3 rows)
    for offset, by in [(40, "Admin"), (55, "Emily Burgess"), (70, "Admin")]:
        db.add(HrPayRun(
            label=f"{(today - timedelta(days=offset + 14)).strftime('%b %d')} - {(today - timedelta(days=offset)).strftime('%b %d')}: Entity - US",
            pay_schedule_name=_SCHED,
            entity=_ENT,
            pay_run_type="regular",
            pay_date=today - timedelta(days=offset),
            funding_method="ACH",
            status="archived",
            action_text="Unarchive",
            archived_by=by,
        ))

    # People status — matching Rippling screenshot
    missing_people = [
        ("Will Burns", None, _SCHED, "missing_1", "missing_details", 1, "Direct deposit routing number", None),
        ("Donna Walker", None, _SCHED, "missing_4", "missing_details", 4, "SSN, DOB, address, direct deposit", None),
        ("Eric Lee", None, None, "missing_3", "missing_details", 3, "Pay schedule, SSN, address", None),
        ("Dennis Ingram", None, None, "missing_3", "missing_details", 3, "Pay schedule, SSN, bank info", None),
        ("Cynthia Nunez", None, None, "action_needed", "missing_details", 0, None, None),
        ("Cassandra Oliver", None, None, "action_needed", "missing_details", 0, None, None),
    ]
    for name, title, sched, status, bucket, crit, fields, sig in missing_people:
        db.add(HrPayrollPeopleStatus(
            employee_name=name, employee_title=title, pay_schedule=sched,
            status=status, bucket=bucket,
            critical_missing_count=crit, missing_fields=fields, signatory_status=sig,
        ))

    ready_people = [
        ("Emily Burgess", "CEO, Finance"),
        ("Mark Lindsey", "COO, Customer Support"),
        ("Peter Chambers", "CFO, Finance"),
        ("Lauren Phillips", "CTO, Engineering"),
        ("Kevin Gonzalez", "VP Engineering, Engineering"),
        ("Stephen Tran", "Director of Engineering Ops, Backend"),
        ("Tina Chang", "Software Engineer, Frontend"),
        ("Jacob Stuart", "Sr. Software Engineer, Infra"),
        ("Daniel Melendez", "VP Sales, Sales"),
        ("Elizabeth Hill", "Account Executive, Enterprise"),
        ("Adam Rodriguez", "Database Manager, Marketing"),
        ("Amanda Garcia", "Customer Support Associate, Support"),
        ("Colleen Kelley", "VP Marketing, Marketing"),
        ("Edgar Rodriguez", "Marketo Manager, Marketing"),
        ("Edward Moore", "Sales Development Rep, SMB"),
        ("Jane Aguirre", "Implementation Manager, CS"),
        ("Jessica Myers", "HR Director, Finance"),
        ("Kathryn Williams", "Accounts Payable, Finance"),
        ("Kristen Cruz", "Dispatcher, Operations"),
        ("Lisa Mcdowell", "Office Manager, Operations"),
        ("Shane Thomas", "Lead Technician, Operations"),
        ("Christopher Webster", "Controller, Finance"),
        ("Will Burns", "San Marcos Office, Operations"),
        ("Chandler Turney", "Columbia VTO, Operations"),
        ("John Harvey", "Nashville VTO, Operations"),
    ]
    for name, title in ready_people:
        db.add(HrPayrollPeopleStatus(
            employee_name=name, employee_title=title, pay_schedule=_SCHED,
            status="payroll_ready", bucket="payroll_ready",
            critical_missing_count=0, missing_fields=None, signatory_status=None,
        ))

    # Signatory status
    db.add(HrPayrollPeopleStatus(
        employee_name="Emily Burgess", employee_title="CEO, Finance", pay_schedule=None,
        status="action_needed", bucket="signatory",
        critical_missing_count=0, missing_fields=None, signatory_status="Action Needed",
    ))

    await db.commit()
    return {
        "seeded": True,
        "pay_runs": 6,
        "people_missing": len(missing_people),
        "people_ready": len(ready_people),
        "signatory": 1,
    }
