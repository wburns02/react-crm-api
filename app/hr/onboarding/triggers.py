"""Hire → onboarding spawn handler.

Called inline from `app.hr.recruiting.application_services.transition_stage`
when an application moves to the `hired` stage.  Uses the caller's session
so the hire + promotion + spawn land in the same transaction.

Also fires an advisory `hr.onboarding.spawned` event on the TriggerBus for
any downstream listeners (Plan 4 dashboard, future integrations).  Errors
in listeners never affect the hire flow.
"""
import logging
import secrets
import traceback
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.employees.models import HrOnboardingToken
from app.hr.recruiting.applicant_models import HrApplicant
from app.hr.recruiting.models import HrRequisition
from app.hr.shared.audit import write_audit
from app.hr.workflow.engine import spawn_instance
from app.hr.workflow.models import HrWorkflowTemplate
from app.hr.workflow.triggers import trigger_bus
from app.models.technician import Technician


logger = logging.getLogger(__name__)


async def _promote_applicant_to_technician(
    db: AsyncSession, applicant: HrApplicant
) -> Technician:
    """Return an existing Technician keyed by applicant.email, or create one."""
    row = (
        await db.execute(
            select(Technician).where(Technician.email == applicant.email)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    tech = Technician(
        first_name=applicant.first_name,
        last_name=applicant.last_name,
        email=applicant.email,
        phone=applicant.phone,
        is_active=True,
    )
    db.add(tech)
    await db.flush()
    return tech


async def _find_onboarding_template(
    db: AsyncSession, *, preferred_id: UUID | None = None
) -> HrWorkflowTemplate | None:
    if preferred_id is not None:
        row = (
            await db.execute(
                select(HrWorkflowTemplate).where(HrWorkflowTemplate.id == preferred_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    return (
        await db.execute(
            select(HrWorkflowTemplate).where(
                HrWorkflowTemplate.name == "New Field Tech Onboarding",
                HrWorkflowTemplate.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def spawn_onboarding_for_hire(
    db: AsyncSession,
    *,
    application_id: UUID,
    applicant_id: UUID,
    requisition_id: UUID,
    actor_user_id: int | None,
) -> dict | None:
    """Promote applicant → spawn onboarding instance → issue public token.

    Returns the payload of created ids on success, None on missing data.
    Never raises — failures are logged; the hire transaction already succeeded.
    """
    try:
        applicant = (
            await db.execute(
                select(HrApplicant).where(HrApplicant.id == applicant_id)
            )
        ).scalar_one_or_none()
        requisition = (
            await db.execute(
                select(HrRequisition).where(HrRequisition.id == requisition_id)
            )
        ).scalar_one_or_none()
        if applicant is None or requisition is None:
            logger.warning(
                "hr.applicant.hired — applicant or requisition missing "
                "(application=%s)",
                application_id,
            )
            return None

        technician = await _promote_applicant_to_technician(db, applicant)

        template = await _find_onboarding_template(
            db, preferred_id=requisition.onboarding_template_id
        )
        if template is None:
            logger.warning(
                "hr.applicant.hired — no onboarding template available "
                "(requisition=%s)",
                requisition_id,
            )
            return None

        instance = await spawn_instance(
            db,
            template_id=template.id,
            subject_type="employee",
            subject_id=technician.id,
            started_by=actor_user_id,
        )

        token_row = HrOnboardingToken(
            instance_id=instance.id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        db.add(token_row)
        await db.flush()

        await write_audit(
            db,
            entity_type="application",
            entity_id=application_id,
            event="onboarding_spawned",
            diff={
                "technician_id": [None, str(technician.id)],
                "instance_id": [None, str(instance.id)],
                "token": [None, token_row.token],
            },
            actor_user_id=actor_user_id,
        )

        payload = {
            "technician_id": str(technician.id),
            "instance_id": str(instance.id),
            "token": token_row.token,
        }
        try:
            await trigger_bus.fire("hr.onboarding.spawned", payload)
        except Exception as e:  # noqa: BLE001
            logger.error("hr.onboarding.spawned bus fire failed: %s", e)

        logger.info(
            "hr.applicant.hired — spawned onboarding instance %s "
            "for technician %s",
            instance.id,
            technician.id,
        )
        return payload
    except Exception as e:  # noqa: BLE001
        logger.exception("spawn_onboarding_for_hire failed: %s", e)
        traceback.print_exc()
        return None
