"""Tickets API - Support/service ticket management."""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, text
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


def ticket_to_response(ticket: Ticket) -> dict:
    """Convert Ticket model to response dict."""
    return {
        "id": str(ticket.id),
        "customer_id": str(ticket.customer_id),
        "work_order_id": ticket.work_order_id,
        "subject": ticket.subject,
        "description": ticket.description,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "assigned_to": ticket.assigned_to,
        "resolution": ticket.resolution,
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
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_to: Optional[str] = None,
    category: Optional[str] = None,
):
    """List tickets with pagination and filtering."""
    try:
        # Base query
        query = select(Ticket)

        # Apply filters
        if customer_id:
            query = query.where(Ticket.customer_id == customer_id)

        if status:
            query = query.where(Ticket.status == status)

        if priority:
            query = query.where(Ticket.priority == priority)

        if assigned_to:
            query = query.where(Ticket.assigned_to == assigned_to)

        if category:
            query = query.where(Ticket.category == category)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Ticket.created_at.desc())

        # Execute query
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
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "error": str(e)}


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
    data = ticket_data.model_dump()

    # Convert customer_id from string to int
    data["customer_id"] = int(data["customer_id"])

    # Set created_by to current user
    data["created_by"] = current_user.email

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

    # Update only provided fields
    update_data = ticket_data.model_dump(exclude_unset=True)

    # If status changed to resolved, set resolved_at
    if update_data.get("status") == "resolved" and ticket.status != "resolved":
        update_data["resolved_at"] = datetime.utcnow()

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
