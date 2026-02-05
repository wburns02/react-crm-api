"""
Public API - Work Order Endpoints

Provides public API access to work order resources with OAuth2 authentication.
"""

import logging
import uuid
from typing import Optional, Any
from datetime import datetime, date as date_type, time as time_type
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status, Query, Depends, Response
from sqlalchemy import select, func, cast, String
from pydantic import BaseModel, Field

from app.api.public.deps import PublicAPIClient, DbSession, require_scope
from app.models.work_order import WorkOrder
from app.core.rate_limit import get_public_api_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/work-orders", tags=["Public API - Work Orders"])


# ============================================================================
# Schemas (Simplified for Public API)
# ============================================================================


class PublicWorkOrderBase(BaseModel):
    """Base work order schema for public API."""

    customer_id: str
    technician_id: Optional[str] = None
    job_type: str
    status: Optional[str] = "draft"
    priority: Optional[str] = "normal"

    # Scheduling
    scheduled_date: Optional[date_type] = None
    time_window_start: Optional[time_type] = None
    time_window_end: Optional[time_type] = None
    estimated_duration_hours: Optional[float] = None

    # Service location
    service_address_line1: Optional[str] = None
    service_address_line2: Optional[str] = None
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None

    # Job details
    estimated_gallons: Optional[int] = None
    notes: Optional[str] = None

    # Assignment
    assigned_vehicle: Optional[str] = None
    assigned_technician: Optional[str] = None

    # Financial
    total_amount: Optional[Decimal] = None


class PublicWorkOrderCreate(PublicWorkOrderBase):
    """Schema for creating a work order via public API."""

    pass


class PublicWorkOrderUpdate(BaseModel):
    """Schema for updating a work order via public API."""

    customer_id: Optional[str] = None
    technician_id: Optional[str] = None
    job_type: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None

    scheduled_date: Optional[date_type] = None
    time_window_start: Optional[time_type] = None
    time_window_end: Optional[time_type] = None
    estimated_duration_hours: Optional[float] = None

    service_address_line1: Optional[str] = None
    service_address_line2: Optional[str] = None
    service_city: Optional[str] = None
    service_state: Optional[str] = None
    service_postal_code: Optional[str] = None
    service_latitude: Optional[float] = None
    service_longitude: Optional[float] = None

    estimated_gallons: Optional[int] = None
    notes: Optional[str] = None

    assigned_vehicle: Optional[str] = None
    assigned_technician: Optional[str] = None

    total_amount: Optional[Decimal] = None


class PublicWorkOrderStatusUpdate(BaseModel):
    """Schema for updating work order status."""

    status: str = Field(
        ...,
        description="New status. Valid values: draft, scheduled, confirmed, enroute, "
        "on_site, in_progress, completed, canceled, requires_followup",
    )
    notes: Optional[str] = Field(None, description="Optional status change notes")


