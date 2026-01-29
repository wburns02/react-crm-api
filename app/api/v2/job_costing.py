"""Job Costing API - Track costs and profitability for work orders.

Features:
- CRUD for job costs
- Cost summary per work order
- Profitability analysis
- Cost reports
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime, date, timedelta
import logging
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.job_cost import JobCost
from app.models.work_order import WorkOrder
from app.models.payroll import TechnicianPayRate, Commission
from app.models.dump_site import DumpSite
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Pydantic Schemas
# ========================


class JobCostCreate(BaseModel):
    work_order_id: str
    cost_type: str
    category: Optional[str] = None
    description: str
    notes: Optional[str] = None
    quantity: float = 1.0
    unit: str = "each"
    unit_cost: float
    markup_percent: float = 0.0
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    cost_date: date
    is_billable: bool = True
    vendor_name: Optional[str] = None
    vendor_invoice: Optional[str] = None


class JobCostUpdate(BaseModel):
    cost_type: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    notes: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    unit_cost: Optional[float] = None
    markup_percent: Optional[float] = None
    is_billable: Optional[bool] = None
    is_billed: Optional[bool] = None
    invoice_id: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_invoice: Optional[str] = None


class JobCostResponse(BaseModel):
    id: str
    work_order_id: str
    cost_type: str
    category: Optional[str] = None
    description: str
    quantity: float
    unit: str
    unit_cost: float
    total_cost: float
    markup_percent: float
    billable_amount: Optional[float] = None
    technician_id: Optional[str] = None
    technician_name: Optional[str] = None
    cost_date: date
    is_billable: bool
    is_billed: bool
    vendor_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int


class WorkOrderCostSummary(BaseModel):
    work_order_id: str
    total_costs: float
    total_billable: float
    cost_breakdown: dict
    labor_costs: float
    material_costs: float
    other_costs: float
    cost_count: int


class ProfitabilityReport(BaseModel):
    work_order_id: str
    revenue: float
    total_costs: float
    gross_profit: float
    profit_margin_percent: float
    cost_breakdown: dict


# ========================
# Endpoints
# ========================


@router.get("", response_model=ListResponse)
async def list_job_costs(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    work_order_id: Optional[str] = Query(None),
    cost_type: Optional[str] = Query(None),
    technician_id: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    is_billable: Optional[bool] = Query(None),
    is_billed: Optional[bool] = Query(None),
):
    """List job costs with filtering."""
    try:
        query = select(JobCost)

        if work_order_id:
            query = query.where(JobCost.work_order_id == work_order_id)
        if cost_type:
            query = query.where(JobCost.cost_type == cost_type)
        if technician_id:
            query = query.where(JobCost.technician_id == technician_id)
        if date_from:
            query = query.where(JobCost.cost_date >= date_from)
        if date_to:
            query = query.where(JobCost.cost_date <= date_to)
        if is_billable is not None:
            query = query.where(JobCost.is_billable == is_billable)
        if is_billed is not None:
            query = query.where(JobCost.is_billed == is_billed)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(JobCost.cost_date.desc())

        result = await db.execute(query)
        costs = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(c.id),
                    "work_order_id": c.work_order_id,
                    "cost_type": c.cost_type,
                    "description": c.description,
                    "quantity": c.quantity,
                    "unit": c.unit,
                    "unit_cost": c.unit_cost,
                    "total_cost": c.total_cost,
                    "cost_date": c.cost_date,
                    "is_billable": c.is_billable,
                    "is_billed": c.is_billed,
                }
                for c in costs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing job costs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=JobCostResponse, status_code=status.HTTP_201_CREATED)
async def create_job_cost(
    cost_data: JobCostCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new job cost."""
    try:
        # Calculate total cost
        total_cost = cost_data.quantity * cost_data.unit_cost

        # Calculate billable amount
        billable_amount = total_cost * (1 + cost_data.markup_percent / 100) if cost_data.is_billable else None

        cost = JobCost(
            **cost_data.model_dump(),
            total_cost=total_cost,
            billable_amount=billable_amount,
            created_by=current_user.email,
        )
        db.add(cost)
        await db.commit()
        await db.refresh(cost)

        return {
            "id": str(cost.id),
            "work_order_id": cost.work_order_id,
            "cost_type": cost.cost_type,
            "category": cost.category,
            "description": cost.description,
            "quantity": cost.quantity,
            "unit": cost.unit,
            "unit_cost": cost.unit_cost,
            "total_cost": cost.total_cost,
            "markup_percent": cost.markup_percent,
            "billable_amount": cost.billable_amount,
            "technician_id": cost.technician_id,
            "technician_name": cost.technician_name,
            "cost_date": cost.cost_date,
            "is_billable": cost.is_billable,
            "is_billed": cost.is_billed,
            "vendor_name": cost.vendor_name,
            "created_at": cost.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating job cost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{cost_id}", response_model=JobCostResponse)
async def get_job_cost(
    cost_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific job cost."""
    try:
        result = await db.execute(select(JobCost).where(JobCost.id == uuid.UUID(cost_id)))
        cost = result.scalar_one_or_none()

        if not cost:
            raise HTTPException(status_code=404, detail="Job cost not found")

        return {
            "id": str(cost.id),
            "work_order_id": cost.work_order_id,
            "cost_type": cost.cost_type,
            "category": cost.category,
            "description": cost.description,
            "quantity": cost.quantity,
            "unit": cost.unit,
            "unit_cost": cost.unit_cost,
            "total_cost": cost.total_cost,
            "markup_percent": cost.markup_percent,
            "billable_amount": cost.billable_amount,
            "technician_id": cost.technician_id,
            "technician_name": cost.technician_name,
            "cost_date": cost.cost_date,
            "is_billable": cost.is_billable,
            "is_billed": cost.is_billed,
            "vendor_name": cost.vendor_name,
            "created_at": cost.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job cost {cost_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{cost_id}", response_model=JobCostResponse)
async def update_job_cost(
    cost_id: str,
    update_data: JobCostUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a job cost."""
    try:
        result = await db.execute(select(JobCost).where(JobCost.id == uuid.UUID(cost_id)))
        cost = result.scalar_one_or_none()

        if not cost:
            raise HTTPException(status_code=404, detail="Job cost not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(cost, key, value)

        # Recalculate totals if pricing fields changed
        if "quantity" in update_dict or "unit_cost" in update_dict:
            cost.total_cost = cost.quantity * cost.unit_cost

        if "markup_percent" in update_dict or "total_cost" in update_dict:
            if cost.is_billable:
                cost.billable_amount = cost.total_cost * (1 + cost.markup_percent / 100)

        await db.commit()
        await db.refresh(cost)

        return {
            "id": str(cost.id),
            "work_order_id": cost.work_order_id,
            "cost_type": cost.cost_type,
            "category": cost.category,
            "description": cost.description,
            "quantity": cost.quantity,
            "unit": cost.unit,
            "unit_cost": cost.unit_cost,
            "total_cost": cost.total_cost,
            "markup_percent": cost.markup_percent,
            "billable_amount": cost.billable_amount,
            "technician_id": cost.technician_id,
            "technician_name": cost.technician_name,
            "cost_date": cost.cost_date,
            "is_billable": cost.is_billable,
            "is_billed": cost.is_billed,
            "vendor_name": cost.vendor_name,
            "created_at": cost.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating job cost {cost_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{cost_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_cost(
    cost_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a job cost."""
    try:
        result = await db.execute(select(JobCost).where(JobCost.id == uuid.UUID(cost_id)))
        cost = result.scalar_one_or_none()

        if not cost:
            raise HTTPException(status_code=404, detail="Job cost not found")

        if cost.is_billed:
            raise HTTPException(status_code=400, detail="Cannot delete billed cost")

        await db.delete(cost)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting job cost {cost_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Summary Endpoints
# ========================


@router.get("/work-order/{work_order_id}/summary", response_model=WorkOrderCostSummary)
async def get_work_order_cost_summary(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get cost summary for a work order."""
    try:
        result = await db.execute(select(JobCost).where(JobCost.work_order_id == work_order_id))
        costs = result.scalars().all()

        total_costs = sum(c.total_cost for c in costs)
        total_billable = sum(c.billable_amount or 0 for c in costs if c.is_billable)

        # Breakdown by type
        cost_breakdown = {}
        for cost in costs:
            if cost.cost_type not in cost_breakdown:
                cost_breakdown[cost.cost_type] = 0
            cost_breakdown[cost.cost_type] += cost.total_cost

        # Standard categories
        labor_costs = sum(c.total_cost for c in costs if c.cost_type == "labor")
        material_costs = sum(c.total_cost for c in costs if c.cost_type == "materials")
        other_costs = total_costs - labor_costs - material_costs

        return {
            "work_order_id": work_order_id,
            "total_costs": total_costs,
            "total_billable": total_billable,
            "cost_breakdown": cost_breakdown,
            "labor_costs": labor_costs,
            "material_costs": material_costs,
            "other_costs": other_costs,
            "cost_count": len(costs),
        }
    except Exception as e:
        logger.error(f"Error getting cost summary for {work_order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/work-order/{work_order_id}/profitability", response_model=ProfitabilityReport)
async def get_work_order_profitability(
    work_order_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get profitability analysis for a work order."""
    try:
        # Get costs
        cost_result = await db.execute(select(JobCost).where(JobCost.work_order_id == work_order_id))
        costs = cost_result.scalars().all()

        total_costs = sum(c.total_cost for c in costs)

        # Breakdown by type
        cost_breakdown = {}
        for cost in costs:
            if cost.cost_type not in cost_breakdown:
                cost_breakdown[cost.cost_type] = 0
            cost_breakdown[cost.cost_type] += cost.total_cost

        # Get work order for revenue (if available)
        wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == work_order_id))
        work_order = wo_result.scalar_one_or_none()

        revenue = 0.0
        if work_order and hasattr(work_order, "total_amount"):
            revenue = float(work_order.total_amount or 0)

        gross_profit = revenue - total_costs
        profit_margin = (gross_profit / revenue * 100) if revenue > 0 else 0

        return {
            "work_order_id": work_order_id,
            "revenue": revenue,
            "total_costs": total_costs,
            "gross_profit": gross_profit,
            "profit_margin_percent": round(profit_margin, 2),
            "cost_breakdown": cost_breakdown,
        }
    except Exception as e:
        logger.error(f"Error getting profitability for {work_order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reports/summary")
async def get_cost_reports_summary(
    db: DbSession,
    current_user: CurrentUser,
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """Get job costing summary report."""
    try:
        if not date_from:
            date_from = date.today() - timedelta(days=30)
        if not date_to:
            date_to = date.today()

        result = await db.execute(select(JobCost).where(JobCost.cost_date >= date_from, JobCost.cost_date <= date_to))
        costs = result.scalars().all()

        total_costs = sum(c.total_cost for c in costs)
        total_billable = sum(c.billable_amount or 0 for c in costs if c.is_billable)
        billed_amount = sum(c.billable_amount or 0 for c in costs if c.is_billed)

        # By type
        by_type = {}
        for cost in costs:
            if cost.cost_type not in by_type:
                by_type[cost.cost_type] = {"count": 0, "total": 0}
            by_type[cost.cost_type]["count"] += 1
            by_type[cost.cost_type]["total"] += cost.total_cost

        # By technician
        by_technician = {}
        for cost in costs:
            if cost.technician_id:
                key = cost.technician_name or cost.technician_id
                if key not in by_technician:
                    by_technician[key] = {"count": 0, "total": 0}
                by_technician[key]["count"] += 1
                by_technician[key]["total"] += cost.total_cost

        return {
            "period": {
                "from": date_from,
                "to": date_to,
            },
            "summary": {
                "total_costs": total_costs,
                "total_billable": total_billable,
                "billed_amount": billed_amount,
                "unbilled_amount": total_billable - billed_amount,
                "cost_count": len(costs),
            },
            "by_type": by_type,
            "by_technician": by_technician,
        }
    except Exception as e:
        logger.error(f"Error getting cost reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Calculation Endpoints
# ========================


@router.get("/calculate/labor")
async def calculate_labor_cost(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: str = Query(..., description="Technician ID"),
    hours: float = Query(..., ge=0, description="Hours worked"),
):
    """Calculate labor cost using technician's current pay rate."""
    try:
        # Get technician's active pay rate
        result = await db.execute(
            select(TechnicianPayRate)
            .where(
                TechnicianPayRate.technician_id == technician_id,
                TechnicianPayRate.is_active == True
            )
            .order_by(TechnicianPayRate.effective_date.desc())
            .limit(1)
        )
        pay_rate = result.scalar_one_or_none()

        # Get technician name
        tech_result = await db.execute(
            select(Technician).where(Technician.id == technician_id)
        )
        technician = tech_result.scalar_one_or_none()
        tech_name = technician.name if technician else "Unknown"

        if not pay_rate:
            # Return default calculation if no pay rate configured
            default_rate = 25.0  # Default hourly rate
            return {
                "technician_id": technician_id,
                "technician_name": tech_name,
                "hours": hours,
                "pay_type": "hourly",
                "hourly_rate": default_rate,
                "regular_hours": min(hours, 8),
                "overtime_hours": max(0, hours - 8),
                "regular_cost": min(hours, 8) * default_rate,
                "overtime_cost": max(0, hours - 8) * default_rate * 1.5,
                "total_labor_cost": min(hours, 8) * default_rate + max(0, hours - 8) * default_rate * 1.5,
                "commission_rate": 0,
                "source": "default"
            }

        # Calculate based on pay type
        if pay_rate.pay_type == "salary":
            # Convert annual salary to hourly equivalent
            # Assume 260 working days, 8 hours/day = 2080 hours/year
            hourly_equivalent = (pay_rate.salary_amount or 52000) / 2080
            total_cost = hours * hourly_equivalent

            return {
                "technician_id": technician_id,
                "technician_name": tech_name,
                "hours": hours,
                "pay_type": "salary",
                "annual_salary": pay_rate.salary_amount,
                "hourly_equivalent": round(hourly_equivalent, 2),
                "regular_hours": hours,
                "overtime_hours": 0,
                "regular_cost": round(total_cost, 2),
                "overtime_cost": 0,
                "total_labor_cost": round(total_cost, 2),
                "commission_rate": pay_rate.job_commission_rate or 0,
                "source": "pay_rate"
            }
        else:
            # Hourly calculation with overtime
            hourly_rate = pay_rate.hourly_rate or 25.0
            overtime_multiplier = pay_rate.overtime_multiplier or 1.5

            # For single-day calculation, assume overtime after 8 hours
            regular_hours = min(hours, 8)
            overtime_hours = max(0, hours - 8)

            regular_cost = regular_hours * hourly_rate
            overtime_cost = overtime_hours * hourly_rate * overtime_multiplier

            return {
                "technician_id": technician_id,
                "technician_name": tech_name,
                "hours": hours,
                "pay_type": "hourly",
                "hourly_rate": hourly_rate,
                "overtime_multiplier": overtime_multiplier,
                "regular_hours": regular_hours,
                "overtime_hours": overtime_hours,
                "regular_cost": round(regular_cost, 2),
                "overtime_cost": round(overtime_cost, 2),
                "total_labor_cost": round(regular_cost + overtime_cost, 2),
                "commission_rate": pay_rate.job_commission_rate or 0,
                "source": "pay_rate"
            }

    except Exception as e:
        logger.error(f"Error calculating labor cost: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculate/dump-fee")
async def calculate_dump_fee(
    db: DbSession,
    current_user: CurrentUser,
    dump_site_id: str = Query(..., description="Dump site ID"),
    gallons: int = Query(..., ge=0, description="Gallons to dump"),
):
    """Calculate dump fee for given gallons at specific site."""
    try:
        result = await db.execute(
            select(DumpSite).where(DumpSite.id == dump_site_id)
        )
        dump_site = result.scalar_one_or_none()

        if not dump_site:
            raise HTTPException(status_code=404, detail="Dump site not found")

        fee_per_gallon = dump_site.fee_per_gallon
        total_fee = gallons * fee_per_gallon

        return {
            "dump_site_id": str(dump_site.id),
            "dump_site_name": dump_site.name,
            "state": dump_site.address_state,
            "gallons": gallons,
            "fee_per_gallon": fee_per_gallon,
            "total_dump_fee": round(total_fee, 2)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating dump fee: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculate/commission")
async def calculate_commission(
    db: DbSession,
    current_user: CurrentUser,
    technician_id: str = Query(..., description="Technician ID"),
    job_total: float = Query(..., ge=0, description="Total job revenue"),
    dump_fee: float = Query(0, ge=0, description="Dump fee to deduct"),
):
    """Calculate commission for technician on a job."""
    try:
        # Get technician's commission rate
        result = await db.execute(
            select(TechnicianPayRate)
            .where(
                TechnicianPayRate.technician_id == technician_id,
                TechnicianPayRate.is_active == True
            )
            .order_by(TechnicianPayRate.effective_date.desc())
            .limit(1)
        )
        pay_rate = result.scalar_one_or_none()

        # Get technician name
        tech_result = await db.execute(
            select(Technician).where(Technician.id == technician_id)
        )
        technician = tech_result.scalar_one_or_none()
        tech_name = technician.name if technician else "Unknown"

        # Default commission rate if no pay rate configured
        commission_rate = 0.0
        if pay_rate:
            commission_rate = pay_rate.job_commission_rate or 0.0

        # Calculate commissionable amount (job total minus dump fee)
        commissionable_amount = job_total - dump_fee

        # Calculate commission
        commission_amount = commissionable_amount * (commission_rate / 100)

        return {
            "technician_id": technician_id,
            "technician_name": tech_name,
            "job_total": job_total,
            "dump_fee": dump_fee,
            "commissionable_amount": round(commissionable_amount, 2),
            "commission_rate_percent": commission_rate,
            "commission_amount": round(commission_amount, 2),
            "net_to_company": round(job_total - commission_amount, 2)
        }

    except Exception as e:
        logger.error(f"Error calculating commission: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/technicians/pay-rates")
async def list_technician_pay_rates(
    db: DbSession,
    current_user: CurrentUser,
):
    """List all technicians with their current pay rates."""
    try:
        # Get all active technicians
        tech_result = await db.execute(
            select(Technician).where(Technician.is_active == True)
        )
        technicians = tech_result.scalars().all()

        result = []
        for tech in technicians:
            # Get pay rate for this technician
            rate_result = await db.execute(
                select(TechnicianPayRate)
                .where(
                    TechnicianPayRate.technician_id == tech.id,
                    TechnicianPayRate.is_active == True
                )
                .order_by(TechnicianPayRate.effective_date.desc())
                .limit(1)
            )
            pay_rate = rate_result.scalar_one_or_none()

            result.append({
                "technician_id": tech.id,
                "name": tech.name,
                "pay_type": pay_rate.pay_type if pay_rate else "hourly",
                "hourly_rate": pay_rate.hourly_rate if pay_rate else None,
                "salary_amount": pay_rate.salary_amount if pay_rate else None,
                "commission_rate": pay_rate.job_commission_rate if pay_rate else 0,
                "has_pay_rate": pay_rate is not None
            })

        return {"technicians": result, "total": len(result)}

    except Exception as e:
        logger.error(f"Error listing technician pay rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dump-sites/list")
async def list_dump_sites_for_costing(
    db: DbSession,
    current_user: CurrentUser,
):
    """List active dump sites for job costing selection."""
    try:
        result = await db.execute(
            select(DumpSite)
            .where(DumpSite.is_active == True)
            .order_by(DumpSite.address_state, DumpSite.name)
        )
        sites = result.scalars().all()

        return {
            "sites": [
                {
                    "id": str(site.id),
                    "name": site.name,
                    "city": site.address_city,
                    "state": site.address_state,
                    "fee_per_gallon": site.fee_per_gallon
                }
                for site in sites
            ],
            "total": len(sites)
        }

    except Exception as e:
        logger.error(f"Error listing dump sites: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/work-orders/recent")
async def list_recent_work_orders(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=100),
):
    """List recent work orders for job costing selection."""
    try:
        result = await db.execute(
            select(WorkOrder)
            .order_by(WorkOrder.created_at.desc())
            .limit(limit)
        )
        work_orders = result.scalars().all()

        return {
            "work_orders": [
                {
                    "id": wo.id,
                    "customer_id": wo.customer_id,
                    "job_type": getattr(wo, "job_type", None),
                    "status": getattr(wo, "status", None),
                    "total_amount": float(wo.total_amount) if hasattr(wo, "total_amount") and wo.total_amount else 0,
                    "scheduled_start": wo.scheduled_start.isoformat() if hasattr(wo, "scheduled_start") and wo.scheduled_start else None,
                    "technician_id": getattr(wo, "technician_id", None),
                    "created_at": wo.created_at.isoformat() if wo.created_at else None
                }
                for wo in work_orders
            ],
            "total": len(work_orders)
        }

    except Exception as e:
        logger.error(f"Error listing recent work orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))
