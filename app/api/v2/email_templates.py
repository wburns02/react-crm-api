"""Email Templates API Endpoints

CRUD operations for email templates with merge field support.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from uuid import UUID
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.marketing import EmailTemplate
from app.schemas.email_template import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    EmailTemplateResponse,
    EmailTemplateListResponse,
    EmailTemplatePreview,
    EmailTemplateRenderRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_email_templates(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List all email templates with optional filtering."""
    try:
        query = select(EmailTemplate)

        # Apply filters
        if category:
            query = query.where(EmailTemplate.category == category)

        if is_active is not None:
            query = query.where(EmailTemplate.is_active == is_active)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(EmailTemplate.name)

        # Execute query
        result = await db.execute(query)
        templates = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "subject": t.subject,
                    "body_html": t.body_html,
                    "body_text": t.body_text,
                    "variables": t.variables or [],
                    "category": t.category,
                    "is_active": t.is_active,
                    "created_by": t.created_by,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in templates
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Email templates list failed: {e}")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "debug_error": str(e),
        }


@router.get("/categories")
async def list_template_categories(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get list of available template categories with counts."""
    query = select(
        EmailTemplate.category,
        func.count(EmailTemplate.id).label("count"),
    ).group_by(EmailTemplate.category)

    result = await db.execute(query)
    rows = result.all()

    return {"categories": [{"name": row.category, "count": row.count} for row in rows]}


@router.get("/{template_id}", response_model=EmailTemplateResponse)
async def get_email_template(
    template_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single email template by ID."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email template not found",
        )

    return template


@router.post("", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_email_template(
    request: EmailTemplateCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new email template."""
    template = EmailTemplate(
        name=request.name,
        category=request.category,
        subject=request.subject,
        body_html=request.body_html,
        body_text=request.body_text,
        variables=request.variables,
        is_active=request.is_active,
        created_by=current_user.id,
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    logger.info(f"Email template created: {template.id} by user {current_user.id}")

    return template


@router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: UUID,
    request: EmailTemplateUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an existing email template."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email template not found",
        )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    logger.info(f"Email template updated: {template.id} by user {current_user.id}")

    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_template(
    template_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an email template."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email template not found",
        )

    await db.delete(template)
    await db.commit()

    logger.info(f"Email template deleted: {template_id} by user {current_user.id}")


@router.post("/{template_id}/preview", response_model=EmailTemplatePreview)
async def preview_email_template(
    template_id: UUID,
    request: EmailTemplateRenderRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Preview a template with sample data."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email template not found",
        )

    return EmailTemplatePreview(
        subject=template.render_subject(request.context),
        body_html=template.render_body_html(request.context),
        body_text=template.render_body_text(request.context),
    )


@router.get("/{template_id}/merge-fields")
async def get_template_merge_fields(
    template_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get available merge fields for a template."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email template not found",
        )

    # Define field metadata
    field_metadata = {
        "customer_name": {"description": "Customer's full name", "example": "John Smith"},
        "customer_email": {"description": "Customer's email address", "example": "john@example.com"},
        "customer_phone": {"description": "Customer's phone number", "example": "(555) 123-4567"},
        "scheduled_date": {"description": "Appointment date", "example": "January 30, 2026"},
        "scheduled_time": {"description": "Appointment time", "example": "10:00 AM"},
        "job_type": {"description": "Type of service", "example": "Septic Tank Pumping"},
        "service_address": {"description": "Service location", "example": "123 Main St, Houston, TX"},
        "technician_name": {"description": "Assigned technician", "example": "Mike Johnson"},
        "invoice_number": {"description": "Invoice number", "example": "INV-2026-001"},
        "invoice_total": {"description": "Invoice total amount", "example": "$350.00"},
        "due_date": {"description": "Payment due date", "example": "February 15, 2026"},
        "payment_link": {"description": "Online payment URL", "example": "https://pay.example.com/inv123"},
        "company_name": {"description": "Your company name", "example": "MAC Septic Services"},
        "company_phone": {"description": "Company phone number", "example": "(713) 555-0100"},
        "review_link": {"description": "Review submission URL", "example": "https://g.page/review/..."},
        "completed_date": {"description": "Service completion date", "example": "January 29, 2026"},
    }

    return {
        "fields": [
            {"name": field, **field_metadata.get(field, {"description": f"Value for {field}", "example": ""})}
            for field in (template.variables or [])
        ]
    }