class PublicWorkOrderResponse(PublicWorkOrderBase):
    """Schema for work order response in public API."""

    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Recurrence info
    is_recurring: Optional[bool] = False
    recurrence_frequency: Optional[str] = None
    next_recurrence_date: Optional[date_type] = None

    # Time tracking (read-only)
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class PublicWorkOrderListResponse(BaseModel):
    """Paginated work order list response."""

    items: list[PublicWorkOrderResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# Valid status values for validation
VALID_STATUSES = {
    "draft",
    "scheduled",
    "confirmed",
    "enroute",
    "on_site",
    "in_progress",
    "completed",
    "canceled",
    "requires_followup",
}

VALID_JOB_TYPES = {
    "pumping",
    "inspection",
    "repair",
    "installation",
    "emergency",
    "maintenance",
    "grease_trap",
    "camera_inspection",
}

VALID_PRIORITIES = {"low", "normal", "high", "urgent", "emergency"}


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=PublicWorkOrderListResponse,
    dependencies=[Depends(require_scope("work_orders:read"))],
    summary="List Work Orders",
    description="""
    List work orders with pagination and filtering.

    **Required Scope:** `work_orders:read` or `work_orders` or `admin`

    **Pagination:**
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)

    **Filtering:**
    - `customer_id`: Filter by customer
    - `status`: Filter by status
    - `job_type`: Filter by job type
    - `priority`: Filter by priority
    - `technician_id`: Filter by assigned technician
    - `scheduled_date`: Filter by exact scheduled date (YYYY-MM-DD)
    - `scheduled_date_from`: Filter by minimum scheduled date
    - `scheduled_date_to`: Filter by maximum scheduled date
    """,
)
async def list_work_orders(
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    job_type: Optional[str] = Query(None, description="Filter by job type"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    technician_id: Optional[str] = Query(None, description="Filter by technician ID"),
    scheduled_date: Optional[str] = Query(None, description="Filter by exact date (YYYY-MM-DD)"),
    scheduled_date_from: Optional[str] = Query(None, description="Minimum scheduled date"),
    scheduled_date_to: Optional[str] = Query(None, description="Maximum scheduled date"),
):
    """List work orders with pagination and optional filtering."""
    # Build query
    query = select(WorkOrder)

    # Apply filters
    if customer_id:
        query = query.where(WorkOrder.customer_id == customer_id)

    if status_filter:
        query = query.where(cast(WorkOrder.status, String) == status_filter)

    if job_type:
        query = query.where(cast(WorkOrder.job_type, String) == job_type)

    if priority:
        query = query.where(cast(WorkOrder.priority, String) == priority)

    if technician_id:
        query = query.where(WorkOrder.technician_id == technician_id)

    if scheduled_date:
        try:
            date_obj = date_type.fromisoformat(scheduled_date)
            query = query.where(WorkOrder.scheduled_date == date_obj)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_date",
                    "message": "scheduled_date must be in YYYY-MM-DD format",
                },
            )

    if scheduled_date_from:
        try:
            date_obj = date_type.fromisoformat(scheduled_date_from)
            query = query.where(WorkOrder.scheduled_date >= date_obj)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_date",
                    "message": "scheduled_date_from must be in YYYY-MM-DD format",
                },
            )

    if scheduled_date_to:
        try:
            date_obj = date_type.fromisoformat(scheduled_date_to)
            query = query.where(WorkOrder.scheduled_date <= date_obj)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_date",
                    "message": "scheduled_date_to must be in YYYY-MM-DD format",
                },
            )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(WorkOrder.created_at.desc())

    # Execute query
    result = await db.execute(query)
    work_orders = result.scalars().all()

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.debug(f"Work order list request by {client.client_id}: returned {len(work_orders)} of {total}")

    return PublicWorkOrderListResponse(
        items=work_orders,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(work_orders)) < total,
    )


@router.get(
    "/{work_order_id}",
    response_model=PublicWorkOrderResponse,
    dependencies=[Depends(require_scope("work_orders:read"))],
    summary="Get Work Order",
    description="""
    Get a single work order by ID.

    **Required Scope:** `work_orders:read` or `work_orders` or `admin`
    """,
)
async def get_work_order(
    work_order_id: str,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Get a single work order by ID."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Work order with ID {work_order_id} not found",
            },
        )

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.debug(f"Work order {work_order_id} retrieved by {client.client_id}")

    return work_order


