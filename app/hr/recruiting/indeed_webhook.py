"""Indeed Apply JSON webhook.

Indeed posts applicant data as JSON when a candidate clicks "Apply with
Indeed" on a job listing sourced from our XML feed.  We identify the
matching requisition by slug (we emit it as <referencenumber> in the XML
feed) and upsert an HrApplicant + HrApplication with source=indeed.

Shape tolerated (Indeed Apply v1-ish, lenient):

    {
      "id": "indeed-apply-id",             # optional
      "job": {"jobId": "slug", "jobTitle": "..."},
      "applicant": {
        "fullName": "First Last",
        "email": "...",
        "phoneNumber": "..."
      },
      "resume": {"url": "https://..."}
    }

We also accept the alternate flat shape some integrators send:

    {
      "reference_number": "slug",
      "first_name": "...",
      "last_name": "...",
      "email": "...",
      "phone": "..."
    }

The endpoint is public (no auth), accepts JSON only, and returns the
created IDs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbSession
from app.hr.recruiting.applicant_models import (
    HrApplicant,
    HrApplication,
    HrApplicationEvent,
)
from app.hr.recruiting.models import HrRequisition
from app.hr.shared.audit import write_audit


indeed_webhook_router = APIRouter(tags=["hr-indeed-apply"])


class IndeedApplyIn(BaseModel):
    """Flexible inbound shape — we pick up either nested or flat fields."""

    id: str | None = None
    # Nested shape (Indeed Apply v1-style)
    job: dict[str, Any] | None = None
    applicant: dict[str, Any] | None = None
    resume: dict[str, Any] | None = None
    # Flat shape fallbacks
    reference_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    # Allow extra forward-compat fields
    model_config = {"extra": "allow"}

    def slug(self) -> str | None:
        if self.job and isinstance(self.job, dict):
            for k in ("jobId", "job_id", "reference_number", "referencenumber"):
                v = self.job.get(k)
                if isinstance(v, str) and v:
                    return v
        return self.reference_number

    def names(self) -> tuple[str | None, str | None]:
        first = self.first_name
        last = self.last_name
        full = self.full_name
        if self.applicant and isinstance(self.applicant, dict):
            full = self.applicant.get("fullName") or full
            first = self.applicant.get("firstName") or first
            last = self.applicant.get("lastName") or last
        if not (first or last) and full:
            parts = full.strip().split(None, 1)
            first = parts[0] if parts else None
            last = parts[1] if len(parts) > 1 else None
        return first, last

    def email_value(self) -> str | None:
        if self.applicant and isinstance(self.applicant, dict):
            v = self.applicant.get("email")
            if isinstance(v, str):
                return v
        return str(self.email) if self.email else None

    def phone_value(self) -> str | None:
        if self.applicant and isinstance(self.applicant, dict):
            v = self.applicant.get("phoneNumber") or self.applicant.get("phone")
            if isinstance(v, str):
                return v
        return self.phone

    def resume_url(self) -> str | None:
        if self.resume and isinstance(self.resume, dict):
            v = self.resume.get("url")
            if isinstance(v, str):
                return v
        return None


@indeed_webhook_router.post(
    "/hr/indeed-apply", status_code=status.HTTP_201_CREATED
)
async def indeed_apply(
    payload: IndeedApplyIn, request: Request, db: DbSession
) -> dict:
    slug = payload.slug()
    if not slug:
        raise HTTPException(
            status_code=400,
            detail="missing job reference (job.jobId or reference_number)",
        )
    first, last = payload.names()
    email = payload.email_value()
    if not first or not last or not email:
        raise HTTPException(
            status_code=400,
            detail="applicant.fullName (or first_name/last_name) and email required",
        )

    requisition = (
        await db.execute(
            select(HrRequisition).where(
                HrRequisition.slug == slug, HrRequisition.status == "open"
            )
        )
    ).scalar_one_or_none()
    if requisition is None:
        raise HTTPException(
            status_code=404, detail="requisition not found or not open"
        )

    ip = request.client.host if request.client else "unknown"
    phone = payload.phone_value()
    resume_url = payload.resume_url()

    applicant = (
        await db.execute(select(HrApplicant).where(HrApplicant.email == email))
    ).scalar_one_or_none()
    if applicant is None:
        applicant = HrApplicant(
            first_name=first,
            last_name=last,
            email=email,
            phone=phone,
            resume_storage_key=None,
            source="indeed",
            source_ref=payload.id,
            sms_consent_given=False,
        )
        db.add(applicant)
        await db.flush()
    else:
        if phone and not applicant.phone:
            applicant.phone = phone
        # Refresh source_ref if Indeed reposts the same applicant.
        if payload.id and not applicant.source_ref:
            applicant.source_ref = payload.id

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
        raise HTTPException(
            status_code=409, detail="already applied for this role"
        )

    event_payload: dict[str, Any] = {"source": "indeed", "stage": "applied"}
    if resume_url:
        event_payload["resume_url"] = resume_url
    if payload.id:
        event_payload["indeed_apply_id"] = payload.id
    db.add(
        HrApplicationEvent(
            application_id=application.id,
            event_type="created",
            payload=event_payload,
        )
    )
    await write_audit(
        db,
        entity_type="application",
        entity_id=application.id,
        event="created",
        diff={
            "stage": [None, "applied"],
            "source": [None, "indeed"],
        },
        actor_ip=ip,
        actor_user_agent=request.headers.get("user-agent", "indeed-apply"),
    )
    await db.commit()

    return {
        "application_id": str(application.id),
        "applicant_id": str(applicant.id),
        "stage": application.stage,
        "source": "indeed",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
