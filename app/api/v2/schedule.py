from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, or_
from typing import Optional, List
from datetime import datetime, date, timedelta
from pydantic import BaseModel
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.models.technician import Technician
from app.models.contract import Contract

logger = logging.getLogger(__name__)

router = APIRouter()


class ScheduleStats(BaseModel):
    today_jobs: int
    week_jobs: int
    unscheduled_jobs: int
    emergency_jobs: int


class ScheduleWorkOrder(BaseModel):
    id: str
    customer_id: str
    customer_name: Optional[str] = None
    job_type: str
    status: str
    priority: str
    scheduled_date: Optional[str] = None
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    assigned_technician: Optional[str] = None
    service_address: Optional[str] = None
    service_city: Optional[str] = None


class UnscheduledResponse(BaseModel):
    items: list[ScheduleWorkOrder]
    total: int


def work_order_to_schedule(wo: WorkOrder, customer: Optional[Customer] = None) -> dict:
    """Convert WorkOrder to schedule format with customer name.

    Args:
        wo: The work order to convert
        customer: Optional customer object from JOIN (for real customer name)
    """
    # Build customer name from customer object if provided
    customer_name = None
    if customer:
        first = customer.first_name or ""
        last = customer.last_name or ""
        customer_name = f"{first} {last}".strip() or None

    return {
        "id": str(wo.id),
        "customer_id": str(wo.customer_id),
        "customer_name": customer_name,
        "job_type": wo.job_type or "pumping",
        "status": wo.status or "draft",
        "priority": wo.priority or "normal",
        "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date else None,
        "time_window_start": str(wo.time_window_start) if wo.time_window_start else None,
        "time_window_end": str(wo.time_window_end) if wo.time_window_end else None,
        "assigned_technician": wo.assigned_technician,
        "service_address": wo.service_address_line1,
        "service_city": wo.service_city,
    }


@router.get("/stats", response_model=ScheduleStats)
async def get_schedule_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get schedule statistics."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    today_result = await db.execute(select(func.count()).where(WorkOrder.scheduled_date == today))
    today_jobs = today_result.scalar() or 0

    week_result = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.scheduled_date >= week_start,
                WorkOrder.scheduled_date <= week_end,
            )
        )
    )
    week_jobs = week_result.scalar() or 0

    unscheduled_result = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.status == "draft",
                or_(
                    WorkOrder.scheduled_date.is_(None),
                    WorkOrder.scheduled_date == None,
                ),
            )
        )
    )
    unscheduled_jobs = unscheduled_result.scalar() or 0

    emergency_result = await db.execute(select(func.count()).where(WorkOrder.priority == "emergency"))
    emergency_jobs = emergency_result.scalar() or 0

    return ScheduleStats(
        today_jobs=today_jobs,
        week_jobs=week_jobs,
        unscheduled_jobs=unscheduled_jobs,
        emergency_jobs=emergency_jobs,
    )


@router.get("/unscheduled", response_model=UnscheduledResponse)
async def get_unscheduled_work_orders(
    db: DbSession,
    current_user: CurrentUser,
    page_size: int = Query(100, ge=1, le=500),
):
    """Get unscheduled work orders (draft without date) with customer names."""
    # LEFT JOIN with Customer table to get real customer names
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(
            and_(
                WorkOrder.status == "draft",
                or_(
                    WorkOrder.scheduled_date.is_(None),
                    WorkOrder.scheduled_date == None,
                ),
            )
        )
        .order_by(WorkOrder.created_at.desc())
        .limit(page_size)
    )

    result = await db.execute(query)
    rows = result.all()

    return UnscheduledResponse(
        items=[work_order_to_schedule(wo, customer) for wo, customer in rows],
        total=len(rows),
    )


