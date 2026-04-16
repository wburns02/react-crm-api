import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.hr.esign.models import (
    HrDocumentTemplate,
    HrSignatureEvent,
    HrSignatureRequest,
    HrSignedDocument,
)
from app.hr.esign.renderer import fill_and_stamp
from app.hr.esign.schemas import SignatureRequestCreateIn
from app.hr.shared import storage
from app.hr.shared.audit import write_audit
from app.hr.workflow.models import HrWorkflowTask


class SignatureError(Exception):
    pass


async def create_signature_request(
    db: AsyncSession,
    payload: SignatureRequestCreateIn,
    *,
    actor_user_id: int | None,
) -> HrSignatureRequest:
    template = (
        await db.execute(
            select(HrDocumentTemplate).where(
                HrDocumentTemplate.kind == payload.document_template_kind,
                HrDocumentTemplate.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if template is None:
        raise SignatureError(
            f"document template '{payload.document_template_kind}' not found"
        )

    token = secrets.token_urlsafe(32)
    req = HrSignatureRequest(
        token=token,
        signer_email=payload.signer_email,
        signer_name=payload.signer_name,
        signer_user_id=payload.signer_user_id,
        document_template_id=template.id,
        field_values=payload.field_values,
        status="sent",
        expires_at=datetime.utcnow() + timedelta(days=payload.ttl_days),
        workflow_task_id=
            UUID(payload.workflow_task_id) if payload.workflow_task_id else None,
    )
    db.add(req)
    await db.flush()
    db.add(HrSignatureEvent(signature_request_id=req.id, event_type="sent"))
    await write_audit(
        db,
        entity_type="signature_request",
        entity_id=req.id,
        event="sent",
        actor_user_id=actor_user_id,
    )
    return req


async def mark_viewed(
    db: AsyncSession, *, token: str, ip: str, user_agent: str
) -> HrSignatureRequest:
    req = await _get_active_by_token(db, token=token)
    if req.status == "sent":
        req.status = "viewed"
        req.viewed_at = datetime.utcnow()
    db.add(
        HrSignatureEvent(
            signature_request_id=req.id,
            event_type="viewed",
            ip=ip,
            user_agent=user_agent,
        )
    )
    return req


async def submit_signature(
    db: AsyncSession,
    *,
    token: str,
    signature_image_base64: str,
    consent_confirmed: bool,
    ip: str,
    user_agent: str,
) -> HrSignedDocument:
    if not consent_confirmed:
        raise SignatureError("consent required")

    req = await _get_active_by_token(db, token=token)
    template = (
        await db.execute(
            select(HrDocumentTemplate).where(
                HrDocumentTemplate.id == req.document_template_id
            )
        )
    ).scalar_one()

    try:
        _, b64 = (
            signature_image_base64.split(",", 1)
            if "," in signature_image_base64
            else ("", signature_image_base64)
        )
        sig_bytes = base64.b64decode(b64)
    except Exception as e:
        raise SignatureError(f"invalid signature image: {e}")
    sig_key = storage.save_bytes(sig_bytes, ".png")

    source_path = storage.path_for(template.pdf_storage_key)
    template_fields = list(template.fields or [])
    text_fields = [f for f in template_fields if f.get("field_type") == "text"]
    sig_field = next(
        (f for f in template_fields if f.get("field_type") == "signature"), None
    )
    if sig_field is None:
        raise SignatureError("template has no signature field")

    pdf_bytes = fill_and_stamp(
        source_pdf_path=source_path,
        field_values=req.field_values or {},
        fields=text_fields,
        signature_image_path=storage.path_for(sig_key),
        signature_field=sig_field,
        signer_name=req.signer_name,
        signer_ip=ip,
        timestamp_override=datetime.utcnow().isoformat(),
    )
    signed_key = storage.save_bytes(pdf_bytes, ".pdf")
    h = hashlib.sha256(pdf_bytes).hexdigest()

    req.status = "signed"
    req.signed_at = datetime.utcnow()

    signed_doc = HrSignedDocument(
        signature_request_id=req.id,
        storage_key=signed_key,
        signer_ip=ip,
        signer_user_agent=user_agent,
        signature_image_key=sig_key,
        hash_sha256=h,
    )
    db.add(signed_doc)
    db.add(
        HrSignatureEvent(
            signature_request_id=req.id,
            event_type="signed",
            ip=ip,
            user_agent=user_agent,
        )
    )
    await db.flush()

    # If tied to a workflow task, surface the signed doc ids in the task result.
    if req.workflow_task_id:
        task = (
            await db.execute(
                select(HrWorkflowTask)
                .where(HrWorkflowTask.id == req.workflow_task_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if task is not None:
            task.result = {
                **(task.result or {}),
                "signature_id": str(req.id),
                "signed_document_id": str(signed_doc.id),
            }

    await write_audit(
        db,
        entity_type="signature_request",
        entity_id=req.id,
        event="signed",
        diff={"hash_sha256": [None, h]},
    )
    return signed_doc


async def _get_active_by_token(db: AsyncSession, *, token: str) -> HrSignatureRequest:
    req = (
        await db.execute(
            select(HrSignatureRequest).where(HrSignatureRequest.token == token)
        )
    ).scalar_one_or_none()
    if req is None:
        raise SignatureError("token not found")
    # Normalise: both sides must be naive UTC.  Postgres columns are
    # `TIMESTAMP WITHOUT TIME ZONE`, so the DB returns naive datetimes.
    expires = req.expires_at
    if expires.tzinfo is not None:
        expires = expires.astimezone(timezone.utc).replace(tzinfo=None)
    if req.status in {"expired", "revoked"} or expires < datetime.utcnow():
        raise SignatureError("signature link expired or revoked")
    if req.status == "signed":
        raise SignatureError("already signed")
    return req
