"""Document Center API endpoints for PDF generation, email delivery, and management."""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func, desc, or_
from sqlalchemy.orm import selectinload, joinedload
import httpx

from app.api.deps import DbSession, CurrentUser, EntityCtx
from app.models import Document, Customer, Invoice, Quote, WorkOrder
from app.services.document_templates import render_document_html, render_document_pdf

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic schemas for Document Center
class GenerateRequest(BaseModel):
    document_type: str  # invoice, quote, work_order, inspection_report
    reference_id: str


class SendRequest(BaseModel):
    email: str
    subject: Optional[str] = None
    message: Optional[str] = None


class BatchGenerateRequest(BaseModel):
    document_type: str
    reference_ids: List[str]


class DocumentResponse(BaseModel):
    id: str
    document_type: str
    reference_id: Optional[str]
    reference_number: Optional[str]
    customer_id: Optional[str]
    customer_name: Optional[str]
    file_name: Optional[str]
    file_size: Optional[int]
    status: str
    sent_at: Optional[datetime]
    sent_to: Optional[str]
    viewed_at: Optional[datetime]
    created_by: Optional[str]
    created_at: datetime


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class DocumentStats(BaseModel):
    total_documents: int
    sent_this_month: int
    viewed_count: int
    pending_drafts: int
    monthly_counts: List[dict]  # [{month: "2026-01", count: 15, ...}, ...]


def document_to_response(document: Document, customer: Optional[Customer] = None) -> DocumentResponse:
    """Convert Document model to response format."""
    customer_name = None
    if customer:
        customer_name = customer.name or f"{customer.first_name or ''} {customer.last_name or ''}".strip()

    return DocumentResponse(
        id=str(document.id),
        document_type=document.document_type,
        reference_id=str(document.reference_id) if document.reference_id else None,
        reference_number=document.reference_number,
        customer_id=str(document.customer_id) if document.customer_id else None,
        customer_name=customer_name,
        file_name=document.file_name,
        file_size=document.file_size,
        status=document.status,
        sent_at=document.sent_at,
        sent_to=document.sent_to,
        viewed_at=document.viewed_at,
        created_by=str(document.created_by) if document.created_by else None,
        created_at=document.created_at,
    )


