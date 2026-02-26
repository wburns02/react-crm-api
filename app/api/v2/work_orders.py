from fastapi import APIRouter, HTTPException, status, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, cast, String, text, and_, or_, desc
from typing import Optional, List
from datetime import datetime, date as date_type
from pydantic import BaseModel, Field
import uuid
import logging
import traceback

from app.api.deps import DbSession, CurrentUser, EntityCtx
from app.models.work_order import WorkOrder
from app.models.work_order_audit import WorkOrderAuditLog
from app.models.customer import Customer
from app.models.technician import Technician
from app.services.commission_service import auto_create_commission
from app.services.cache_service import get_cache_service, TTL
from app.schemas.work_order import (
    WorkOrderCreate,
    WorkOrderUpdate,
    WorkOrderResponse,
    WorkOrderListResponse,
    WorkOrderCursorResponse,
    WorkOrderAuditLogResponse,
)
from app.schemas.pagination import decode_cursor, encode_cursor
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()

# PostgreSQL ENUM fields that need explicit type casting
ENUM_FIELDS = {"status", "job_type", "priority"}


@router.post("/fix-table")
async def fix_work_orders_table(db: DbSession, current_user: CurrentUser):
    """Add work_order_number column and backfill existing work orders."""
    try:
        # Check if column exists
        result = await db.execute(
            text(
                """SELECT column_name FROM information_schema.columns
                WHERE table_name = 'work_orders' AND column_name = 'work_order_number'"""
            )
        )
        exists = result.fetchone()

        if not exists:
            logger.info("Adding work_order_number column...")
            await db.execute(
                text("ALTER TABLE work_orders ADD COLUMN work_order_number VARCHAR(20)")
            )
            await db.commit()

            # Backfill existing work orders
            logger.info("Backfilling work order numbers...")
            await db.execute(
                text("""
                    WITH numbered AS (
                        SELECT id, ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) as rn
                        FROM work_orders
                        WHERE work_order_number IS NULL
                    )
                    UPDATE work_orders wo
                    SET work_order_number = 'WO-' || LPAD(n.rn::text, 6, '0')
                    FROM numbered n
                    WHERE wo.id = n.id
                """)
            )
            await db.commit()

            # Add index
            try:
                await db.execute(
                    text("CREATE UNIQUE INDEX IF NOT EXISTS ix_work_orders_number ON work_orders(work_order_number)")
                )
                await db.commit()
            except Exception:
                pass

            return {"status": "success", "message": "work_order_number column added and backfilled"}
        else:
            # Check for any NULL values and backfill them
            result = await db.execute(
                text("SELECT COUNT(*) FROM work_orders WHERE work_order_number IS NULL")
            )
            null_count = result.scalar()

            if null_count and null_count > 0:
                logger.info(f"Backfilling {null_count} work orders with NULL work_order_number...")
                await db.execute(
                    text("""
                        WITH max_num AS (
                            SELECT COALESCE(MAX(CAST(REPLACE(work_order_number, 'WO-', '') AS INTEGER)), 0) as max_n
                            FROM work_orders
                            WHERE work_order_number IS NOT NULL
                        ),
                        numbered AS (
                            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at NULLS LAST, id) as rn
                            FROM work_orders
                            WHERE work_order_number IS NULL
                        )
                        UPDATE work_orders wo
                        SET work_order_number = 'WO-' || LPAD((n.rn + (SELECT max_n FROM max_num))::text, 6, '0')
                        FROM numbered n
                        WHERE wo.id = n.id
                    """)
                )
                await db.commit()
                return {"status": "success", "message": f"Backfilled {null_count} work orders"}

            return {"status": "success", "message": "Column already exists, no action needed"}

    except Exception as e:
        logger.error(f"Error fixing work_orders table: {e}")
        return {"status": "error", "message": str(e)}


