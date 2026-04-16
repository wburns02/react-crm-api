from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.recruiting.applicant_models import HrApplication, HrApplicationEvent
from app.hr.recruiting.applicant_schemas import ApplicationIn
from app.hr.shared.audit import write_audit
from app.hr.workflow.triggers import trigger_bus


class ApplicationStateError(Exception):
    pass


TERMINAL = {"hired", "rejected", "withdrawn"}

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "applied": {"screen", "rejected", "withdrawn"},
    "screen": {"ride_along", "rejected", "withdrawn"},
    "ride_along": {"offer", "rejected", "withdrawn"},
    "offer": {"hired", "rejected", "withdrawn"},
    "hired": set(),
    "rejected": set(),
    "withdrawn": set(),
}


async def create_application(
    db: AsyncSession,
    payload: ApplicationIn,
    *,
    actor_user_id: int | None,
) -> HrApplication:
    row = HrApplication(
        applicant_id=UUID(payload.applicant_id),
        requisition_id=UUID(payload.requisition_id),
        stage=payload.stage,
        assigned_recruiter_id=payload.assigned_recruiter_id,
        notes=payload.notes,
        answers=payload.answers,
    )
    db.add(row)
    await db.flush()
    db.add(
        HrApplicationEvent(
            application_id=row.id,
            event_type="created",
            user_id=actor_user_id,
            payload={"stage": row.stage},
        )
    )
    await write_audit(
        db,
        entity_type="application",
        entity_id=row.id,
        event="created",
        diff={"stage": [None, row.stage]},
        actor_user_id=actor_user_id,
    )
    return row


async def transition_stage(
    db: AsyncSession,
    *,
    application_id: UUID,
    new_stage: str,
    actor_user_id: int | None,
    reason: str | None = None,
    note: str | None = None,
) -> HrApplication:
    row = (
        await db.execute(
            select(HrApplication)
            .where(HrApplication.id == application_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApplicationStateError(f"application {application_id} not found")

    if new_stage not in _ALLOWED_TRANSITIONS[row.stage]:
        raise ApplicationStateError(
            f"cannot transition from {row.stage} to {new_stage}"
        )
    if new_stage == "rejected" and not reason:
        raise ApplicationStateError("rejection requires a reason")

    old_stage = row.stage
    row.stage = new_stage
    row.stage_entered_at = datetime.utcnow()
    if new_stage == "rejected":
        row.rejection_reason = reason
    if note:
        row.notes = (row.notes + "\n" if row.notes else "") + note

    db.add(
        HrApplicationEvent(
            application_id=row.id,
            event_type="stage_changed",
            user_id=actor_user_id,
            payload={"from": old_stage, "to": new_stage, "reason": reason},
        )
    )
    await write_audit(
        db,
        entity_type="application",
        entity_id=row.id,
        event="stage_changed",
        diff={"stage": [old_stage, new_stage]},
        actor_user_id=actor_user_id,
    )
    await db.flush()

    if new_stage == "hired":
        await trigger_bus.fire(
            "hr.applicant.hired",
            {
                "application_id": str(row.id),
                "applicant_id": str(row.applicant_id),
                "requisition_id": str(row.requisition_id),
                "actor_user_id": actor_user_id,
            },
        )

    # Candidate SMS is consent-gated and silently no-ops when phone / consent
    # / template are missing.  Import inside the function so the test suite
    # can monkeypatch the symbol per-call.
    from app.hr.recruiting.notifications import maybe_send_stage_sms

    await maybe_send_stage_sms(db, application_id=row.id, new_stage=new_stage)
    return row


async def list_by_requisition(
    db: AsyncSession,
    *,
    requisition_id: UUID,
    stage: str | None = None,
) -> list[HrApplication]:
    stmt = (
        select(HrApplication)
        .where(HrApplication.requisition_id == requisition_id)
        .order_by(HrApplication.created_at.desc())
    )
    if stage is not None:
        stmt = stmt.where(HrApplication.stage == stage)
    return list((await db.execute(stmt)).scalars().all())


async def get_application(
    db: AsyncSession, application_id: UUID
) -> HrApplication | None:
    return (
        await db.execute(select(HrApplication).where(HrApplication.id == application_id))
    ).scalar_one_or_none()


async def stage_counts_for_requisition(
    db: AsyncSession, *, requisition_id: UUID
) -> dict[str, int]:
    rows = (
        await db.execute(
            select(HrApplication.stage, func.count(HrApplication.id))
            .where(HrApplication.requisition_id == requisition_id)
            .group_by(HrApplication.stage)
        )
    ).all()
    return {stage: n for stage, n in rows}
