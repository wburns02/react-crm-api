from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime
import uuid
import logging
import traceback

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderResponse,
    WorkOrderListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=WorkOrderListResponse)
async def list_work_orders(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    job_type: Optional[str] = None,
    priority: Optional[str] = None,
    assigned_technician: Optional[str] = None,
    technician_id: Optional[str] = None,
    scheduled_date: Optional[str] = None,
    scheduled_date_from: Optional[datetime] = None,
    scheduled_date_to: Optional[datetime] = None,
):
    """List work orders with pagination and filtering."""
    try:
        # Base query
        query = select(WorkOrder)

        # Apply filters
        if customer_id:
            query = query.where(WorkOrder.customer_id == customer_id)
        if status_filter:
            query = query.where(WorkOrder.status == status_filter)
        if job_type:
            query = query.where(WorkOrder.job_type == job_type)
        if priority:
            query = query.where(WorkOrder.priority == priority)
        if assigned_technician:
            query = query.where(WorkOrder.assigned_technician == assigned_technician)
        if technician_id:
            query = query.where(WorkOrder.technician_id == technician_id)
        if scheduled_date:
            query = query.where(func.date(WorkOrder.scheduled_date) == scheduled_date)
        if scheduled_date_from:
            query = query.where(WorkOrder.scheduled_date >= scheduled_date_from)
        if scheduled_date_to:
            query = query.where(WorkOrder.scheduled_date <= scheduled_date_to)

        # Get total count - simple count with same filters
        count_query = select(func.count()).select_from(WorkOrder)
        if customer_id:
            count_query = count_query.where(WorkOrder.customer_id == customer_id)
        if status_filter:
            count_query = count_query.where(WorkOrder.status == status_filter)
        if job_type:
            count_query = count_query.where(WorkOrder.job_type == job_type)
        if priority:
            count_query = count_query.where(WorkOrder.priority == priority)
        if assigned_technician:
            count_query = count_query.where(WorkOrder.assigned_technician == assigned_technician)
        if technician_id:
            count_query = count_query.where(WorkOrder.technician_id == technician_id)
        if scheduled_date:
            count_query = count_query.where(func.date(WorkOrder.scheduled_date) == scheduled_date)
        if scheduled_date_from:
            count_query = count_query.where(WorkOrder.scheduled_date >= scheduled_date_from)
        if scheduled_date_to:
            count_query = count_query.where(WorkOrder.scheduled_date <= scheduled_date_to)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WorkOrder.created_at.desc())

        # Execute query
        result = await db.execute(query)
        work_orders = result.scalars().all()

        return WorkOrderListResponse(
            items=work_orders,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error in list_work_orders: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single work order by ID."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    return work_order


@router.post("", response_model=WorkOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_work_order(
    work_order_data: WorkOrderCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new work order."""
    data = work_order_data.model_dump()
    data["id"] = str(uuid.uuid4())
    work_order = WorkOrder(**data)
    db.add(work_order)
    await db.commit()
    await db.refresh(work_order)
    return work_order


@router.patch("/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: str,
    work_order_data: WorkOrderUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a work order."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    update_data = work_order_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(work_order, field, value)

    await db.commit()
    await db.refresh(work_order)
    return work_order


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_order(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a work order."""
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    await db.delete(work_order)
    await db.commit()
