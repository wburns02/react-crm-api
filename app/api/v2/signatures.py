"""E-Signature API - Digital document signing.

Features:
- Create signature requests
- Email/SMS signing links
- Capture signatures (drawn, typed)
- Generate signed PDFs
- Audit trail
"""
from fastapi import APIRouter, HTTPException, status, Query, Request
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import secrets
import logging
import json

from app.api.deps import DbSession, CurrentUser
from app.models.signature import SignatureRequest, Signature, SignedDocument
from app.models.quote import Quote

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models

class CreateSignatureRequest(BaseModel):
    document_type: str = Field(..., description="quote, contract, work_order")
    document_id: str
    customer_id: str
    signer_name: str
    signer_email: str
    signer_phone: Optional[str] = None
    title: str
    message: Optional[str] = None
    expires_in_days: int = Field(7, ge=1, le=30)


class CaptureSignatureRequest(BaseModel):
    signature_data: str = Field(..., description="Base64 image or SVG path data")
    signature_type: str = Field("drawn", description="drawn, typed, uploaded")
    consent_accepted: bool = True


class SignatureRequestResponse(BaseModel):
    id: str
    document_type: str
    document_id: str
    customer_id: str
    signer_name: str
    signer_email: str
    title: str
    status: str
    signing_url: Optional[str] = None
    sent_at: Optional[str] = None
    viewed_at: Optional[str] = None
    signed_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None


# Helper functions

def sig_request_to_response(req: SignatureRequest, include_url: bool = False) -> dict:
    """Convert SignatureRequest model to response dict."""
    response = {
        "id": str(req.id),
        "document_type": req.document_type,
        "document_id": req.document_id,
        "customer_id": str(req.customer_id),
        "signer_name": req.signer_name,
        "signer_email": req.signer_email,
        "signer_phone": req.signer_phone,
        "title": req.title,
        "message": req.message,
        "status": req.status,
        "sent_at": req.sent_at.isoformat() if req.sent_at else None,
        "viewed_at": req.viewed_at.isoformat() if req.viewed_at else None,
        "signed_at": req.signed_at.isoformat() if req.signed_at else None,
        "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        "reminder_count": req.reminder_count,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }

    if include_url:
        # Generate signing URL (frontend will use this)
        response["signing_url"] = f"/sign/{req.access_token}"

    return response


# Endpoints

@router.post("")
async def create_signature_request(
    request: CreateSignatureRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new signature request for a document."""
    # Generate secure access token
    access_token = secrets.token_urlsafe(32)

    sig_request = SignatureRequest(
        document_type=request.document_type,
        document_id=request.document_id,
        customer_id=int(request.customer_id),
        signer_name=request.signer_name,
        signer_email=request.signer_email,
        signer_phone=request.signer_phone,
        title=request.title,
        message=request.message,
        access_token=access_token,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(days=request.expires_in_days),
        created_by=current_user.email,
    )

    db.add(sig_request)
    await db.commit()
    await db.refresh(sig_request)

    return sig_request_to_response(sig_request, include_url=True)


@router.get("")
async def list_signature_requests(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    document_type: Optional[str] = None,
    customer_id: Optional[str] = None,
):
    """List signature requests with filtering."""
    query = select(SignatureRequest)

    if status_filter:
        query = query.where(SignatureRequest.status == status_filter)
    if document_type:
        query = query.where(SignatureRequest.document_type == document_type)
    if customer_id:
        query = query.where(SignatureRequest.customer_id == int(customer_id))

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(SignatureRequest.created_at.desc())

    result = await db.execute(query)
    requests = result.scalars().all()

    return {
        "items": [sig_request_to_response(r) for r in requests],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{request_id}")
async def get_signature_request(
    request_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a signature request by ID."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == request_id)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found",
        )

    return sig_request_to_response(sig_request, include_url=True)


@router.post("/{request_id}/send")
async def send_signature_request(
    request_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send signature request via email."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == request_id)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found",
        )

    # TODO: Integrate with communications service to send email
    # For now, just mark as sent
    sig_request.sent_at = datetime.utcnow()
    sig_request.status = "sent" if sig_request.status == "pending" else sig_request.status
    await db.commit()

    return {
        "status": "sent",
        "signing_url": f"/sign/{sig_request.access_token}",
        "sent_to": sig_request.signer_email,
    }


@router.post("/{request_id}/remind")
async def send_reminder(
    request_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send a reminder for unsigned document."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == request_id)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found",
        )

    if sig_request.status == "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document already signed",
        )

    # TODO: Send reminder email
    sig_request.reminder_count += 1
    sig_request.last_reminder_at = datetime.utcnow()
    await db.commit()

    return {
        "status": "reminder_sent",
        "reminder_count": sig_request.reminder_count,
    }


@router.delete("/{request_id}")
async def cancel_signature_request(
    request_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Cancel a signature request."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == request_id)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signature request not found",
        )

    if sig_request.status == "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel signed document",
        )

    sig_request.status = "cancelled"
    await db.commit()

    return {"status": "cancelled"}


# Public signing endpoints (no auth required)

@router.get("/sign/{token}")
async def get_signing_page(
    token: str,
    http_request: Request,
    db: DbSession,
):
    """Get document for signing (public, no auth)."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.access_token == token)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired signing link",
        )

    # Check expiration
    if sig_request.expires_at and datetime.utcnow() > sig_request.expires_at:
        sig_request.status = "expired"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Signing link has expired",
        )

    if sig_request.status == "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document already signed",
        )

    if sig_request.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Signature request has been cancelled",
        )

    # Mark as viewed
    if not sig_request.viewed_at:
        sig_request.viewed_at = datetime.utcnow()
        sig_request.status = "viewed"
        sig_request.ip_address = http_request.client.host if http_request.client else None
        sig_request.user_agent = http_request.headers.get("user-agent")
        await db.commit()

    # TODO: Load actual document content based on document_type/document_id
    document_content = None
    if sig_request.document_type == "quote":
        quote_result = await db.execute(
            select(Quote).where(Quote.id == sig_request.document_id)
        )
        quote = quote_result.scalar_one_or_none()
        if quote:
            document_content = {
                "type": "quote",
                "id": str(quote.id),
                # Add relevant quote fields
            }

    return {
        "request_id": str(sig_request.id),
        "title": sig_request.title,
        "message": sig_request.message,
        "signer_name": sig_request.signer_name,
        "document_type": sig_request.document_type,
        "document_content": document_content,
        "consent_text": "By signing below, I agree to the terms and conditions of this document.",
    }