def work_order_with_customer_name(wo: WorkOrder, customer: Optional[Customer]) -> dict:
    """Convert WorkOrder to dict with customer_name populated from Customer JOIN."""
    customer_name = None
    customer_phone = None
    if customer:
        first = customer.first_name or ""
        last = customer.last_name or ""
        customer_name = f"{first} {last}".strip() or None
        customer_phone = customer.phone or None

    return {
        "id": wo.id,
        "work_order_number": wo.work_order_number,
        "customer_id": wo.customer_id,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "technician_id": wo.technician_id,
        "job_type": str(wo.job_type) if wo.job_type else None,
        "status": str(wo.status) if wo.status else "draft",
        "priority": str(wo.priority) if wo.priority else "normal",
        "scheduled_date": wo.scheduled_date,
        "time_window_start": wo.time_window_start,
        "time_window_end": wo.time_window_end,
        "estimated_duration_hours": wo.estimated_duration_hours or {
            "inspection": 0.5, "pumping": 1.0, "repair": 2.0,
            "installation": 4.0, "maintenance": 1.0, "grease_trap": 1.0, "emergency": 2.0,
        }.get(str(wo.job_type) if wo.job_type else "", 1.0),
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
        "system_type": wo.system_type or "conventional",
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
    entity: EntityCtx,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    customer_id: Optional[str] = None,
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
    # Check cache first
    cache = get_cache_service()
    cache_key = f"workorders:list:{page}:{page_size}:{customer_id}:{status_filter}:{job_type}:{priority}:{assigned_technician}:{technician_id}:{scheduled_date}:{scheduled_date_from}:{scheduled_date_to}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

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

        # Multi-entity filtering
        if entity:
            if entity.is_default:
                query = query.where(or_(WorkOrder.entity_id == entity.id, WorkOrder.entity_id == None))
            else:
                query = query.where(WorkOrder.entity_id == entity.id)

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
        if entity:
            if entity.is_default:
                count_query = count_query.where(or_(WorkOrder.entity_id == entity.id, WorkOrder.entity_id == None))
            else:
                count_query = count_query.where(WorkOrder.entity_id == entity.id)

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

        response = WorkOrderListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )
        await cache.set(cache_key, jsonable_encoder(response), ttl=TTL.SHORT)
        return response
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
    customer_id: Optional[str] = None,
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


# ============================================
# Bulk Operations
# ============================================

VALID_STATUSES = {"draft", "scheduled", "confirmed", "enroute", "on_site", "in_progress", "completed", "canceled", "requires_followup"}
MAX_BULK_SIZE = 200


class BulkStatusRequest(BaseModel):
    """Bulk update status for multiple work orders."""
    ids: List[str] = Field(..., max_length=MAX_BULK_SIZE)
    status: str


class BulkAssignRequest(BaseModel):
    """Bulk assign technician to multiple work orders."""
    ids: List[str] = Field(..., max_length=MAX_BULK_SIZE)
    assigned_technician: Optional[str] = None
    technician_id: Optional[str] = None


class BulkDeleteRequest(BaseModel):
    """Bulk delete multiple work orders."""
    ids: List[str] = Field(..., max_length=MAX_BULK_SIZE)


class BulkResult(BaseModel):
    """Result of a bulk operation."""
    success_count: int
    failed_count: int
    errors: List[dict] = []