async def fetch_source_data(
    db: DbSession,
    document_type: str,
    reference_id: str,
    entity_id: str
) -> tuple[dict, Optional[Customer]]:
    """Fetch the source record (invoice/quote/WO) and customer data for PDF generation."""

    if document_type == "invoice":
        result = await db.execute(
            select(Invoice)
            .options(selectinload(Invoice.line_items))
            .where(Invoice.id == reference_id, Invoice.entity_id == entity_id)
        )
        invoice = result.scalar_one_or_none()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Get customer
        customer = None
        if invoice.customer_id:
            result = await db.execute(
                select(Customer).where(Customer.id == invoice.customer_id)
            )
            customer = result.scalar_one_or_none()

        return {
            "invoice": {
                "id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
                "status": invoice.status,
                "notes": invoice.notes,
                "line_items": invoice.line_items or [],
                "amount": float(invoice.amount) if invoice.amount else 0.0,
                "created_at": invoice.created_at.isoformat(),
            },
            "customer": {
                "id": str(customer.id) if customer else None,
                "name": customer.name if customer else "Unknown Customer",
                "first_name": customer.first_name if customer else "",
                "last_name": customer.last_name if customer else "",
                "email": customer.email if customer else "",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
            } if customer else {},
        }, customer

    elif document_type == "quote":
        result = await db.execute(
            select(Quote)
            .where(Quote.id == reference_id, Quote.entity_id == entity_id)
        )
        quote = result.scalar_one_or_none()
        if not quote:
            raise HTTPException(status_code=404, detail="Quote not found")

        # Get customer
        customer = None
        if quote.customer_id:
            result = await db.execute(
                select(Customer).where(Customer.id == quote.customer_id)
            )
            customer = result.scalar_one_or_none()

        return {
            "quote": {
                "id": str(quote.id),
                "quote_number": f"QUO-{str(quote.id)[:8].upper()}",
                "created_at": quote.created_at.isoformat(),
                "valid_until": quote.expiry_date.isoformat() if hasattr(quote, 'expiry_date') and quote.expiry_date else None,
                "status": quote.status if hasattr(quote, 'status') else "draft",
                "line_items": quote.line_items if hasattr(quote, 'line_items') else [],
            },
            "customer": {
                "id": str(customer.id) if customer else None,
                "name": customer.name if customer else "Unknown Customer",
                "first_name": customer.first_name if customer else "",
                "last_name": customer.last_name if customer else "",
                "email": customer.email if customer else "",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
            } if customer else {},
        }, customer

    elif document_type == "work_order":
        result = await db.execute(
            select(WorkOrder)
            .options(joinedload(WorkOrder.customer), joinedload(WorkOrder.technician))
            .where(WorkOrder.id == reference_id, WorkOrder.entity_id == entity_id)
        )
        work_order = result.scalar_one_or_none()
        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        customer = work_order.customer
        technician = work_order.technician

        return {
            "work_order": {
                "id": str(work_order.id),
                "type": work_order.type,
                "status": work_order.status,
                "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
                "priority": work_order.priority if hasattr(work_order, 'priority') else "normal",
                "notes": work_order.notes,
                "checklist": work_order.checklist if hasattr(work_order, 'checklist') else {},
                "job_type": work_order.type,
            },
            "customer": {
                "id": str(customer.id) if customer else None,
                "name": customer.name if customer else "Unknown Customer",
                "first_name": customer.first_name if customer else "",
                "last_name": customer.last_name if customer else "",
                "email": customer.email if customer else "",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
            } if customer else {},
            "technician": {
                "id": str(technician.id) if technician else None,
                "first_name": technician.first_name if technician else "",
                "last_name": technician.last_name if technician else "",
            } if technician else {},
        }, customer

    elif document_type == "inspection_report":
        # Same as work_order but focus on inspection data
        result = await db.execute(
            select(WorkOrder)
            .options(joinedload(WorkOrder.customer))
            .where(WorkOrder.id == reference_id, WorkOrder.entity_id == entity_id)
        )
        work_order = result.scalar_one_or_none()
        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        customer = work_order.customer

        return {
            "work_order": {
                "id": str(work_order.id),
                "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
                "checklist": work_order.checklist if hasattr(work_order, 'checklist') else {},
            },
            "customer": {
                "id": str(customer.id) if customer else None,
                "name": customer.name if customer else "Unknown Customer",
                "first_name": customer.first_name if customer else "",
                "last_name": customer.last_name if customer else "",
                "email": customer.email if customer else "",
                "phone": customer.phone if customer else "",
                "address": customer.address if customer else "",
            } if customer else {},
        }, customer

    else:
        raise HTTPException(status_code=400, detail=f"Unknown document type: {document_type}")


