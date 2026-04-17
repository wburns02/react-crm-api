from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.hr.recruiting.applicant_models import HrRecruitingMessageTemplate
from app.hr.recruiting.templates_admin_schemas import (
    MessageTemplateOut,
    MessageTemplatePatch,
)
from app.hr.shared.audit import write_audit


templates_admin_router = APIRouter(
    prefix="/recruiting/message-templates", tags=["hr-recruiting-templates"]
)


@templates_admin_router.get("", response_model=list[MessageTemplateOut])
async def list_templates(
    db: DbSession, user: CurrentUser
) -> list[MessageTemplateOut]:
    rows = (
        await db.execute(
            select(HrRecruitingMessageTemplate).order_by(
                HrRecruitingMessageTemplate.stage
            )
        )
    ).scalars().all()
    return [MessageTemplateOut.model_validate(r) for r in rows]


@templates_admin_router.patch("/{stage}", response_model=MessageTemplateOut)
async def patch_template(
    stage: str,
    payload: MessageTemplatePatch,
    db: DbSession,
    user: CurrentUser,
) -> MessageTemplateOut:
    row = (
        await db.execute(
            select(HrRecruitingMessageTemplate).where(
                HrRecruitingMessageTemplate.stage == stage
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")

    data = payload.model_dump(exclude_none=True)
    diff = {}
    for k, v in data.items():
        cur = getattr(row, k)
        if cur != v:
            diff[k] = [str(cur), str(v)]
            setattr(row, k, v)
    if diff:
        row.updated_at = datetime.utcnow()
        await db.flush()
        await write_audit(
            db,
            entity_type="recruiting_message_template",
            entity_id=row.id,
            event="updated",
            diff=diff,
            actor_user_id=user.id,
        )
        await db.commit()
    return MessageTemplateOut.model_validate(row)