@router.patch("/bulk/status")
async def bulk_update_status(
    request: BulkStatusRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> BulkResult:
    """Bulk update work order status. Max 200 at a time."""
    if request.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {request.status}")

    success = 0
    errors = []

    for wo_id in request.ids:
        try:
            result = await db.execute(select(WorkOrder).where(WorkOrder.id == wo_id))
            wo = result.scalar_one_or_none()
            if not wo:
                errors.append({"id": wo_id, "error": "Not found"})
                continue
            wo.status = request.status
            wo.updated_at = datetime.utcnow()
            success += 1
        except Exception as e:
            errors.append({"id": wo_id, "error": str(e)})

    await db.commit()

    # Invalidate cache
    cache = get_cache_service()
    await cache.delete_pattern("work-orders:*")

    # Broadcast WebSocket event
    await manager.broadcast({
        "type": "work_order_update",
        "data": {"count": success, "status": request.status},
    })

    return BulkResult(success_count=success, failed_count=len(errors), errors=errors)


@router.patch("/bulk/assign")
async def bulk_assign_technician(
    request: BulkAssignRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> BulkResult:
    """Bulk assign a technician to multiple work orders. Max 200."""
    # Resolve technician_id from name if not provided
    tech_id = None
    if request.technician_id:
        tech_id = request.technician_id
    elif request.assigned_technician:
        parts = request.assigned_technician.strip().split()
        if len(parts) >= 2:
            tech_result = await db.execute(
                select(Technician).where(
                    func.lower(Technician.first_name) == parts[0].lower(),
                    func.lower(Technician.last_name) == parts[-1].lower(),
                )
            )
            tech = tech_result.scalar_one_or_none()
            if tech:
                tech_id = str(tech.id)

    success = 0
    errors = []

    for wo_id in request.ids:
        try:
            result = await db.execute(select(WorkOrder).where(WorkOrder.id == wo_id))
            wo = result.scalar_one_or_none()
            if not wo:
                errors.append({"id": wo_id, "error": "Not found"})
                continue
            wo.assigned_technician = request.assigned_technician
            if tech_id:
                wo.technician_id = tech_id
            wo.updated_at = datetime.utcnow()
            success += 1
        except Exception as e:
            errors.append({"id": wo_id, "error": str(e)})

    await db.commit()

    cache = get_cache_service()
    await cache.delete_pattern("work-orders:*")

    await manager.broadcast({
        "type": "dispatch_update",
        "data": {"count": success, "technician": request.assigned_technician},
    })

    return BulkResult(success_count=success, failed_count=len(errors), errors=errors)


@router.delete("/bulk")
async def bulk_delete_work_orders(
    request: BulkDeleteRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> BulkResult:
    """Bulk delete work orders. Max 200."""
    success = 0
    errors = []

    for wo_id in request.ids:
        try:
            result = await db.execute(select(WorkOrder).where(WorkOrder.id == wo_id))
            wo = result.scalar_one_or_none()
            if not wo:
                errors.append({"id": wo_id, "error": "Not found"})
                continue
            await db.delete(wo)
            success += 1
        except Exception as e:
            errors.append({"id": wo_id, "error": str(e)})

    await db.commit()

    cache = get_cache_service()
    await cache.delete_pattern("work-orders:*")

    return BulkResult(success_count=success, failed_count=len(errors), errors=errors)


# ============================================
# Route Optimization
# ============================================

import math


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in miles."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _nearest_neighbor_route(
    jobs: list[dict], start_lat: float, start_lng: float
) -> tuple[list[dict], float]:
    """Greedy nearest-neighbor TSP approximation."""
    remaining = list(jobs)
    ordered = []
    current_lat, current_lng = start_lat, start_lng
    total_dist = 0.0

    while remaining:
        nearest = min(
            remaining,
            key=lambda j: _haversine_miles(
                current_lat, current_lng, j["lat"], j["lng"]
            ),
        )
        dist = _haversine_miles(current_lat, current_lng, nearest["lat"], nearest["lng"])
        total_dist += dist
        current_lat, current_lng = nearest["lat"], nearest["lng"]
        ordered.append(nearest)
        remaining.remove(nearest)

    return ordered, total_dist


def _address_to_approx_coords(address: str) -> tuple[float, float]:
    """
    Deterministic address-based approximation for San Marcos TX area.
    Used when no stored coordinates are available.
    """
    h = hash(address) % 10000
    lat = 29.8 + (h % 100) / 500  # ~29.8 to 30.0
    lng = -97.9 + (h // 100 % 100) / 500  # ~-97.9 to -97.7
    return lat, lng


class RouteOptimizeRequest(BaseModel):
    job_ids: list[str]
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    start_address: Optional[str] = "105 S Comanche St, San Marcos, TX 78666"


class RouteOptimizeResponse(BaseModel):
    ordered_job_ids: list[str]
    total_distance_miles: float
    estimated_drive_minutes: int
    waypoints: list[dict]  # [{job_id, address, lat, lng}]


@router.post("/optimize-route", response_model=RouteOptimizeResponse)
async def optimize_route(
    request: RouteOptimizeRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Given a list of job IDs and a start location, return the jobs
    reordered by nearest-neighbor haversine distance.

    Input: { "job_ids": [...], "start_lat": 30.0, "start_lng": -97.0 }
    OR: { "job_ids": [...], "start_address": "123 Main St, San Marcos TX" }

    Output: {
        "ordered_job_ids": [...],
        "total_distance_miles": 47.3,
        "estimated_drive_minutes": 68,
        "waypoints": [{"job_id": ..., "address": ..., "lat": ..., "lng": ...}]
    }
    """
    if not request.job_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_ids must not be empty",
        )

    # Determine start coordinates
    if request.start_lat is not None and request.start_lng is not None:
        start_lat = request.start_lat
        start_lng = request.start_lng
    else:
        addr = request.start_address or "105 S Comanche St, San Marcos, TX 78666"
        start_lat, start_lng = _address_to_approx_coords(addr)

    # Fetch work orders with customer data for coordinates
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.id.in_(request.job_ids))
    )
    result = await db.execute(query)
    rows = result.all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No work orders found for the provided job_ids",
        )

    # Build job dicts with coordinates
    jobs = []
    for wo, customer in rows:
        # Prefer work order service coords, then customer coords, then hash approximation
        lat = None
        lng = None

        if wo.service_latitude is not None and wo.service_longitude is not None:
            lat = float(wo.service_latitude)
            lng = float(wo.service_longitude)
        elif customer and customer.latitude is not None and customer.longitude is not None:
            lat = float(customer.latitude)
            lng = float(customer.longitude)
        else:
            # Build address string for hash approximation
            address_parts = [
                wo.service_address_line1 or (customer.address_line1 if customer else None),
                wo.service_city or (customer.city if customer else None),
                wo.service_state or (customer.state if customer else None),
                wo.service_postal_code or (customer.postal_code if customer else None),
            ]
            address_str = ", ".join(p for p in address_parts if p)
            lat, lng = _address_to_approx_coords(address_str or str(wo.id))

        # Build human-readable address
        addr_parts = [
            wo.service_address_line1,
            wo.service_city,
            wo.service_state,
            wo.service_postal_code,
        ]
        address = ", ".join(p for p in addr_parts if p) or "Unknown address"

        jobs.append({
            "job_id": str(wo.id),
            "address": address,
            "lat": lat,
            "lng": lng,
        })

    # Run nearest-neighbor optimization
    ordered_jobs, total_distance = _nearest_neighbor_route(jobs, start_lat, start_lng)

    # Estimate drive time: assume average 35 mph for rural/suburban Texas
    estimated_drive_minutes = int(round(total_distance / 35 * 60))

    ordered_job_ids = [j["job_id"] for j in ordered_jobs]
    waypoints = [
        {
            "job_id": j["job_id"],
            "address": j["address"],
            "lat": j["lat"],
            "lng": j["lng"],
        }
        for j in ordered_jobs
    ]

    return RouteOptimizeResponse(
        ordered_job_ids=ordered_job_ids,
        total_distance_miles=round(total_distance, 2),
        estimated_drive_minutes=estimated_drive_minutes,
        waypoints=waypoints,
    )


# ============================================
# Single Work Order Operations
# ============================================


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


async def generate_work_order_number(db: DbSession) -> str:
    """Generate next work order number in WO-NNNNNN format."""
    result = await db.execute(
        select(func.max(WorkOrder.work_order_number))
    )
    last_number = result.scalar()
    if last_number and last_number.startswith("WO-"):
        try:
            num = int(last_number.replace("WO-", "")) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f"WO-{num:06d}"


@router.post("", response_model=WorkOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_work_order(
    work_order_data: WorkOrderCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    entity: EntityCtx,
):
    """Create a new work order."""
    data = work_order_data.model_dump()
    data["id"] = str(uuid.uuid4())
    if entity:
        data["entity_id"] = str(entity.id)
    data["work_order_number"] = await generate_work_order_number(db)

    # Audit trail fields
    data["created_by"] = current_user.email if current_user else None
    data["updated_by"] = current_user.email if current_user else None
    data["source"] = request.headers.get("X-Source", "crm")
    data["created_at"] = datetime.utcnow()
    data["updated_at"] = datetime.utcnow()

    # Set default estimated_duration_hours based on job type if not provided
    if not data.get("estimated_duration_hours"):
        job_type_durations = {
            "inspection": 0.5,   # 30 minutes
            "pumping": 1.0,      # 1 hour
            "repair": 2.0,       # 2 hours
            "installation": 4.0, # 4 hours
            "maintenance": 1.0,  # 1 hour
            "grease_trap": 1.0,  # 1 hour
            "emergency": 2.0,    # 2 hours
        }
        data["estimated_duration_hours"] = job_type_durations.get(
            data.get("job_type", ""), 1.0
        )

    # Auto-resolve assigned_technician → technician_id if not already set
    if data.get("assigned_technician") and not data.get("technician_id"):
        tech_name = data["assigned_technician"].strip()
        name_parts = tech_name.split(None, 1)
        if len(name_parts) >= 2:
            tech_result = await db.execute(
                select(Technician).where(
                    Technician.first_name == name_parts[0],
                    Technician.last_name == name_parts[1],
                    Technician.is_active == True,
                ).limit(1)
            )
        else:
            tech_result = await db.execute(
                select(Technician).where(
                    Technician.first_name == tech_name,
                    Technician.is_active == True,
                ).limit(1)
            )
        matched_tech = tech_result.scalar_one_or_none()
        if matched_tech:
            data["technician_id"] = str(matched_tech.id)
            logger.info(f"Auto-resolved technician '{tech_name}' → {matched_tech.id}")

    work_order = WorkOrder(**data)
    db.add(work_order)
    await db.commit()
    await db.refresh(work_order)

    # Create audit log entry
    try:
        client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
        audit_entry = WorkOrderAuditLog(
            work_order_id=work_order.id,
            action="created",
            description=f"Work order {work_order.work_order_number} created for {work_order.job_type}",
            user_email=current_user.email if current_user else None,
            user_name=getattr(current_user, "full_name", None) or (current_user.email if current_user else "System"),
            source=request.headers.get("X-Source", "crm"),
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent", None),
            changes={"status": {"old": None, "new": work_order.status}, "job_type": {"old": None, "new": work_order.job_type}},
        )
        db.add(audit_entry)
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to create audit log for WO {work_order.id}: {e}")

    # Broadcast work order created event via WebSocket
    await manager.broadcast_event(
        event_type="work_order_update",
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

    # Invalidate work order and dashboard caches
    await get_cache_service().delete_pattern("workorders:*")
    await get_cache_service().delete_pattern("dashboard:*")

    # Fetch customer for name population in response
    customer = None
    if work_order.customer_id:
        cust_result = await db.execute(
            select(Customer).where(Customer.id == work_order.customer_id)
        )
        customer = cust_result.scalar_one_or_none()

    return work_order_with_customer_name(work_order, customer)


@router.patch("/{work_order_id}", response_model=WorkOrderResponse)
async def update_work_order(
    work_order_id: str,
    work_order_data: WorkOrderUpdate,
    request: Request,
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
        # Still need customer name for response
        customer = None
        if work_order.customer_id:
            cust_result = await db.execute(
                select(Customer).where(Customer.id == work_order.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
        return work_order_with_customer_name(work_order, customer)

    # Track status change for WebSocket event
    old_status = str(work_order.status) if work_order.status else None
    old_technician = work_order.assigned_technician

    # Capture before-state for audit diff
    audit_changes = {}
    for field, new_value in update_data.items():
        old_value = getattr(work_order, field, None)
        # Serialize for JSON comparison
        old_ser = str(old_value) if old_value is not None else None
        new_ser = str(new_value) if new_value is not None else None
        if old_ser != new_ser:
            audit_changes[field] = {"old": old_ser, "new": new_ser}

    try:
        # Use SQLAlchemy ORM update - handles ENUM types correctly
        for field, value in update_data.items():
            setattr(work_order, field, value)

        # Auto-resolve assigned_technician (name string) → technician_id (UUID FK)
        # The schedule UI only sets assigned_technician, but the technician dashboard
        # needs technician_id to find jobs. Bridge the gap automatically.
        if "assigned_technician" in update_data and update_data["assigned_technician"]:
            tech_name = update_data["assigned_technician"]
            name_parts = tech_name.strip().split(None, 1)
            if len(name_parts) >= 2:
                tech_result = await db.execute(
                    select(Technician).where(
                        Technician.first_name == name_parts[0],
                        Technician.last_name == name_parts[1],
                        Technician.is_active == True,
                    ).limit(1)
                )
            else:
                tech_result = await db.execute(
                    select(Technician).where(
                        Technician.first_name == tech_name,
                        Technician.is_active == True,
                    ).limit(1)
                )
            matched_tech = tech_result.scalar_one_or_none()
            if matched_tech:
                work_order.technician_id = matched_tech.id
                logger.info(f"Auto-resolved technician '{tech_name}' → {matched_tech.id}")

        # Update timestamp and audit
        work_order.updated_at = datetime.utcnow()
        work_order.updated_by = current_user.email if current_user else None

        await db.commit()
        await db.refresh(work_order)

        # Create audit log entry for the update
        if audit_changes:
            try:
                # Determine action type from changes
                action = "updated"
                desc_parts = []
                if "status" in audit_changes:
                    action = "status_changed"
                    desc_parts.append(f"Status: {audit_changes['status']['old']} → {audit_changes['status']['new']}")
                if "assigned_technician" in audit_changes or "technician_id" in audit_changes:
                    action = "assigned" if "status" not in audit_changes else action
                    desc_parts.append(f"Technician: {audit_changes.get('assigned_technician', {}).get('old', '?')} → {audit_changes.get('assigned_technician', {}).get('new', '?')}")
                if not desc_parts:
                    desc_parts.append(f"Updated {', '.join(audit_changes.keys())}")

                client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else None)
                audit_entry = WorkOrderAuditLog(
                    work_order_id=work_order.id,
                    action=action,
                    description="; ".join(desc_parts),
                    user_email=current_user.email if current_user else None,
                    user_name=getattr(current_user, "full_name", None) or (current_user.email if current_user else "System"),
                    source=request.headers.get("X-Source", "crm"),
                    ip_address=client_ip,
                    user_agent=request.headers.get("User-Agent", None),
                    changes=audit_changes,
                )
                db.add(audit_entry)
                await db.commit()
            except Exception as audit_err:
                logger.warning(f"Failed to create audit log for WO {work_order_id}: {audit_err}")

    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating work order {work_order_id}: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Outlook calendar sync — fire-and-forget when technician is assigned
    if ("assigned_technician" in update_data or "technician_id" in update_data) and work_order.technician_id:
        try:
            import asyncio
            from app.services.ms365_calendar_service import MS365CalendarService
            tech_result2 = await db.execute(
                select(Technician).where(Technician.id == work_order.technician_id)
            )
            tech = tech_result2.scalar_one_or_none()
            ms_email = getattr(tech, "microsoft_email", None) if tech else None
            if ms_email and MS365CalendarService.is_configured():
                customer2 = None
                if work_order.customer_id:
                    cr = await db.execute(select(Customer).where(Customer.id == work_order.customer_id))
                    customer2 = cr.scalar_one_or_none()
                cust_name = f"{customer2.first_name} {customer2.last_name}" if customer2 else "Unknown"
                job = str(work_order.job_type) if work_order.job_type else "Service"
                addr = work_order.service_address_line1 or ""
                sched = work_order.scheduled_date.isoformat() if work_order.scheduled_date else ""
                t_start = work_order.time_window_start
                t_end = work_order.time_window_end

                from datetime import datetime as dt2, time as time2
                # Build start datetime from scheduled_date + time_window_start
                if sched and t_start:
                    start_datetime = dt2.combine(work_order.scheduled_date, t_start)
                elif sched:
                    start_datetime = dt2.fromisoformat(f"{sched}T08:00:00")
                else:
                    start_datetime = dt2.now()
                dur = work_order.estimated_duration_hours or 2.0
                wo_id = str(work_order.id)
                wo_notes = work_order.notes or ""
                existing_event_id = work_order.outlook_event_id

                async def _sync_calendar():
                    try:
                        if existing_event_id:
                            await MS365CalendarService.update_event(
                                technician_microsoft_email=ms_email,
                                event_id=existing_event_id,
                                subject=f"{job.title()} - {cust_name}",
                                location=addr,
                                body=f"Work Order: {wo_id}\nNotes: {wo_notes}",
                                start_dt=start_datetime,
                                duration_hours=dur,
                            )
                        else:
                            new_event_id = await MS365CalendarService.create_event(
                                technician_microsoft_email=ms_email,
                                subject=f"{job.title()} - {cust_name}",
                                location=addr,
                                body=f"Work Order: {wo_id}\nNotes: {wo_notes}",
                                start_dt=start_datetime,
                                duration_hours=dur,
                            )
                            if new_event_id:
                                # Save event ID back — need a fresh DB session
                                from app.database import async_session_maker
                                async with async_session_maker() as sess:
                                    from sqlalchemy import text as sql_text
                                    await sess.execute(
                                        sql_text("UPDATE work_orders SET outlook_event_id = :eid WHERE id = :wid"),
                                        {"eid": new_event_id, "wid": wo_id},
                                    )
                                    await sess.commit()
                                logger.info(f"Outlook event {new_event_id} created for WO {wo_id}")
                    except Exception as cal_err:
                        logger.warning(f"Outlook calendar sync failed for WO {wo_id}: {cal_err}")

                asyncio.create_task(_sync_calendar())
        except Exception as e:
            logger.warning(f"Calendar sync setup error: {e}")

    # Invalidate caches
    await get_cache_service().delete_pattern("workorders:*")
    await get_cache_service().delete_pattern("dashboard:*")

    # Fetch customer for name population in response
    customer = None
    if work_order.customer_id:
        cust_result = await db.execute(
            select(Customer).where(Customer.id == work_order.customer_id)
        )
        customer = cust_result.scalar_one_or_none()

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

    # Auto-generate invoice when status changes to "completed" via PATCH
    if old_status != new_status and new_status == "completed":
        try:
            from app.models.invoice import Invoice
            from datetime import timedelta as td

            existing_inv = await db.execute(
                select(Invoice).where(Invoice.work_order_id == work_order_id)
            )
            if not existing_inv.scalar_one_or_none():
                wo_amount = float(work_order.total_amount) if work_order.total_amount else 0.0
                if wo_amount > 0 and work_order.customer_id:
                    job_labels = {
                        "pumping": "Septic Tank Pumping", "inspection": "Septic System Inspection",
                        "repair": "Septic System Repair", "installation": "Septic System Installation",
                        "emergency": "Emergency Service Call", "maintenance": "Septic Maintenance",
                        "grease_trap": "Grease Trap Service", "camera_inspection": "Camera Inspection",
                    }
                    job_label = job_labels.get(str(work_order.job_type) if work_order.job_type else "pumping", "Septic Service")
                    addr_parts = [work_order.service_address_line1, work_order.service_city, work_order.service_state]
                    addr = ", ".join(p for p in addr_parts if p)
                    desc = job_label + (f" at {addr}" if addr else "")
                    tax_rate, tax = 8.25, round(wo_amount * 0.0825, 2)
                    total = round(wo_amount + tax, 2)
                    inv = Invoice(
                        id=uuid.uuid4(), customer_id=work_order.customer_id, work_order_id=work_order.id,
                        invoice_number=f"INV-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}",
                        issue_date=datetime.now().date(), due_date=datetime.now().date() + td(days=30),
                        amount=total, paid_amount=0, status="draft",
                        line_items=[{"description": desc, "quantity": 1, "unit_price": wo_amount, "amount": wo_amount}],
                        notes=f"Auto-generated from {work_order.work_order_number or 'work order'} completion",
                    )
                    db.add(inv)
                    await db.commit()
                    logger.info(f"Auto-generated invoice {inv.invoice_number} for WO {work_order_id} (via PATCH)")
                    # Send "Pay Now" SMS with customer portal link
                    try:
                        if customer and customer.phone:
                            from app.services.twilio_service import TwilioService
                            pay_url = f"https://react.ecbtx.com/portal/pay/{inv.id}"
                            sms_msg = (
                                f"Hi {customer.first_name or "there"}, your invoice "
                                f"#{inv.invoice_number} for ${float(total):.2f} is ready. "
                                f"Pay online: {pay_url}"
                            )
                            twilio = TwilioService()
                            await twilio.send_sms(customer.phone, sms_msg)
                            logger.info(f"Sent Pay Now SMS to {customer.phone} for invoice {inv.invoice_number}")
                    except Exception as sms_err:
                        logger.warning(f"Pay Now SMS failed for invoice {inv.invoice_number}: {sms_err}")
        except Exception as e:
            await db.rollback()
            logger.warning(f"Auto-invoice generation failed for WO {work_order_id}: {e}")

    # Auto-notify customer via SMS when job is marked completed
    notification_sent = False
    if old_status != new_status and new_status == "completed":
        try:
            from app.services.twilio_service import TwilioService
            if work_order.customer_id and customer:
                phone = customer.phone
                if phone:
                    addr_parts = [work_order.service_address_line1, work_order.service_city]
                    addr = ", ".join(p for p in addr_parts if p) or "your property"
                    msg = (
                        f"Hi {customer.first_name}! Your septic service at {addr} is complete. "
                        f"Thank you for choosing MAC Septic. Questions? Call (512) 353-0555."
                    )
                    sms = TwilioService()
                    if sms.is_configured:
                        await sms.send_sms(to=phone, body=msg)
                        notification_sent = True
                        logger.info(f"Completion SMS sent to {phone} for WO {work_order_id}")
                    else:
                        logger.info("Twilio not configured — completion SMS skipped")
        except Exception as e:
            logger.warning(f"Completion SMS failed for WO {work_order_id}: {e}")

    # Status change event
    if old_status != new_status:
        await manager.broadcast_event(
            event_type="job_status",
            data={
                **event_data,
                "old_status": old_status,
                "new_status": new_status,
            },
        )

    # Technician assignment event
    if old_technician != new_technician:
        await manager.broadcast_event(
            event_type="dispatch_update",
            data={
                **event_data,
                "old_technician": old_technician,
                "new_technician": new_technician,
            },
        )

    # General update event (always sent)
    await manager.broadcast_event(
        event_type="work_order_update",
        data=event_data,
    )

    # Schedule change event (when schedule-related fields change)
    schedule_fields = {"scheduled_date", "time_window_start", "time_window_end", "assigned_technician"}
    if schedule_fields.intersection(update_data.keys()):
        await manager.broadcast_event(
            event_type="schedule_change",
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

    response_data = work_order_with_customer_name(work_order, customer)
    response_data["notification_sent"] = notification_sent
    return response_data


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_order(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a work order."""
    try:
        result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        work_order = result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Work order not found",
            )

        await db.delete(work_order)
        await db.commit()
        await get_cache_service().delete_pattern("workorders:*")
        await get_cache_service().delete_pattern("dashboard:*")
    except HTTPException:
        raise
    except Exception as e:
        import logging
        import traceback
        logging.error(f"Error deleting work order {work_order_id}: {e}")
        logging.error(traceback.format_exc())
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete work order: {str(e)}",
        )


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

    # Use ORM setattr like the PATCH endpoint does - handles ENUM types correctly
    work_order.status = "completed"
    work_order.actual_end_time = datetime.now()
    work_order.updated_at = datetime.utcnow()

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

    # Commit the status change FIRST, before commission
    try:
        await db.commit()
        await db.refresh(work_order)
        logger.info(f"Committed work order {work_order_id} status to completed")
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to commit work order completion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to complete work order: {str(e)}")

    # Now auto-create commission (in separate transaction)
    commission = await auto_create_commission(
        db=db,
        work_order=work_order,
        dump_site_id=request.dump_site_id,
    )

    # Commit commission if created
    if commission:
        try:
            await db.commit()
            logger.info(f"Created commission {commission.id} for work order {work_order_id}")
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to create commission: {e}")
            commission = None  # Still return success for work order completion

    # Auto-generate invoice (non-blocking, won't fail WO completion)
    invoice_info = None
    try:
        from app.models.invoice import Invoice
        from datetime import timedelta as td

        # Check if invoice already exists for this WO
        existing_inv = await db.execute(
            select(Invoice).where(Invoice.work_order_id == work_order_id)
        )
        if not existing_inv.scalar_one_or_none():
            wo_amount = float(work_order.total_amount) if work_order.total_amount else 0.0
            if wo_amount > 0 and work_order.customer_id:
                job_labels = {
                    "pumping": "Septic Tank Pumping",
                    "inspection": "Septic System Inspection",
                    "repair": "Septic System Repair",
                    "installation": "Septic System Installation",
                    "emergency": "Emergency Service Call",
                    "maintenance": "Septic Maintenance",
                    "grease_trap": "Grease Trap Service",
                    "camera_inspection": "Camera Inspection",
                }
                job_label = job_labels.get(
                    str(work_order.job_type) if work_order.job_type else "pumping",
                    "Septic Service",
                )
                addr_parts = [work_order.service_address_line1, work_order.service_city, work_order.service_state]
                addr = ", ".join(p for p in addr_parts if p)
                desc = job_label
                if addr:
                    desc += f" at {addr}"

                tax_rate = 8.25
                tax = round(wo_amount * tax_rate / 100, 2)
                total = round(wo_amount + tax, 2)
                date_part = datetime.now().strftime("%Y%m%d")
                random_part = uuid.uuid4().hex[:4].upper()

                invoice = Invoice(
                    id=uuid.uuid4(),
                    customer_id=work_order.customer_id,
                    work_order_id=work_order.id,
                    invoice_number=f"INV-{date_part}-{random_part}",
                    issue_date=datetime.now().date(),
                    due_date=datetime.now().date() + td(days=30),
                    amount=total,
                    paid_amount=0,
                    status="draft",
                    line_items=[{"description": desc, "quantity": 1, "unit_price": wo_amount, "amount": wo_amount}],
                    notes=f"Auto-generated from {work_order.work_order_number or 'work order'} completion",
                )
                db.add(invoice)
                await db.commit()
                await db.refresh(invoice)
                invoice_info = {"id": str(invoice.id), "invoice_number": invoice.invoice_number, "total": total}
                logger.info(f"Auto-generated invoice {invoice.invoice_number} for WO {work_order_id}")
    except Exception as e:
        await db.rollback()
        logger.warning(f"Auto-invoice generation failed for WO {work_order_id}: {e}")

    # Store values before any potential errors
    wo_id = work_order.id
    wo_number = work_order.work_order_number
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
            event_type="job_status",
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
        "work_order_number": wo_number,
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
        "invoice": invoice_info,
    }


# =====================================================
# Invoice Generation from Work Order
# =====================================================


@router.post("/{work_order_id}/generate-invoice")
async def generate_invoice_from_work_order(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Auto-generate an invoice from a completed work order.

    Creates an invoice with line items derived from the work order's
    job type, total_amount, and service details. Sets net-30 payment terms.
    """
    from app.models.invoice import Invoice
    from datetime import timedelta

    # Fetch work order with customer
    result = await db.execute(
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.id == work_order_id)
    )
    row = result.first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work order not found",
        )

    work_order, customer = row

    # Check if invoice already exists for this work order
    existing = await db.execute(
        select(Invoice).where(Invoice.work_order_id == work_order_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An invoice already exists for this work order",
        )

    # Build line items from work order data
    job_type_labels = {
        "pumping": "Septic Tank Pumping",
        "inspection": "Septic System Inspection",
        "repair": "Septic System Repair",
        "installation": "Septic System Installation",
        "emergency": "Emergency Service Call",
        "maintenance": "Septic Maintenance",
        "grease_trap": "Grease Trap Service",
        "camera_inspection": "Camera Inspection",
    }

    job_label = job_type_labels.get(
        str(work_order.job_type) if work_order.job_type else "pumping",
        "Septic Service",
    )
    amount = float(work_order.total_amount) if work_order.total_amount else 0.0

    # Build description from service address
    address_parts = [
        work_order.service_address_line1,
        work_order.service_city,
        work_order.service_state,
    ]
    address = ", ".join(p for p in address_parts if p)
    description = f"{job_label}"
    if address:
        description += f" at {address}"
    if work_order.scheduled_date:
        description += f" on {work_order.scheduled_date}"
    if work_order.estimated_gallons:
        description += f" ({work_order.estimated_gallons} gallons)"

    line_items = [
        {
            "description": description,
            "quantity": 1,
            "unit_price": amount,
            "amount": amount,
        }
    ]

    # Calculate tax (8.25% default)
    tax_rate = 8.25
    subtotal = amount
    tax = round(subtotal * tax_rate / 100, 2)
    total = round(subtotal + tax, 2)

    # Generate invoice number
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = uuid.uuid4().hex[:4].upper()
    invoice_number = f"INV-{date_part}-{random_part}"

    # Create invoice
    today = datetime.now().date()
    invoice = Invoice(
        id=uuid.uuid4(),
        customer_id=work_order.customer_id,
        work_order_id=work_order.id,
        invoice_number=invoice_number,
        issue_date=today,
        due_date=today + timedelta(days=30),
        amount=total,
        paid_amount=0,
        status="draft",
        line_items=line_items,
        notes=f"Generated from {work_order.work_order_number or 'work order'}",
    )

    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)

    # Invalidate caches
    await get_cache_service().delete_pattern("dashboard:*")

    customer_name = None
    if customer:
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "customer_id": str(invoice.customer_id),
        "customer_name": customer_name,
        "work_order_id": str(invoice.work_order_id),
        "work_order_number": work_order.work_order_number,
        "issue_date": invoice.issue_date.isoformat(),
        "due_date": invoice.due_date.isoformat(),
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax": tax,
        "total": total,
        "status": invoice.status,
        "line_items": line_items,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Audit Log Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/{work_order_id}/audit-log", response_model=list[WorkOrderAuditLogResponse])
async def get_work_order_audit_log(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get the full audit trail for a work order (newest first)."""
    result = await db.execute(
        select(WorkOrderAuditLog)
        .where(WorkOrderAuditLog.work_order_id == work_order_id)
        .order_by(desc(WorkOrderAuditLog.created_at))
    )
    entries = result.scalars().all()
    return entries