async def send_document_email(
    document: Document,
    email: str,
    subject: Optional[str] = None,
    message: Optional[str] = None
):
    """Send document PDF via email with tracking pixel."""

    # Default subject if not provided
    if not subject:
        doc_type_map = {
            "invoice": "Invoice",
            "quote": "Estimate",
            "work_order": "Work Order",
            "inspection_report": "Inspection Report"
        }
        doc_type_name = doc_type_map.get(document.document_type, "Document")
        subject = f"{doc_type_name} {document.reference_number or ''} from MAC Septic Services".strip()

    # Default message if not provided
    if not message:
        message = f"Please find attached your {document.document_type.replace('_', ' ')} from MAC Septic Services."

    # Create HTML email body with tracking pixel
    tracking_url = f"https://react-crm-api-production.up.railway.app/api/v2/documents/track/{document.id}"
    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1e293b;">MAC Septic Services</h2>
            <p>Dear Valued Customer,</p>
            <p>{message}</p>
            <p>If you have any questions, please don't hesitate to contact us.</p>
            <br>
            <p>Best regards,<br>MAC Septic Services Team</p>
            <hr>
            <p style="font-size: 12px; color: #64748b;">
                This is an automated message from MAC Septic Services.
            </p>
        </div>
        <img src="{tracking_url}" width="1" height="1" style="border:0; display:block;" />
    </body>
    </html>
    """

    # For now, log the email sending - in production, integrate with your email service
    logger.info(f"Sending document {document.id} to {email} with subject: {subject}")
    logger.info(f"HTML body length: {len(html_body)}")
    logger.info(f"PDF size: {document.file_size} bytes")

    # TODO: Integrate with actual email service (Brevo, SendGrid, etc.)
    # For now, we'll simulate successful sending
    return True


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    document_type: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """List documents with pagination and filters."""

    query = select(Document).where(Document.entity_id == entity.id)

    # Add filters
    if document_type:
        query = query.where(Document.document_type == document_type)

    if customer_id:
        query = query.where(Document.customer_id == customer_id)

    if status:
        query = query.where(Document.status == status)

    if search:
        query = query.where(
            or_(
                Document.reference_number.ilike(f"%{search}%"),
                Document.file_name.ilike(f"%{search}%")
            )
        )

    if date_from:
        try:
            date_from_parsed = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            query = query.where(Document.created_at >= date_from_parsed)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_parsed = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            query = query.where(Document.created_at <= date_to_parsed)
        except ValueError:
            pass

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    query = query.order_by(desc(Document.created_at)).offset(offset).limit(page_size)

    # Execute query
    result = await db.execute(query)
    documents = result.scalars().all()

    # Fetch customer data for enrichment
    customer_ids = [doc.customer_id for doc in documents if doc.customer_id]
    customers_dict = {}
    if customer_ids:
        customers_result = await db.execute(
            select(Customer).where(Customer.id.in_(customer_ids))
        )
        customers = customers_result.scalars().all()
        customers_dict = {str(c.id): c for c in customers}

    # Convert to response format
    items = []
    for doc in documents:
        customer = customers_dict.get(str(doc.customer_id)) if doc.customer_id else None
        items.append(document_to_response(doc, customer))

    return DocumentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.get("/stats", response_model=DocumentStats)
async def get_document_stats(
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Return document statistics for dashboard."""

    # Total documents
    total_result = await db.execute(
        select(func.count(Document.id)).where(Document.entity_id == entity.id)
    )
    total_documents = total_result.scalar() or 0

    # Sent this month
    current_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sent_this_month_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.entity_id == entity.id,
            Document.sent_at >= current_month_start,
            Document.status.in_(["sent", "viewed"])
        )
    )
    sent_this_month = sent_this_month_result.scalar() or 0

    # Viewed count
    viewed_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.entity_id == entity.id,
            Document.viewed_at.isnot(None)
        )
    )
    viewed_count = viewed_result.scalar() or 0

    # Pending drafts
    drafts_result = await db.execute(
        select(func.count(Document.id)).where(
            Document.entity_id == entity.id,
            Document.status == "draft"
        )
    )
    pending_drafts = drafts_result.scalar() or 0

    # Monthly counts for chart (last 12 months)
    monthly_counts = []
    for i in range(12):
        # Calculate the start and end of each month going backwards
        if i == 0:
            month_start = current_month_start
            month_end = datetime.now()
        else:
            # Go back i months
            year = current_month_start.year
            month = current_month_start.month - i
            if month <= 0:
                month += 12
                year -= 1

            month_start = datetime(year, month, 1)
            # End of month
            if month == 12:
                month_end = datetime(year + 1, 1, 1)
            else:
                month_end = datetime(year, month + 1, 1)

        month_result = await db.execute(
            select(
                func.count(Document.id),
                func.sum(func.case((Document.document_type == "invoice", 1), else_=0)),
                func.sum(func.case((Document.document_type == "quote", 1), else_=0)),
                func.sum(func.case((Document.document_type == "work_order", 1), else_=0)),
                func.sum(func.case((Document.document_type == "inspection_report", 1), else_=0)),
            ).where(
                Document.entity_id == entity.id,
                Document.created_at >= month_start,
                Document.created_at < month_end
            )
        )
        counts = month_result.first()

        monthly_counts.append({
            "month": month_start.strftime("%Y-%m"),
            "total": counts[0] or 0,
            "invoices": counts[1] or 0,
            "quotes": counts[2] or 0,
            "work_orders": counts[3] or 0,
            "inspections": counts[4] or 0,
        })

    # Reverse to get chronological order
    monthly_counts.reverse()

    return DocumentStats(
        total_documents=total_documents,
        sent_this_month=sent_this_month,
        viewed_count=viewed_count,
        pending_drafts=pending_drafts,
        monthly_counts=monthly_counts,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Get single document metadata (no PDF data)."""

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.entity_id == entity.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get customer if available
    customer = None
    if document.customer_id:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == document.customer_id)
        )
        customer = customer_result.scalar_one_or_none()

    return document_to_response(document, customer)


@router.get("/{document_id}/pdf")
async def download_pdf(
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Stream the PDF binary as download."""

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.entity_id == entity.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.pdf_data:
        raise HTTPException(status_code=404, detail="PDF data not available")

    def pdf_generator():
        yield document.pdf_data

    filename = document.file_name or f"document-{document_id}.pdf"

    return StreamingResponse(
        pdf_generator(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )


@router.get("/{document_id}/html", response_class=HTMLResponse)
async def preview_html(
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Return rendered HTML preview."""

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.entity_id == entity.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.reference_id:
        raise HTTPException(status_code=400, detail="Cannot generate preview without reference data")

    try:
        # Fetch source data and generate HTML
        data, _ = await fetch_source_data(
            db, document.document_type, str(document.reference_id), entity.id
        )
        html = await render_document_html(document.document_type, data, entity.id)
        return HTMLResponse(content=html)
    except Exception as e:
        logger.error(f"Failed to generate HTML preview: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate preview")


@router.post("/generate", response_model=DocumentResponse)
async def generate_document(
    request: GenerateRequest,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Generate a new document PDF."""

    try:
        # Fetch source data
        data, customer = await fetch_source_data(
            db, request.document_type, request.reference_id, entity.id
        )

        # Generate PDF
        pdf_bytes = await render_document_pdf(request.document_type, data, entity.id)

        # Determine reference number based on document type
        reference_number = None
        if request.document_type == "invoice" and "invoice" in data:
            reference_number = data["invoice"].get("invoice_number")
        elif request.document_type == "quote" and "quote" in data:
            reference_number = data["quote"].get("quote_number")
        elif request.document_type in ["work_order", "inspection_report"] and "work_order" in data:
            prefix = "WO" if request.document_type == "work_order" else "INSP"
            reference_number = f"{prefix}-{str(data['work_order']['id'])[:8].upper()}"

        # Generate filename
        file_name = f"{reference_number or request.document_type}-{datetime.now().strftime('%Y%m%d')}.pdf"

        # Create Document record
        document = Document(
            entity_id=entity.id,
            document_type=request.document_type,
            reference_id=UUID(request.reference_id),
            reference_number=reference_number,
            customer_id=customer.id if customer else None,
            file_name=file_name,
            file_size=len(pdf_bytes),
            pdf_data=pdf_bytes,
            status="draft",
            created_by=user.id,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        return document_to_response(document, customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate document: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate document")


@router.post("/batch-generate")
async def batch_generate_documents(
    request: BatchGenerateRequest,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Generate multiple documents at once."""

    results = []
    errors = []

    for ref_id in request.reference_ids:
        try:
            # Generate each document
            gen_request = GenerateRequest(
                document_type=request.document_type,
                reference_id=ref_id
            )
            doc = await generate_document(gen_request, db, user, entity)
            results.append(doc)
        except Exception as e:
            logger.error(f"Failed to generate document for {ref_id}: {e}")
            errors.append({"reference_id": ref_id, "error": str(e)})

    return {
        "generated": results,
        "errors": errors,
        "total_requested": len(request.reference_ids),
        "total_generated": len(results),
        "total_errors": len(errors),
    }


@router.post("/{document_id}/send", response_model=DocumentResponse)
async def send_document(
    document_id: UUID,
    request: SendRequest,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Email the PDF to a customer."""

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.entity_id == entity.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.pdf_data:
        raise HTTPException(status_code=400, detail="No PDF data to send")

    try:
        # Send email
        await send_document_email(
            document=document,
            email=request.email,
            subject=request.subject,
            message=request.message
        )

        # Update document status
        document.status = "sent"
        document.sent_at = datetime.utcnow()
        document.sent_to = request.email

        await db.commit()
        await db.refresh(document)

        # Get customer for response
        customer = None
        if document.customer_id:
            customer_result = await db.execute(
                select(Customer).where(Customer.id == document.customer_id)
            )
            customer = customer_result.scalar_one_or_none()

        return document_to_response(document, customer)

    except Exception as e:
        logger.error(f"Failed to send document {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to send document")


@router.post("/{document_id}/resend", response_model=DocumentResponse)
async def resend_document(
    document_id: UUID,
    request: SendRequest,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Resend document to same or new email."""
    # Same logic as send_document
    return await send_document(document_id, request, db, user, entity)


@router.get("/track/{document_id}")
async def track_document_view(document_id: UUID, db: DbSession):
    """Public tracking pixel endpoint - updates viewed_at on first hit."""

    try:
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if document and not document.viewed_at:
            document.viewed_at = datetime.utcnow()
            document.status = "viewed" if document.status == "sent" else document.status
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to track document view {document_id}: {e}")

    # Return 1x1 transparent PNG
    transparent_pixel = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    )

    return Response(
        content=transparent_pixel,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


@router.delete("/{document_id}")
async def delete_document(
    document_id: UUID,
    db: DbSession,
    user: CurrentUser,
    entity: EntityCtx,
):
    """Delete a document."""

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.entity_id == entity.id
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    await db.delete(document)
    await db.commit()

    return {"message": "Document deleted successfully"}