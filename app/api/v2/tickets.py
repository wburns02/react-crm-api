"""Tickets API - Internal project/feature ticket management with RICE scoring."""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_
from typing import Optional
from datetime import datetime
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.ticket import Ticket
from app.schemas.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    TicketListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def calculate_rice_score(reach: float, impact: float, confidence: float, effort: float) -> float:
    """Calculate RICE score: (Reach * Impact * Confidence%) / Effort."""
    if not effort or effort == 0:
        return 0.0
    return (reach * impact * (confidence / 100.0)) / effort


def ticket_to_response(ticket: Ticket) -> dict:
    """Convert Ticket model to response dict."""
    # Use title, falling back to subject for legacy data
    title = ticket.title or ticket.subject or "Untitled"
    return {
        "id": str(ticket.id),
        "title": title,
        "description": ticket.description,
        "type": ticket.type or ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "rice_score": ticket.rice_score,
        "reach": ticket.reach,
        "impact": ticket.impact,
        "confidence": ticket.confidence,
        "effort": ticket.effort,
        "assigned_to": ticket.assigned_to,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "created_by": ticket.created_by,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


@router.get("")
async def list_tickets(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
):
    """List tickets with pagination and filtering."""
    try:
        query = select(Ticket)

        # Search in title, subject, description
        if search:
            search_term = f"%{search}%"
            query = query.where(
                or_(
                    Ticket.title.ilike(search_term),
                    Ticket.subject.ilike(search_term),
                    Ticket.description.ilike(search_term),
                )
            )

        if type:
            query = query.where(or_(Ticket.type == type, Ticket.category == type))

        if status:
            query = query.where(Ticket.status == status)

        if priority:
            query = query.where(Ticket.priority == priority)

        if assigned_to:
            query = query.where(Ticket.assigned_to == assigned_to)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Ticket.created_at.desc())

        result = await db.execute(query)
        tickets = result.scalars().all()

        return {
            "items": [ticket_to_response(t) for t in tickets],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error in list_tickets: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(
    ticket_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single ticket by ID."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    return ticket_to_response(ticket)


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_data: TicketCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new ticket."""
    data = ticket_data.model_dump(exclude_none=True)

    # Calculate RICE score if all components provided
    reach = data.get("reach")
    impact = data.get("impact")
    confidence = data.get("confidence")
    effort = data.get("effort")
    if reach is not None and impact is not None and confidence is not None and effort is not None:
        data["rice_score"] = calculate_rice_score(reach, impact, confidence, effort)

    # Set created_by to current user
    data["created_by"] = current_user.email

    # Also set legacy subject field for backwards compatibility
    data["subject"] = data.get("title", "")

    ticket = Ticket(**data)
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket_to_response(ticket)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: str,
    ticket_data: TicketUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a ticket."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    update_data = ticket_data.model_dump(exclude_unset=True)

    # If status changed to resolved, set resolved_at
    if update_data.get("status") == "resolved" and ticket.status != "resolved":
        update_data["resolved_at"] = datetime.utcnow()

    # Recalculate RICE score if any component changed
    reach = update_data.get("reach", ticket.reach)
    impact = update_data.get("impact", ticket.impact)
    confidence = update_data.get("confidence", ticket.confidence)
    effort = update_data.get("effort", ticket.effort)
    if reach is not None and impact is not None and confidence is not None and effort is not None:
        update_data["rice_score"] = calculate_rice_score(reach, impact, confidence, effort)

    # Keep subject in sync with title
    if "title" in update_data:
        update_data["subject"] = update_data["title"]

    for field, value in update_data.items():
        setattr(ticket, field, value)

    await db.commit()
    await db.refresh(ticket)
    return ticket_to_response(ticket)


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(
    ticket_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a ticket."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    await db.delete(ticket)
    await db.commit()
