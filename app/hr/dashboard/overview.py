"""HR module overview aggregator.

Single async function that assembles the dashboard KPIs in one round-trip.
All queries are read-only; safe to call from an authed admin endpoint.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.employees.models import HrEmployeeCertification
from app.hr.recruiting.applicant_models import HrApplicant, HrApplication
from app.hr.recruiting.models import HrRequisition
from app.hr.workflow.models import (
    HrWorkflowInstance,
    HrWorkflowTask,
    HrWorkflowTemplate,
)


async def build_overview(db: AsyncSession) -> dict:
    today = date.today()
    week_ago = datetime.utcnow() - timedelta(days=7)

    open_requisitions = (
        await db.execute(
            select(func.count(HrRequisition.id)).where(
                HrRequisition.status == "open"
            )
        )
    ).scalar_one() or 0

    applicants_last_7d = (
        await db.execute(
            select(func.count(HrApplicant.id)).where(
                HrApplicant.created_at >= week_ago
            )
        )
    ).scalar_one() or 0

    # Active onboardings — instance status=active AND template.category=onboarding.
    active_onboardings = (
        await db.execute(
            select(func.count(HrWorkflowInstance.id))
            .join(
                HrWorkflowTemplate,
                HrWorkflowInstance.template_id == HrWorkflowTemplate.id,
            )
            .where(
                HrWorkflowInstance.status == "active",
                HrWorkflowTemplate.category == "onboarding",
            )
        )
    ).scalar_one() or 0

    active_offboardings = (
        await db.execute(
            select(func.count(HrWorkflowInstance.id))
            .join(
                HrWorkflowTemplate,
                HrWorkflowInstance.template_id == HrWorkflowTemplate.id,
            )
            .where(
                HrWorkflowInstance.status == "active",
                HrWorkflowTemplate.category == "offboarding",
            )
        )
    ).scalar_one() or 0

    expiring_certs_30d = (
        await db.execute(
            select(func.count(HrEmployeeCertification.id)).where(
                HrEmployeeCertification.expires_at.is_not(None),
                HrEmployeeCertification.expires_at <= today + timedelta(days=30),
                HrEmployeeCertification.expires_at >= today,
                HrEmployeeCertification.status == "active",
            )
        )
    ).scalar_one() or 0

    # Pending HR-role tasks — first 20.
    pending_tasks = (
        await db.execute(
            select(HrWorkflowTask)
            .where(
                HrWorkflowTask.status.in_(["ready", "in_progress"]),
                HrWorkflowTask.assignee_role == "hr",
            )
            .order_by(HrWorkflowTask.due_at.asc().nullslast())
            .limit(20)
        )
    ).scalars().all()

    active_applications_by_stage: dict[str, int] = {}
    rows = (
        await db.execute(
            select(HrApplication.stage, func.count(HrApplication.id))
            .where(HrApplication.stage.notin_(["rejected", "withdrawn", "hired"]))
            .group_by(HrApplication.stage)
        )
    ).all()
    for stage, count in rows:
        active_applications_by_stage[stage] = count

    return {
        "open_requisitions": open_requisitions,
        "applicants_last_7d": applicants_last_7d,
        "active_onboardings": active_onboardings,
        "active_offboardings": active_offboardings,
        "expiring_certs_30d": expiring_certs_30d,
        "active_applications_by_stage": active_applications_by_stage,
        "pending_hr_tasks": [
            {
                "id": str(t.id),
                "name": t.name,
                "instance_id": str(t.instance_id),
                "due_at": t.due_at.isoformat() if t.due_at else None,
                "status": t.status,
            }
            for t in pending_tasks
        ],
    }
