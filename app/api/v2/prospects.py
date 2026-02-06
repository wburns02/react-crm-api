"""
Prospects API - Customers in prospect stages (not yet won).
Prospects are customers with prospect_stage != 'won'.
"""

from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)

router = APIRouter()

# Prospect stages (not won)
PROSPECT_STAGES = ["new_lead", "contacted", "qualified", "quoted", "negotiation", "lost"]


@router.get("/", response_model=CustomerListResponse)
async def list_prospects(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    stage: Optional[str] = None,
    lead_source: Optional[str] = None,
):
    """List prospects (customers not yet won) with pagination and filtering."""
    # Base query - filter to prospect stages only (exclude 'won')
    # Also exclude soft-deleted prospects (is_active=False)
    query = select(Customer).where(
        or_(Customer.prospect_stage.in_(PROSPECT_STAGES), Customer.prospect_stage.is_(None)),
        Customer.is_active == True,  # Exclude soft-deleted prospects
    )

    # Apply filters
    if search:
        search_filter = or_(
            Customer.first_name.ilike(f"%{search}%"),
            Customer.last_name.ilike(f"%{search}%"),
            Customer.email.ilike(f"%{search}%"),
            Customer.phone.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    if stage:
        query = query.where(Customer.prospect_stage == stage)

    if lead_source:
        query = query.where(Customer.lead_source == lead_source)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Customer.created_at.desc())

    # Execute query
    result = await db.execute(query)
    prospects = result.scalars().all()

    return CustomerListResponse(
        items=prospects,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{prospect_id}", response_model=CustomerResponse)
async def get_prospect(
    prospect_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single prospect by ID."""
    result = await db.execute(select(Customer).where(Customer.id == prospect_id))
    prospect = result.scalar_one_or_none()

    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found",
        )

    return prospect


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_prospect(
    prospect_data: CustomerCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new prospect."""
    data = prospect_data.model_dump()
    # Default to new_lead stage if not specified
    if not data.get("prospect_stage"):
        data["prospect_stage"] = "new_lead"

    prospect = Customer(**data)
    db.add(prospect)
    await db.commit()
    await db.refresh(prospect)
    return prospect


@router.patch("/{prospect_id}", response_model=CustomerResponse)
async def update_prospect(
    prospect_id: UUID,
    prospect_data: CustomerUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a prospect."""
    result = await db.execute(select(Customer).where(Customer.id == prospect_id))
    prospect = result.scalar_one_or_none()

    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found",
        )

    # Update only provided fields
    update_data = prospect_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(prospect, field, value)

    await db.commit()
    await db.refresh(prospect)
    return prospect


@router.patch("/{prospect_id}/stage", response_model=CustomerResponse)
async def update_prospect_stage(
    prospect_id: UUID,
    stage: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a prospect's stage (for drag-drop in pipeline view)."""
    result = await db.execute(select(Customer).where(Customer.id == prospect_id))
    prospect = result.scalar_one_or_none()

    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found",
        )

    prospect.prospect_stage = stage
    await db.commit()
    await db.refresh(prospect)
    return prospect


@router.delete("/{prospect_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prospect(
    prospect_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Delete a prospect (soft delete).

    Sets is_active=False instead of hard deleting to preserve
    related records (work orders, invoices, messages, etc.).
    """
    result = await db.execute(select(Customer).where(Customer.id == prospect_id))
    prospect = result.scalar_one_or_none()

    if not prospect:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prospect not found",
        )

    # Soft delete - set is_active=False to preserve related records
    # Hard delete would fail due to foreign key constraints from
    # work_orders, invoices, messages, equipment, etc.
    prospect.is_active = False
    await db.commit()
