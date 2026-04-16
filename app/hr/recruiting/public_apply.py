from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
)
from app.hr.recruiting.applicant_schemas import ApplicantSource
from app.hr.recruiting.models import HrRequisition
from app.hr.shared import storage
from app.hr.shared.audit import write_audit


public_apply_router = APIRouter(prefix="/careers", tags=["hr-apply-public"])


_ALLOWED_RESUME_MIMES = {"application/pdf", "image/jpeg", "image/png"}
_MAX_RESUME_BYTES = 10 * 1024 * 1024  # 10 MB


@public_apply_router.post(
    "/{slug}/apply",
    status_code=status.HTTP_201_CREATED,
)
async def apply(
    slug: str,
    request: Request,
    db: DbSession,
    first_name: str = Form(..., min_length=1, max_length=128),
    last_name: str = Form(..., min_length=1, max_length=128),
    email: str = Form(..., min_length=3, max_length=256),
    phone: str | None = Form(None, max_length=32),
    sms_consent: bool = Form(False),
    source: ApplicantSource = Form("careers_page"),
    source_ref: str | None = Form(None),
    resume: UploadFile | None = File(None),
) -> dict:
    requisition = (
        await db.execute(
            select(HrRequisition).where(
                HrRequisition.slug == slug, HrRequisition.status == "open"
            )
        )
    ).scalar_one_or_none()
    if requisition is None:
        raise HTTPException(status_code=404, detail="requisition not found or closed")

    resume_key: str | None = None
    if resume is not None and resume.filename:
        if resume.content_type not in _ALLOWED_RESUME_MIMES:
            raise HTTPException(status_code=400, detail="resume must be pdf / jpg / png")
        data = await resume.read()
        if len(data) > _MAX_RESUME_BYTES:
            raise HTTPException(status_code=400, detail="resume exceeds 10 MB")
        if data:
            suffix = "." + (resume.filename.rsplit(".", 1)[-1].lower() or "bin")
            resume_key = storage.save_bytes(data, suffix)

    ip = request.client.host if request.client else "unknown"

    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.email == email))
    ).scalar_one_or_none()
    if applicant is None:
        applicant = HrApplicant(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            resume_storage_key=resume_key,
            source=source,
            source_ref=source_ref,
            sms_consent_given=sms_consent,
            sms_consent_ip=ip if sms_consent else None,
            sms_consent_at=datetime.utcnow() if sms_consent else None,
        )
        db.add(applicant)
        await db.flush()
    else:
        if phone and not applicant.phone:
            applicant.phone = phone
        if resume_key:
            applicant.resume_storage_key = resume_key
        if sms_consent and not applicant.sms_consent_given:
            applicant.sms_consent_given = True
            applicant.sms_consent_ip = ip
            applicant.sms_consent_at = datetime.utcnow()

    try:
        application = HrApplication(
            applicant_id=applicant.id,
            requisition_id=requisition.id,
            stage="applied",
        )
        db.add(application)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="already applied for this role")

    db.add(
        HrApplicationEvent(
            application_id=application.id,
            event_type="created",
            payload={"source": source, "stage": "applied"},
        )
    )
    if resume_key:
        db.add(
            HrApplicationEvent(
                application_id=application.id,
                event_type="resume_uploaded",
                payload={"storage_key": resume_key},
            )
        )
    await write_audit(
        db,
        entity_type="application",
        entity_id=application.id,
        event="created",
        diff={"stage": [None, "applied"], "source": [None, source]},
        actor_ip=ip,
        actor_user_agent=request.headers.get("user-agent", ""),
    )
    await db.commit()

    return {
        "application_id": str(application.id),
        "applicant_id": str(applicant.id),
        "stage": application.stage,
    }
