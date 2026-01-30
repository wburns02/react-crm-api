from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, cast, String, text, and_, or_
from typing import Optional
from datetime import datetime, date as date_type
from pydantic import BaseModel
import uuid
import logging
import traceback

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.services.commission_service import auto_create_commission
from app.schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderResponse,
    WorkOrderListResponse,
    WorkOrderCursorResponse,
)
from app.schemas.pagination import decode_cursor, encode_cursor
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# PostgreSQL ENUM fields that need explicit type casting
ENUM_FIELDS = {"status", "job_type", "priority"}


def work_order_with_customer_name(wo: WorkOrder, customer: Optional[Customer]) -> dict:
    """Convert WorkOrder to dict with customer_name populated from Customer JOIN."""
    customer_name = None
    if customer:
        first = customer.first_name or ""
        last = customer.last_name or ""
        customer_name = f"{first} {last}".strip() or None

    return {
        "id": wo.id,
        "customer_id": wo.customer_id,
        "customer_name": customer_name,
        "technician_id": wo.technician_id,
        "job_type": str(wo.job_type) if wo.job_type else None,
        "status": str(wo.status) if wo.status else "draft",
        "priority": str(wo.priority) if wo.priority else "normal",
        "scheduled_date": wo.scheduled_date,
        "time_window_start": wo.time_window_start,
        "time_window_end": wo.time_window_end,
        "estimated_duration_hours": wo.estimated_duration_hours,
        "service_address_line1": wo.service_address_line1,
        "service_address_line2": wo.service_address_line2,
        "service_city": wo.service_city,
        "service_state": wo.service_state,
        "service_postal_code": wo.service_postal_code,
        "service_latitude": wo.service_latitude,
        "service_longitude": wo.service_longitude,
        "estimated_gallons": wo.estimated_gallons,
        "notes": wo.notes,
        "internal_notes": wo.internal_notes,
        "is_recurring": wo.is_recurring,
        "recurrence_frequency": wo.recurrence_frequency,
        "next_recurrence_date": wo.next_recurrence_date,
        "checklist": wo.checklist,
        "assigned_vehicle": wo.assigned_vehicle,
        "assigned_technician": wo.assigned_technician,
        "total_amount": wo.total_amount,
        "created_at": wo.created_at,
        "updated_at": wo.updated_at,
        "actual_start_time": wo.actual_start_time,
        "actual_end_time": wo.actual_end_time,
        "travel_start_time": wo.travel_start_time,
        "travel_end_time": wo.travel_end_time,
        "break_minutes": wo.break_minutes,
        "total_labor_minutes": wo.total_labor_minutes,
        "total_travel_minutes": wo.total_travel_minutes,
        "is_clocked_in": wo.is_clocked_in,
        "clock_in_gps_lat": wo.clock_in_gps_lat,
        "clock_in_gps_lon": wo.clock_in_gps_lon,
        "clock_out_gps_lat": wo.clock_out_gps_lat,
        "clock_out_gps_lon": wo.clock_out_gps_lon,
    }


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
    """List work orders with pagination, filtering, and real customer names."""
    try:
        # Base query with LEFT JOIN to Customer for real customer names
        query = select(WorkOrder, Customer).outerjoin(Customer, WorkOrder.customer_id == Customer.id)

        # Apply filters
        if customer_id:
            query = query.where(WorkOrder.customer_id == customer_id)
        if status_filter:
            # Cast status column to string for comparison (handles PostgreSQL ENUM)
            query = query.where(cast(WorkOrder.status, String) == status_filter)
        if job_type:
            query = query.where(cast(WorkOrder.job_type, String) == job_type)
        if priority:
            query = query.where(cast(WorkOrder.priority, String) == priority)
        if assigned_technician:
            query = query.where(WorkOrder.assigned_technician == assigned_technician)
        if technician_id:
            query = query.where(WorkOrder.technician_id == technician_id)
        if scheduled_date:
            # Parse string to date object for proper comparison
            try:
                date_obj = date_type.fromisoformat(scheduled_date)
                query = query.where(WorkOrder.scheduled_date == date_obj)
            except ValueError:
                pass  # Invalid date format, skip filter
        if scheduled_date_from:
            query = query.where(WorkOrder.scheduled_date >= scheduled_date_from)
        if scheduled_date_to:
            query = query.where(WorkOrder.scheduled_date <= scheduled_date_to)

        # Get total count - simple count with same filters
        count_query = select(func.count()).select_from(WorkOrder)
        if customer_id:
            count_query = count_query.where(WorkOrder.customer_id == customer_id)
        if status_filter:
            count_query = count_query.where(cast(WorkOrder.status, String) == status_filter)
        if job_type:
            count_query = count_query.where(cast(WorkOrder.job_type, String) == job_type)
        if priority:
            count_query = count_query.where(cast(WorkOrder.priority, String) == priority)
        if assigned_technician:
            count_query = count_query.where(WorkOrder.assigned_technician == assigned_technician)
        if technician_id:
            count_query = count_query.where(WorkOrder.technician_id == technician_id)
        if scheduled_date:
            try:
                date_obj = date_type.fromisoformat(scheduled_date)
                count_query = count_query.where(WorkOrder.scheduled_date == date_obj)
            except ValueError:
                pass
        if scheduled_date_from:
            count_query = count_query.where(WorkOrder.scheduled_date >= scheduled_date_from)
        if scheduled_date_to:
            count_query = count_query.where(WorkOrder.scheduled_date <= scheduled_date_to)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(WorkOrder.created_at.desc())

        # Execute query - returns tuples of (WorkOrder, Customer)
        result = await db.execute(query)
        rows = result.all()

        # Convert to dicts with customer_name populated
        items = [work_order_with_customer_name(wo, customer) for wo, customer in rows]

        return WorkOrderListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Error in list_work_orders: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/cursor", response_model=WorkOrderCursorResponse)