@router.post("/sign/{token}")
async def capture_signature(
    token: str,
    request: CaptureSignatureRequest,
    http_request: Request,
    db: DbSession,
):
    """Capture signature (public, no auth)."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.access_token == token)
    )
    sig_request = result.scalar_one_or_none()

    if not sig_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired signing link",
        )

    if sig_request.status == "signed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document already signed",
        )

    if sig_request.expires_at and datetime.utcnow() > sig_request.expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Signing link has expired",
        )

    # Create signature record
    signature = Signature(
        request_id=sig_request.id,
        signature_data=request.signature_data,
        signature_type=request.signature_type,
        signer_name=sig_request.signer_name,
        signer_email=sig_request.signer_email,
        ip_address=http_request.client.host if http_request.client else None,
        user_agent=http_request.headers.get("user-agent"),
        consent_text="By signing below, I agree to the terms and conditions of this document.",
        consent_accepted=request.consent_accepted,
    )
    db.add(signature)

    # Update request status
    sig_request.status = "signed"
    sig_request.signed_at = datetime.utcnow()

    # Create audit log
    audit_log = json.dumps({
        "events": [
            {"event": "created", "timestamp": sig_request.created_at.isoformat() if sig_request.created_at else None},
            {"event": "sent", "timestamp": sig_request.sent_at.isoformat() if sig_request.sent_at else None},
            {"event": "viewed", "timestamp": sig_request.viewed_at.isoformat() if sig_request.viewed_at else None},
            {"event": "signed", "timestamp": datetime.utcnow().isoformat(), "ip": signature.ip_address},
        ]
    })

    # Create signed document record
    signed_doc = SignedDocument(
        request_id=sig_request.id,
        signature_id=signature.id,
        document_type=sig_request.document_type,
        document_id=sig_request.document_id,
        customer_id=sig_request.customer_id,
        audit_log=audit_log,
    )
    db.add(signed_doc)

    await db.commit()

    # TODO: Generate PDF with embedded signature
    # TODO: Send confirmation email

    return {
        "status": "signed",
        "signed_document_id": str(signed_doc.id),
        "signed_at": sig_request.signed_at.isoformat(),
    }


@router.get("/documents/{document_id}")
async def get_signed_document(
    document_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a signed document by ID."""
    result = await db.execute(
        select(SignedDocument).where(SignedDocument.id == document_id)
    )
    signed_doc = result.scalar_one_or_none()

    if not signed_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signed document not found",
        )

    return {
        "id": str(signed_doc.id),
        "document_type": signed_doc.document_type,
        "document_id": signed_doc.document_id,
        "customer_id": str(signed_doc.customer_id),
        "pdf_url": signed_doc.pdf_url,
        "audit_log": json.loads(signed_doc.audit_log) if signed_doc.audit_log else None,
        "created_at": signed_doc.created_at.isoformat() if signed_doc.created_at else None,
    }
