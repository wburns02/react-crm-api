"""Candidate SMS on application stage change.

Silently no-ops when:
- no phone on the applicant,
- no SMS consent captured at apply time,
- no active template exists for the target stage,
- outbound SMS raises (logged, event recorded with status=error).

Tests monkeypatch ``_send_sms`` to assert on the payload without touching
the upstream Twilio client in ``app.services.sms_service``.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
    HrRecruitingMessageTemplate,
)
from app.hr.recruiting.models import HrRequisition


logger = logging.getLogger(__name__)

_COMPANY_NAME = "Mac Septic"


async def _send_sms(to: str, body: str) -> None:
    """Thin wrapper so tests can monkeypatch this without touching the upstream
    ``app.services.sms_service`` module."""
    from app.services.sms_service import send_sms

    await send_sms(to, body)


async def maybe_send_stage_sms(
    db: AsyncSession,
    *,
    application_id: UUID,
    new_stage: str,
) -> None:
    application = (
        await db.execute(select(HrApplication).where(HrApplication.id == application_id))
    ).scalar_one_or_none()
    if application is None:
        return

    applicant = (
        await db.execute(
            select(HrApplicant).where(HrApplicant.id == application.applicant_id)
        )
    ).scalar_one()
    if not applicant.phone or not applicant.sms_consent_given:
        return

    template = (
        await db.execute(
            select(HrRecruitingMessageTemplate).where(
                HrRecruitingMessageTemplate.stage == new_stage,
                HrRecruitingMessageTemplate.active.is_(True),
                HrRecruitingMessageTemplate.channel == "sms",
            )
        )
    ).scalar_one_or_none()
    if template is None:
        return

    requisition = (
        await db.execute(
            select(HrRequisition).where(HrRequisition.id == application.requisition_id)
        )
    ).scalar_one()

    try:
        body = template.body.format(
            first_name=applicant.first_name,
            last_name=applicant.last_name,
            requisition_title=requisition.title,
            company_name=_COMPANY_NAME,
        )
    except KeyError as e:
        logger.warning("hr sms template missing key %s for stage %s", e, new_stage)
        return

    status = "ok"
    try:
        await _send_sms(applicant.phone, body)
    except Exception as e:  # noqa: BLE001 - SMS failure must never bubble
        logger.error("hr sms send failed: %s", e)
        status = "error"

    db.add(
        HrApplicationEvent(
            application_id=application.id,
            event_type="message_sent",
            payload={
                "stage": new_stage,
                "channel": "sms",
                "status": status,
                "to": applicant.phone,
            },
        )
    )
    await db.flush()