@router.get("/by-date", response_model=UnscheduledResponse)
async def get_schedule_by_date(
    db: DbSession,
    current_user: CurrentUser,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
):
    """Get all work orders scheduled for a specific date with customer names."""
    # Parse string to date object — asyncpg requires proper types, not raw strings
    parsed_date = datetime.strptime(date, "%Y-%m-%d").date()

    # LEFT JOIN with Customer table to get real customer names
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.scheduled_date == parsed_date)
        .order_by(WorkOrder.time_window_start)
    )

    result = await db.execute(query)
    rows = result.all()

    return UnscheduledResponse(
        items=[work_order_to_schedule(wo, customer) for wo, customer in rows],
        total=len(rows),
    )


@router.get("/by-technician/{technician_name}")
async def get_schedule_by_technician(
    technician_name: str,
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Get work orders assigned to a specific technician with customer names."""
    # LEFT JOIN with Customer table to get real customer names
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.assigned_technician == technician_name)
    )

    if date_from:
        parsed_from = datetime.strptime(date_from, "%Y-%m-%d").date()
        query = query.where(WorkOrder.scheduled_date >= parsed_from)
    if date_to:
        parsed_to = datetime.strptime(date_to, "%Y-%m-%d").date()
        query = query.where(WorkOrder.scheduled_date <= parsed_to)

    query = query.order_by(WorkOrder.scheduled_date, WorkOrder.time_window_start)

    result = await db.execute(query)
    rows = result.all()

    return {
        "technician": technician_name,
        "items": [work_order_to_schedule(wo, customer) for wo, customer in rows],
        "total": len(rows),
    }


@router.get("/week-view")
async def get_week_view(
    db: DbSession,
    current_user: CurrentUser,
    start_date: str = Query(..., description="Start date (Monday) in YYYY-MM-DD format"),
):
    """Get all work orders for a week, grouped by date, with customer names."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = start + timedelta(days=6)

    # LEFT JOIN with Customer table to get real customer names
    query = (
        select(WorkOrder, Customer)
        .outerjoin(Customer, WorkOrder.customer_id == Customer.id)
        .where(
            and_(
                WorkOrder.scheduled_date >= start,
                WorkOrder.scheduled_date <= end,
            )
        )
        .order_by(WorkOrder.scheduled_date, WorkOrder.time_window_start)
    )

    result = await db.execute(query)
    rows = result.all()

    by_date: dict[str, list[dict]] = {}
    for i in range(7):
        day = (start + timedelta(days=i)).isoformat()
        by_date[day] = []

    for wo, customer in rows:
        if wo.scheduled_date:
            day_str = (
                wo.scheduled_date.isoformat()
                if hasattr(wo.scheduled_date, "isoformat")
                else str(wo.scheduled_date)[:10]
            )
            if day_str in by_date:
                by_date[day_str].append(work_order_to_schedule(wo, customer))

    return {
        "start_date": start_date,
        "end_date": end.isoformat(),
        "days": by_date,
        "total": len(rows),
    }


# ---------------------------------------------------------------------------
# Schedule Ahead — auto-generate maintenance inspections from contracts
# ---------------------------------------------------------------------------

class ScheduleAheadRequest(BaseModel):
    months_ahead: int = 12  # How many months to schedule ahead
    contract_ids: Optional[List[str]] = None  # Specific contracts, or all active


class ScheduleAheadResponse(BaseModel):
    created_count: int
    skipped_existing: int
    contracts_processed: int
    work_orders: list[dict]


@router.post("/schedule-ahead", response_model=ScheduleAheadResponse)
async def schedule_ahead(
    body: ScheduleAheadRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Auto-generate recurring maintenance work orders from active contracts.

    For each active maintenance contract, creates evenly-spaced inspection
    work orders (3 per year = every ~4 months) for the next N months.
    Skips dates that already have a work order for the same customer+job_type.
    """
    months_ahead = min(body.months_ahead, 24)  # Cap at 24 months
    today = date.today()
    horizon = today + timedelta(days=months_ahead * 30)

    # Fetch active maintenance contracts
    contract_query = select(Contract).where(
        and_(
            Contract.status == "active",
            Contract.contract_type.in_(["maintenance", "service", "annual"]),
        )
    )
    if body.contract_ids:
        contract_query = contract_query.where(
            Contract.id.in_([uuid.UUID(cid) for cid in body.contract_ids])
        )

    result = await db.execute(contract_query)
    contracts = result.scalars().all()

    if not contracts:
        return ScheduleAheadResponse(
            created_count=0, skipped_existing=0,
            contracts_processed=0, work_orders=[],
        )

    created_orders = []
    skipped = 0

    for contract in contracts:
        # Determine inspections per year from services_included, default 3
        inspections_per_year = 3
        if contract.services_included:
            for svc in contract.services_included:
                if isinstance(svc, dict) and svc.get("frequency") in ("tri_annual", "every_4_months"):
                    inspections_per_year = svc.get("quantity", 3)
                    break

        interval_days = 365 // inspections_per_year  # ~121 days for 3/yr

        # Get customer info for service address
        cust_result = await db.execute(
            select(Customer).where(Customer.id == contract.customer_id)
        )
        customer = cust_result.scalars().first()
        if not customer:
            continue

        # Find existing scheduled inspections for this customer in the horizon
        existing_result = await db.execute(
            select(WorkOrder.scheduled_date).where(
                and_(
                    WorkOrder.customer_id == contract.customer_id,
                    WorkOrder.job_type.in_(["inspection", "aerobic_inspection", "maintenance"]),
                    WorkOrder.scheduled_date >= today,
                    WorkOrder.scheduled_date <= horizon,
                    WorkOrder.status != "canceled",
                )
            )
        )
        existing_dates = {row[0] for row in existing_result.all()}

        # Generate inspection dates: start from next month, space evenly
        # Find the last existing inspection date, or use today as anchor
        if existing_dates:
            anchor = max(existing_dates)
        else:
            anchor = today

        schedule_date = anchor + timedelta(days=interval_days)
        while schedule_date <= horizon:
            # Skip weekends
            while schedule_date.weekday() >= 5:
                schedule_date += timedelta(days=1)

            # Check if a work order already exists within 14 days of this target
            too_close = any(
                abs((schedule_date - ed).days) < 14
                for ed in existing_dates
            )
            if too_close:
                skipped += 1
                schedule_date += timedelta(days=interval_days)
                continue

            # Determine job type based on customer system
            job_type = "maintenance"
            if customer.system_type and "aerobic" in customer.system_type.lower():
                job_type = "aerobic_inspection"

            # Generate next work order number
            wo_num_result = await db.execute(
                select(func.count()).select_from(WorkOrder)
            )
            wo_count = (wo_num_result.scalar() or 0) + 1 + len(created_orders)
            wo_number = f"WO-{wo_count:06d}"

            wo = WorkOrder(
                id=uuid.uuid4(),
                work_order_number=wo_number,
                customer_id=contract.customer_id,
                job_type=job_type,
                priority="normal",
                status="scheduled",
                scheduled_date=schedule_date,
                service_address_line1=customer.address_line1,
                service_city=customer.city,
                service_state=customer.state,
                service_postal_code=customer.postal_code,
                is_recurring=True,
                recurrence_frequency=f"every_{interval_days}_days",
                notes=f"Auto-generated from contract {contract.contract_number}",
                source="schedule_ahead",
                created_by=current_user.email if hasattr(current_user, 'email') else "system",
            )
            db.add(wo)
            existing_dates.add(schedule_date)
            created_orders.append({
                "id": str(wo.id),
                "customer_id": str(contract.customer_id),
                "customer_name": contract.customer_name or f"{customer.first_name} {customer.last_name}".strip(),
                "job_type": job_type,
                "scheduled_date": schedule_date.isoformat(),
                "contract_number": contract.contract_number,
            })

            schedule_date += timedelta(days=interval_days)

    await db.commit()

    logger.info(
        f"Schedule Ahead: created {len(created_orders)} work orders from "
        f"{len(contracts)} contracts, skipped {skipped} existing"
    )

    return ScheduleAheadResponse(
        created_count=len(created_orders),
        skipped_existing=skipped,
        contracts_processed=len(contracts),
        work_orders=created_orders,
    )