async def list_work_orders_cursor(
    db: DbSession,
    current_user: CurrentUser,
    cursor: Optional[str] = None,
    page_size: int = Query(20, ge=1, le=100),
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
    """List work orders with cursor-based pagination (efficient for large datasets).

    Uses cursor pagination instead of offset pagination for better performance
    when paginating through large result sets.
    """
    try:
        # Base query with LEFT JOIN to Customer for real customer names
        query = select(WorkOrder, Customer).outerjoin(Customer, WorkOrder.customer_id == Customer.id)

        # Apply filters
        if customer_id:
            query = query.where(WorkOrder.customer_id == customer_id)
        if status_filter:
            query = query.where(cast(WorkOrder.status, String) == status_filter)
        if job_type:
            query = query.where(cast(WorkOrder.job_type, String) == job_type)
        if priority:
            query = query.where(cast(WorkOrder.priority, String) == priority)
        if assigned_technician:
            query = query.where(WorkOrder.assigned_technician == assigned_technician)
        if technician_id:
            query = query.where(WorkOrder.technician_id == technician_id)
        if scheduled_date:
            try:
                date_obj = date_type.fromisoformat(scheduled_date)
                query = query.where(WorkOrder.scheduled_date == date_obj)
            except ValueError:
                pass
        if scheduled_date_from:
            query = query.where(WorkOrder.scheduled_date >= scheduled_date_from)
        if scheduled_date_to:
            query = query.where(WorkOrder.scheduled_date <= scheduled_date_to)

        # Apply cursor filter if provided
        if cursor:
            try:
                cursor_id, cursor_ts = decode_cursor(cursor)
                # Descending order: get items BEFORE the cursor
                if cursor_ts:
                    cursor_filter = or_(
                        WorkOrder.created_at < cursor_ts,
                        and_(WorkOrder.created_at == cursor_ts, WorkOrder.id < cursor_id),
                    )
                else:
                    cursor_filter = WorkOrder.id < cursor_id
                query = query.where(cursor_filter)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid cursor format")

        # Order by created_at descending, then id for stable pagination
        query = query.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())

        # Fetch one extra to determine if there are more results
        query = query.limit(page_size + 1)

        result = await db.execute(query)
        rows = result.all()

        # Check if there are more results
        has_more = len(rows) > page_size
        rows = rows[:page_size]  # Trim to requested page size

        # Convert to dicts with customer_name populated
        items = [work_order_with_customer_name(wo, customer) for wo, customer in rows]

        # Build next cursor from last item
        next_cursor = None
        if has_more and rows:
            last_wo, _ = rows[-1]
            next_cursor = encode_cursor(last_wo.id, last_wo.created_at)

        return WorkOrderCursorResponse(
            items=items,
            next_cursor=next_cursor,
            has_more=has_more,
            total=None,  # Omit total for cursor pagination (expensive to compute)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in list_work_orders_cursor: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{work_order_id}", response_model=WorkOrderResponse)
async def get_work_order(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single work order by ID with customer name."""
    # JOIN with Customer to get real customer name
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.id == work_order_id)
    )
    result = await db.execute(query)
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    work_order, customer = row
    return work_order_with_customer_name(work_order, customer)


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

    # Broadcast work order created event via WebSocket
    await manager.broadcast_event(
        event_type="work_order.created",
        data={
            "id": work_order.id,
            "customer_id": str(work_order.customer_id),
            "job_type": str(work_order.job_type) if work_order.job_type else None,
            "status": str(work_order.status) if work_order.status else None,
            "priority": str(work_order.priority) if work_order.priority else None,
            "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
            "assigned_technician": work_order.assigned_technician,
        },
    )

    return work_order


@router.patch("/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: str,
    work_order_data: WorkOrderUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a work order."""
    # First check if work order exists
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    update_data = work_order_data.model_dump(exclude_unset=True)

    if not update_data:
        return work_order

    # Track status change for WebSocket event
    old_status = str(work_order.status) if work_order.status else None
    old_technician = work_order.assigned_technician

    try:
        # Use SQLAlchemy ORM update - handles ENUM types correctly
        for field, value in update_data.items():
            setattr(work_order, field, value)

        # Update timestamp
        work_order.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(work_order)
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating work order {work_order_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Determine the type of update for WebSocket event
    new_status = str(work_order.status) if work_order.status else None
    new_technician = work_order.assigned_technician

    # Broadcast appropriate WebSocket events
    event_data = {
        "id": work_order.id,
        "customer_id": str(work_order.customer_id),
        "job_type": str(work_order.job_type) if work_order.job_type else None,
        "status": new_status,
        "priority": str(work_order.priority) if work_order.priority else None,
        "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
        "assigned_technician": new_technician,
        "updated_fields": list(update_data.keys()),
    }

    # Status change event
    if old_status != new_status:
        await manager.broadcast_event(
            event_type="work_order.status_changed",
            data={
                **event_data,
                "old_status": old_status,
                "new_status": new_status,
            },
        )

    # Technician assignment event
    if old_technician != new_technician:
        await manager.broadcast_event(
            event_type="work_order.assigned",
            data={
                **event_data,
                "old_technician": old_technician,
                "new_technician": new_technician,
            },
        )

    # General update event (always sent)
    await manager.broadcast_event(
        event_type="work_order.updated",
        data=event_data,
    )

    # Schedule change event (when schedule-related fields change)
    schedule_fields = {"scheduled_date", "time_window_start", "time_window_end", "assigned_technician"}
    if schedule_fields.intersection(update_data.keys()):
        await manager.broadcast_event(
            event_type="schedule.updated",
            data={
                "work_order_id": work_order.id,
                "customer_id": str(work_order.customer_id),
                "scheduled_date": work_order.scheduled_date.isoformat() if work_order.scheduled_date else None,
                "time_window_start": str(work_order.time_window_start) if work_order.time_window_start else None,
                "time_window_end": str(work_order.time_window_end) if work_order.time_window_end else None,
                "assigned_technician": new_technician,
                "updated_fields": list(schedule_fields.intersection(update_data.keys())),
            },
        )

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


class WorkOrderCompleteRequest(BaseModel):
    """Request to complete a work order."""

    dump_site_id: Optional[str] = None
    notes: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@router.post("/{work_order_id}/complete")
async def complete_work_order(
    work_order_id: str,
    request: WorkOrderCompleteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Complete a work order and auto-create commission.

    This endpoint marks a work order as completed and automatically creates
    a commission record for the assigned technician based on job type and
    configured commission rates.

    For pumping and grease_trap jobs, a dump_site_id should be provided to
    calculate dump fee deductions from the commission.
    """
    result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
    work_order = result.scalar_one_or_none()

    if not work_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    if str(work_order.status) == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Work order is already completed",
        )

    # Update work order status
    work_order.status = "completed"
    work_order.actual_end_time = datetime.now()

    if request.latitude and request.longitude:
        work_order.clock_out_gps_lat = request.latitude
        work_order.clock_out_gps_lon = request.longitude

    if request.notes:
        existing_notes = work_order.notes or ""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        work_order.notes = f"{existing_notes}\n[{timestamp}] Completion: {request.notes}".strip()

    # Calculate labor minutes if start time exists
    if work_order.actual_start_time:
        duration = datetime.now() - work_order.actual_start_time
        work_order.total_labor_minutes = int(duration.total_seconds() / 60)

    # Auto-create commission
    commission = await auto_create_commission(
        db=db,
        work_order=work_order,
        dump_site_id=request.dump_site_id,
    )

    # Commit changes - must happen before any potential exceptions
    await db.commit()

    # Store values before any potential errors
    wo_id = work_order.id
    labor_mins = work_order.total_labor_minutes
    tech_id = work_order.technician_id
    cust_id = work_order.customer_id
    comm_id = str(commission.id) if commission else None
    comm_amount = float(commission.commission_amount) if commission else None
    comm_status = commission.status if commission else None
    comm_job_type = commission.job_type if commission else None
    comm_rate = commission.rate if commission else None

    # Get customer name (in try block to not affect commit)
    customer_name = None
    try:
        if cust_id:
            cust_result = await db.execute(select(Customer).where(Customer.id == cust_id))
            customer = cust_result.scalar_one_or_none()
            if customer:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()
    except Exception as e:
        logger.warning(f"Failed to get customer name: {e}")

    # Broadcast WebSocket event (non-blocking, errors don't affect response)
    try:
        await manager.broadcast_event(
            event_type="work_order.completed",
            data={
                "id": wo_id,
                "status": "completed",
                "technician_id": tech_id,
                "commission_id": comm_id,
                "commission_amount": comm_amount,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to broadcast WebSocket event: {e}")

    return {
        "id": wo_id,
        "status": "completed",
        "customer_name": customer_name,
        "labor_minutes": labor_mins,
        "commission": {
            "id": comm_id,
            "amount": comm_amount,
            "status": comm_status,
            "job_type": comm_job_type,
            "rate": comm_rate,
        }
        if commission
        else None,
    }