@router.post(
    "",
    response_model=PublicWorkOrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("work_orders:write"))],
    summary="Create Work Order",
    description="""
    Create a new work order.

    **Required Scope:** `work_orders:write` or `work_orders` or `admin`

    **Valid job_type values:**
    - pumping, inspection, repair, installation
    - emergency, maintenance, grease_trap, camera_inspection

    **Valid priority values:**
    - low, normal, high, urgent, emergency

    **Valid status values:**
    - draft, scheduled, confirmed, enroute, on_site
    - in_progress, completed, canceled, requires_followup
    """,
)
async def create_work_order(
    work_order_data: PublicWorkOrderCreate,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Create a new work order."""
    # Validate job_type
    if work_order_data.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_job_type",
                "message": f"Invalid job_type. Must be one of: {', '.join(VALID_JOB_TYPES)}",
            },
        )

    # Validate status if provided
    if work_order_data.status and work_order_data.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_status",
                "message": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
            },
        )

    # Validate priority if provided
    if work_order_data.priority and work_order_data.priority not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_priority",
                "message": f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}",
            },
        )

    # Create work order with UUID
    data = work_order_data.model_dump()
    data["id"] = str(uuid.uuid4())
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()

    work_order = WorkOrder(**data)
    db.add(work_order)
    await db.commit()
    await db.refresh(work_order)

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.info(f"Work order created via public API: {work_order.id} by {client.client_id}")

    return work_order


@router.put(
    "/{work_order_id}",
    response_model=PublicWorkOrderResponse,
    dependencies=[Depends(require_scope("work_orders:write"))],
    summary="Update Work Order",
    description="""
    Update an existing work order.

    **Required Scope:** `work_orders:write` or `work_orders` or `admin`

    Only provided fields will be updated.
    """,
)
async def update_work_order(
    work_order_id: str,
    work_order_data: PublicWorkOrderUpdate,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Update a work order."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Work order with ID {work_order_id} not found",
            },
        )

    # Get update data
    update_data = work_order_data.model_dump(exclude_unset=True)

    # Validate job_type if being updated
    if "job_type" in update_data and update_data["job_type"] not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_job_type",
                "message": f"Invalid job_type. Must be one of: {', '.join(VALID_JOB_TYPES)}",
            },
        )

    # Validate status if being updated
    if "status" in update_data and update_data["status"] not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_status",
                "message": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
            },
        )

    # Validate priority if being updated
    if "priority" in update_data and update_data["priority"] not in VALID_PRIORITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_priority",
                "message": f"Invalid priority. Must be one of: {', '.join(VALID_PRIORITIES)}",
            },
        )

    # Apply updates
    for field, value in update_data.items():
        setattr(work_order, field, value)

    work_order.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(work_order)

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.info(f"Work order updated via public API: {work_order.id} by {client.client_id}")

    return work_order


@router.put(
    "/{work_order_id}/status",
    response_model=PublicWorkOrderResponse,
    dependencies=[Depends(require_scope("work_orders:write"))],
    summary="Update Work Order Status",
    description="""
    Update the status of a work order.

    **Required Scope:** `work_orders:write` or `work_orders` or `admin`

    **Valid status values:**
    - draft, scheduled, confirmed, enroute, on_site
    - in_progress, completed, canceled, requires_followup
    """,
)
async def update_work_order_status(
    work_order_id: str,
    status_update: PublicWorkOrderStatusUpdate,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Update work order status."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Work order with ID {work_order_id} not found",
            },
        )

    # Validate status
    if status_update.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_status",
                "message": f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
            },
        )

    old_status = work_order.status
    work_order.status = status_update.status
    work_order.updated_at = datetime.utcnow()

    # Append notes if provided
    if status_update.notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.utcnow().isoformat()
        status_note = (
            f"\n[{timestamp}] Status changed from {old_status} to {status_update.status}: {status_update.notes}"
        )
        work_order.notes = existing_notes + status_note

    await db.commit()
    await db.refresh(work_order)

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.info(
        f"Work order status updated via public API: {work_order.id} "
        f"({old_status} -> {status_update.status}) by {client.client_id}"
    )

    return work_order


@router.delete(
    "/{work_order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("work_orders:write"))],
    summary="Delete Work Order",
    description="""
    Delete a work order.

    **Required Scope:** `work_orders:write` or `work_orders` or `admin`

    Note: This performs a hard delete. Consider updating status to 'canceled' instead.
    """,
)
async def delete_work_order(
    work_order_id: str,
    db: DbSession,
    client: PublicAPIClient,
):
    """Delete a work order."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Work order with ID {work_order_id} not found",
            },
        )

    await db.delete(work_order)
    await db.commit()

    logger.info(f"Work order deleted via public API: {work_order_id} by {client.client_id}")
