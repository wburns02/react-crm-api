"""
Escalation API Endpoints for Enterprise Customer Success Platform

Provides endpoints for managing customer escalations and resolution tracking.
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.user import User
from app.models.customer_success import Escalation, EscalationNote, EscalationActivity
from app.schemas.customer_success.escalation import (
    EscalationCreate,
    EscalationUpdate,
    EscalationResponse,
    EscalationListResponse,
    EscalationNoteCreate,
    EscalationNoteUpdate,
    EscalationNoteResponse,
    EscalationActivityResponse,
    EscalationAnalytics,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def create_activity(
    db: DbSession,
    escalation_id: int,
    activity_type: str,
    description: str,
    user_id: int,
    old_value: str = None,
    new_value: str = None,
):
    """Helper to create an escalation activity."""
    activity = EscalationActivity(
        escalation_id=escalation_id,
        activity_type=activity_type,
        description=description,
        old_value=old_value,
        new_value=new_value,
        performed_by_user_id=user_id,
    )
    db.add(activity)
    return activity


# Escalation CRUD


@router.get("/", response_model=EscalationListResponse)
async def list_escalations(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    escalation_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    assigned_to_user_id: Optional[int] = None,
    search: Optional[str] = None,
):
    """List escalations with filtering."""
    try:
        query = select(Escalation).options(
            selectinload(Escalation.notes),
            selectinload(Escalation.activities),
        )

        if escalation_type:
            query = query.where(Escalation.escalation_type == escalation_type)
        if severity:
            query = query.where(Escalation.severity == severity)
        if status:
            query = query.where(Escalation.status == status)
        if customer_id:
            query = query.where(Escalation.customer_id == customer_id)
        if assigned_to_user_id:
            query = query.where(Escalation.assigned_to_user_id == assigned_to_user_id)
        if search:
            query = query.where(Escalation.title.ilike(f"%{search}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Escalation.priority.desc(), Escalation.created_at.desc())

        result = await db.execute(query)
        escalations = result.scalars().unique().all()

        # Enhance with names
        items = []
        for esc in escalations:
            esc_dict = {
                "id": esc.id,
                "customer_id": esc.customer_id,
                "title": esc.title,
                "description": esc.description,
                "escalation_type": esc.escalation_type,
                "severity": esc.severity,
                "priority": esc.priority,
                "status": esc.status,
                "source": esc.source,
                "source_id": esc.source_id,
                "assigned_to_user_id": esc.assigned_to_user_id,
                "escalated_by_user_id": esc.escalated_by_user_id,
                "escalated_to_user_id": esc.escalated_to_user_id,
                "sla_hours": esc.sla_hours,
                "sla_deadline": esc.sla_deadline,
                "sla_breached": esc.sla_breached,
                "first_response_at": esc.first_response_at,
                "first_response_sla_hours": esc.first_response_sla_hours,
                "first_response_breached": esc.first_response_breached,
                "revenue_at_risk": esc.revenue_at_risk,
                "churn_probability": esc.churn_probability,
                "impact_description": esc.impact_description,
                "root_cause_category": esc.root_cause_category,
                "root_cause_description": esc.root_cause_description,
                "resolution_summary": esc.resolution_summary,
                "resolution_category": esc.resolution_category,
                "customer_satisfaction": esc.customer_satisfaction,
                "tags": esc.tags,
                "notes": esc.notes,
                "activities": esc.activities,
                "created_at": esc.created_at,
                "updated_at": esc.updated_at,
                "resolved_at": esc.resolved_at,
                "closed_at": esc.closed_at,
            }

            # Get customer name
            cust_result = await db.execute(select(Customer.name).where(Customer.id == esc.customer_id))
            esc_dict["customer_name"] = cust_result.scalar_one_or_none()

            # Get user names
            if esc.assigned_to_user_id:
                user_result = await db.execute(select(User.name).where(User.id == esc.assigned_to_user_id))
                esc_dict["assigned_to_name"] = user_result.scalar_one_or_none()
            else:
                esc_dict["assigned_to_name"] = None

            if esc.escalated_by_user_id:
                user_result = await db.execute(select(User.name).where(User.id == esc.escalated_by_user_id))
                esc_dict["escalated_by_name"] = user_result.scalar_one_or_none()
            else:
                esc_dict["escalated_by_name"] = None

            if esc.escalated_to_user_id:
                user_result = await db.execute(select(User.name).where(User.id == esc.escalated_to_user_id))
                esc_dict["escalated_to_name"] = user_result.scalar_one_or_none()
            else:
                esc_dict["escalated_to_name"] = None

            items.append(esc_dict)

        return EscalationListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error listing escalations: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error listing escalations: {str(e)}"
        )


@router.get("/{escalation_id}", response_model=EscalationResponse)
async def get_escalation(
    escalation_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific escalation with notes and activities."""
    result = await db.execute(
        select(Escalation)
        .options(
            selectinload(Escalation.notes),
            selectinload(Escalation.activities),
        )
        .where(Escalation.id == escalation_id)
    )
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    return escalation


