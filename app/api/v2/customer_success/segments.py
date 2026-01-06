"""
Segment API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime

from app.api.deps import DbSession, CurrentUser
from app.models.customer_success import Segment, CustomerSegment
from app.schemas.customer_success.segment import (
    SegmentCreate,
    SegmentUpdate,
    SegmentResponse,
    SegmentListResponse,
    CustomerSegmentResponse,
    SegmentPreviewRequest,
    SegmentPreviewResponse,
    SegmentType,
)

router = APIRouter()


@router.get("/", response_model=SegmentListResponse)
async def list_segments(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    segment_type: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    """List segments with filtering."""
    query = select(Segment)

    if segment_type:
        query = query.where(Segment.segment_type == segment_type)
    if is_active is not None:
        query = query.where(Segment.is_active == is_active)
    if search:
        query = query.where(Segment.name.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Segment.priority.desc(), Segment.name)

    result = await db.execute(query)
    segments = result.scalars().all()

    return SegmentListResponse(
        items=segments,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{segment_id}", response_model=SegmentResponse)
async def get_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific segment."""
    result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    return segment


@router.post("/", response_model=SegmentResponse, status_code=status.HTTP_201_CREATED)
async def create_segment(
    data: SegmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new segment."""
    # Check for duplicate name
    existing = await db.execute(
        select(Segment).where(Segment.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Segment with this name already exists",
        )

    segment = Segment(
        **data.model_dump(),
        created_by_user_id=current_user.id,
        owned_by_user_id=current_user.id,
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    return segment


@router.patch("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    segment_id: int,
    data: SegmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a segment."""
    result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    update_data = data.model_dump(exclude_unset=True)

    # Check for duplicate name if updating name
    if "name" in update_data and update_data["name"] != segment.name:
        existing = await db.execute(
            select(Segment).where(Segment.name == update_data["name"])
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Segment with this name already exists",
            )

    for field, value in update_data.items():
        setattr(segment, field, value)

    await db.commit()
    await db.refresh(segment)
    return segment


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a segment."""
    result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    await db.delete(segment)
    await db.commit()


@router.get("/{segment_id}/customers")
async def list_segment_customers(
    segment_id: int,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: Optional[bool] = True,
):
    """List customers in a segment."""
    # Check segment exists
    segment_result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    if not segment_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    query = select(CustomerSegment).where(CustomerSegment.segment_id == segment_id)

    if is_active is not None:
        query = query.where(CustomerSegment.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(CustomerSegment.entered_at.desc())

    result = await db.execute(query)
    memberships = result.scalars().all()

    return {
        "items": memberships,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{segment_id}/customers/{customer_id}")
async def add_customer_to_segment(
    segment_id: int,
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Manually add a customer to a segment."""
    # Check segment exists and is static
    segment_result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = segment_result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    if segment.segment_type != SegmentType.STATIC.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only manually add customers to static segments",
        )

    # Check if already in segment
    existing = await db.execute(
        select(CustomerSegment).where(
            CustomerSegment.segment_id == segment_id,
            CustomerSegment.customer_id == customer_id,
            CustomerSegment.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer is already in this segment",
        )

    membership = CustomerSegment(
        customer_id=customer_id,
        segment_id=segment_id,
        entry_reason=reason or "Manual addition",
        entered_at=datetime.utcnow(),
    )
    db.add(membership)

    # Update segment count
    segment.customer_count = (segment.customer_count or 0) + 1

    await db.commit()
    await db.refresh(membership)

    return {"status": "success", "message": "Customer added to segment"}


@router.delete("/{segment_id}/customers/{customer_id}")
async def remove_customer_from_segment(
    segment_id: int,
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
    reason: Optional[str] = None,
):
    """Remove a customer from a segment."""
    result = await db.execute(
        select(CustomerSegment).where(
            CustomerSegment.segment_id == segment_id,
            CustomerSegment.customer_id == customer_id,
            CustomerSegment.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer is not in this segment",
        )

    membership.is_active = False
    membership.exited_at = datetime.utcnow()
    membership.exit_reason = reason or "Manual removal"

    # Update segment count
    segment_result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = segment_result.scalar_one_or_none()
    if segment:
        segment.customer_count = max(0, (segment.customer_count or 1) - 1)

    await db.commit()

    return {"status": "success", "message": "Customer removed from segment"}


@router.post("/preview", response_model=SegmentPreviewResponse)
async def preview_segment(
    request: SegmentPreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Preview customers that would match segment rules."""
    # In a real implementation, this would evaluate the rules against the customer database
    # For now, return a placeholder response
    return SegmentPreviewResponse(
        total_matches=0,
        sample_customers=[],
        estimated_arr=None,
        avg_health_score=None,
    )


@router.post("/{segment_id}/evaluate")
async def evaluate_segment(
    segment_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Trigger evaluation of a dynamic segment."""
    result = await db.execute(
        select(Segment).where(Segment.id == segment_id)
    )
    segment = result.scalar_one_or_none()

    if not segment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Segment not found",
        )

    if segment.segment_type != SegmentType.DYNAMIC.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only evaluate dynamic segments",
        )

    # In a real implementation, this would queue a background job
    return {
        "status": "accepted",
        "message": "Segment evaluation queued",
        "segment_id": segment_id,
    }