@router.post("/", response_model=EscalationResponse, status_code=status.HTTP_201_CREATED)
async def create_escalation(
    data: EscalationCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new escalation."""
    # Verify customer exists
    cust_result = await db.execute(select(Customer).where(Customer.id == data.customer_id))
    if not cust_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    escalation_data = data.model_dump()
    escalation = Escalation(
        **escalation_data,
        escalated_by_user_id=current_user.id,
    )

    # Set SLA deadline
    escalation.sla_deadline = datetime.utcnow() + timedelta(hours=escalation.sla_hours)

    db.add(escalation)
    await db.flush()

    # Create initial activity
    await create_activity(
        db,
        escalation.id,
        "created",
        f"Escalation created with severity: {escalation.severity}",
        current_user.id,
    )

    await db.commit()
    await db.refresh(escalation)

    # Load relationships
    result = await db.execute(
        select(Escalation)
        .options(
            selectinload(Escalation.notes),
            selectinload(Escalation.activities),
        )
        .where(Escalation.id == escalation.id)
    )
    return result.scalar_one()


@router.patch("/{escalation_id}", response_model=EscalationResponse)
async def update_escalation(
    escalation_id: int,
    data: EscalationUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an escalation."""
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Track changes for activity log
    for field, value in update_data.items():
        old_value = getattr(escalation, field)
        if old_value != value:
            # Log important changes
            if field in ["status", "severity", "assigned_to_user_id", "priority"]:
                await create_activity(
                    db,
                    escalation.id,
                    f"{field}_change",
                    f"{field.replace('_', ' ').title()} changed",
                    current_user.id,
                    str(old_value),
                    str(value),
                )
            setattr(escalation, field, value)

    # Handle status transitions
    if data.status:
        if data.status == "resolved" and not escalation.resolved_at:
            escalation.resolved_at = datetime.utcnow()
        elif data.status == "closed" and not escalation.closed_at:
            escalation.closed_at = datetime.utcnow()

    # Track first response
    if not escalation.first_response_at and data.status == "in_progress":
        escalation.first_response_at = datetime.utcnow()
        # Check SLA breach
        first_response_deadline = escalation.created_at + timedelta(hours=escalation.first_response_sla_hours)
        if datetime.utcnow() > first_response_deadline:
            escalation.first_response_breached = True

    # Check SLA breach for resolution
    if data.status == "resolved" and escalation.sla_deadline:
        if datetime.utcnow() > escalation.sla_deadline:
            escalation.sla_breached = True

    await db.commit()

    # Load relationships
    result = await db.execute(
        select(Escalation)
        .options(
            selectinload(Escalation.notes),
            selectinload(Escalation.activities),
        )
        .where(Escalation.id == escalation.id)
    )
    return result.scalar_one()


@router.delete("/{escalation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_escalation(
    escalation_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an escalation."""
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    if escalation.status not in ["resolved", "closed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete an open escalation",
        )

    await db.delete(escalation)
    await db.commit()


# Escalation Notes


@router.post("/{escalation_id}/notes", response_model=EscalationNoteResponse, status_code=status.HTTP_201_CREATED)
async def add_note(
    escalation_id: int,
    data: EscalationNoteCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Add a note to an escalation."""
    # Verify escalation exists
    esc_result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    if not esc_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    note = EscalationNote(
        escalation_id=escalation_id,
        created_by_user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(note)

    # Create activity
    await create_activity(
        db,
        escalation_id,
        "note_added",
        f"Note added: {data.note_type}",
        current_user.id,
    )

    await db.commit()
    await db.refresh(note)
    return note


@router.patch("/{escalation_id}/notes/{note_id}", response_model=EscalationNoteResponse)
async def update_note(
    escalation_id: int,
    note_id: int,
    data: EscalationNoteUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an escalation note."""
    result = await db.execute(
        select(EscalationNote).where(
            EscalationNote.id == note_id,
            EscalationNote.escalation_id == escalation_id,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can edit
    if note.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can edit this note",
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(note, field, value)

    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{escalation_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    escalation_id: int,
    note_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an escalation note."""
    result = await db.execute(
        select(EscalationNote).where(
            EscalationNote.id == note_id,
            EscalationNote.escalation_id == escalation_id,
        )
    )
    note = result.scalar_one_or_none()

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can delete
    if note.created_by_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this note",
        )

    await db.delete(note)
    await db.commit()


# Escalation Actions


@router.post("/{escalation_id}/assign")
async def assign_escalation(
    escalation_id: int,
    user_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Assign an escalation to a user."""
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    old_assignee = escalation.assigned_to_user_id
    escalation.assigned_to_user_id = user_id

    # Create activity
    await create_activity(
        db,
        escalation_id,
        "assignment_change",
        "Escalation reassigned",
        current_user.id,
        str(old_assignee) if old_assignee else "None",
        str(user_id),
    )

    await db.commit()
    return {"status": "success", "message": "Escalation assigned"}


@router.post("/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: int,
    resolution_summary: str,
    resolution_category: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Resolve an escalation."""
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    if escalation.status in ["resolved", "closed"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Escalation is already resolved/closed",
        )

    escalation.status = "resolved"
    escalation.resolution_summary = resolution_summary
    escalation.resolution_category = resolution_category
    escalation.resolved_at = datetime.utcnow()

    # Check SLA breach
    if escalation.sla_deadline and datetime.utcnow() > escalation.sla_deadline:
        escalation.sla_breached = True

    # Create activity
    await create_activity(
        db,
        escalation_id,
        "resolved",
        f"Escalation resolved: {resolution_category}",
        current_user.id,
    )

    await db.commit()
    return {"status": "success", "message": "Escalation resolved"}


@router.post("/{escalation_id}/close")
async def close_escalation(
    escalation_id: int,
    db: DbSession,
    current_user: CurrentUser,
    customer_satisfaction: Optional[int] = None,
):
    """Close a resolved escalation."""
    result = await db.execute(select(Escalation).where(Escalation.id == escalation_id))
    escalation = result.scalar_one_or_none()

    if not escalation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Escalation not found",
        )

    if escalation.status != "resolved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only close resolved escalations",
        )

    escalation.status = "closed"
    escalation.closed_at = datetime.utcnow()
    if customer_satisfaction:
        escalation.customer_satisfaction = customer_satisfaction

    # Create activity
    await create_activity(
        db,
        escalation_id,
        "closed",
        "Escalation closed",
        current_user.id,
    )

    await db.commit()
    return {"status": "success", "message": "Escalation closed"}


# Escalation Analytics


@router.get("/analytics/summary", response_model=EscalationAnalytics)
async def get_escalation_analytics(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=1, le=365),
):
    """Get escalation analytics."""
    start_date = datetime.utcnow() - timedelta(days=days)

    # Status counts
    status_result = await db.execute(
        select(
            func.sum(case((Escalation.status == "open", 1), else_=0)).label("open"),
            func.sum(case((Escalation.status == "in_progress", 1), else_=0)).label("in_progress"),
            func.sum(case((Escalation.status == "resolved", 1), else_=0)).label("resolved"),
            func.sum(case((Escalation.status == "closed", 1), else_=0)).label("closed"),
        )
    )
    status_counts = status_result.fetchone()

    # By severity
    severity_result = await db.execute(
        select(
            Escalation.severity,
            func.count(Escalation.id),
        )
        .where(Escalation.created_at >= start_date)
        .group_by(Escalation.severity)
    )
    by_severity = {row[0]: row[1] for row in severity_result.fetchall()}

    # By type
    type_result = await db.execute(
        select(
            Escalation.escalation_type,
            func.count(Escalation.id),
        )
        .where(Escalation.created_at >= start_date)
        .group_by(Escalation.escalation_type)
    )
    by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # SLA compliance
    resolved_with_sla = await db.execute(
        select(
            func.count(Escalation.id).label("total"),
            func.sum(case((Escalation.sla_breached == False, 1), else_=0)).label("met"),
        ).where(
            Escalation.status.in_(["resolved", "closed"]),
            Escalation.created_at >= start_date,
        )
    )
    sla_data = resolved_with_sla.fetchone()
    sla_compliance = (sla_data.met / sla_data.total * 100) if sla_data.total > 0 else None

    # First response compliance
    first_response_data = await db.execute(
        select(
            func.count(Escalation.id).label("total"),
            func.sum(case((Escalation.first_response_breached == False, 1), else_=0)).label("met"),
        ).where(
            Escalation.first_response_at.isnot(None),
            Escalation.created_at >= start_date,
        )
    )
    fr_data = first_response_data.fetchone()
    first_response_compliance = (fr_data.met / fr_data.total * 100) if fr_data.total > 0 else None

    # Trend
    trend_result = await db.execute(
        select(
            func.date(Escalation.created_at).label("date"),
            func.count(Escalation.id).label("opened"),
            func.sum(case((Escalation.resolved_at.isnot(None), 1), else_=0)).label("resolved"),
        )
        .where(Escalation.created_at >= start_date)
        .group_by(func.date(Escalation.created_at))
        .order_by(func.date(Escalation.created_at))
    )
    trend = [
        {"date": str(row.date), "opened": row.opened, "resolved": row.resolved or 0} for row in trend_result.fetchall()
    ]

    # Top root causes
    root_cause_result = await db.execute(
        select(
            Escalation.root_cause_category,
            func.count(Escalation.id),
        )
        .where(
            Escalation.root_cause_category.isnot(None),
            Escalation.created_at >= start_date,
        )
        .group_by(Escalation.root_cause_category)
        .order_by(func.count(Escalation.id).desc())
        .limit(10)
    )
    top_root_causes = [{"category": row[0], "count": row[1]} for row in root_cause_result.fetchall()]

    return EscalationAnalytics(
        total_open=status_counts.open or 0,
        total_in_progress=status_counts.in_progress or 0,
        total_resolved=status_counts.resolved or 0,
        total_closed=status_counts.closed or 0,
        sla_compliance_rate=sla_compliance,
        first_response_compliance_rate=first_response_compliance,
        by_severity=by_severity,
        by_type=by_type,
        trend=trend,
        top_root_causes=top_root_causes,
    )
