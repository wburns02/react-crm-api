from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, or_, extract
from typing import Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder, WorkOrderStatus, JobType
from app.models.customer import Customer, ProspectStage
from app.models.invoice import Invoice, InvoiceStatus
from app.models.technician import Technician

router = APIRouter()


# =====================
# Revenue Report Models
# =====================

class RevenueMetrics(BaseModel):
    total_revenue: float
    total_revenue_change_percent: Optional[float] = None
    work_orders_completed: int
    work_orders_completed_change_percent: Optional[float] = None
    average_job_value: float
    average_job_value_change_percent: Optional[float] = None
    new_customers: int
    new_customers_change_percent: Optional[float] = None
    repeat_customer_rate: float
    repeat_customer_rate_change_percent: Optional[float] = None
    customer_satisfaction_score: Optional[float] = None
    customer_satisfaction_score_change_percent: Optional[float] = None


class RevenueDataPoint(BaseModel):
    date: str
    revenue: float
    work_orders: int


class ServiceBreakdown(BaseModel):
    service_type: str
    count: int
    revenue: float
    percentage: float


class RevenueReport(BaseModel):
    metrics: RevenueMetrics
    revenue_over_time: list[RevenueDataPoint]
    service_breakdown: list[ServiceBreakdown]
    date_range: dict


# ==========================
# Technician Report Models
# ==========================

class TechnicianMetrics(BaseModel):
    technician_id: str
    technician_name: str
    jobs_completed: int
    total_revenue: float
    average_job_duration_hours: Optional[float] = None
    customer_satisfaction: Optional[float] = None
    on_time_completion_rate: float


class TechnicianReport(BaseModel):
    technicians: list[TechnicianMetrics]
    date_range: dict


# ======================
# Customer Report Models
# ======================

class CustomerMetrics(BaseModel):
    total_customers: int
    total_customers_change_percent: Optional[float] = None
    active_customers: int
    active_customers_change_percent: Optional[float] = None
    new_customers_this_month: int
    churn_rate: Optional[float] = None
    average_customer_lifetime_value: Optional[float] = None


class CustomerGrowthDataPoint(BaseModel):
    date: str
    total_customers: int
    new_customers: int
    active_customers: int


class CustomerReport(BaseModel):
    metrics: CustomerMetrics
    growth_over_time: list[CustomerGrowthDataPoint]
    date_range: dict


# =======================
# Pipeline Report Models
# =======================

class ProspectsByStage(BaseModel):
    stage: str
    count: int
    total_value: float


class PipelineMetrics(BaseModel):
    total_pipeline_value: float
    total_prospects: int
    prospects_by_stage: list[ProspectsByStage]
    conversion_rate: Optional[float] = None
    average_deal_size: Optional[float] = None


# =====================
# Revenue Report Endpoint
# =====================

@router.get("/revenue", response_model=RevenueReport)
async def get_revenue_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get revenue report with metrics and trends."""
    # Default to last 30 days
    if not end_date:
        end = date.today()
        end_date = end.isoformat()
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start = end - timedelta(days=30)
        start_date = start.isoformat()
    else:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()

    # Previous period for comparison
    period_days = (end - start).days
    prev_start = start - timedelta(days=period_days)
    prev_end = start - timedelta(days=1)

    # --- REVENUE METRICS ---
    # Current period total revenue (from paid invoices)
    revenue_result = await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            and_(
                Invoice.status == InvoiceStatus.paid,
                Invoice.paid_date >= start_date,
                Invoice.paid_date <= end_date,
            )
        )
    )
    total_revenue = float(revenue_result.scalar() or 0)

    # Previous period revenue
    prev_revenue_result = await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            and_(
                Invoice.status == InvoiceStatus.paid,
                Invoice.paid_date >= prev_start.isoformat(),
                Invoice.paid_date <= prev_end.isoformat(),
            )
        )
    )
    prev_revenue = float(prev_revenue_result.scalar() or 0)
    revenue_change = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else None

    # Work orders completed
    wo_completed_result = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.status == WorkOrderStatus.completed,
                func.date(WorkOrder.completed_at) >= start,
                func.date(WorkOrder.completed_at) <= end,
            )
        )
    )
    work_orders_completed = wo_completed_result.scalar() or 0

    # Previous period work orders
    prev_wo_result = await db.execute(
        select(func.count()).where(
            and_(
                WorkOrder.status == WorkOrderStatus.completed,
                func.date(WorkOrder.completed_at) >= prev_start,
                func.date(WorkOrder.completed_at) <= prev_end,
            )
        )
    )
    prev_wo_completed = prev_wo_result.scalar() or 0
    wo_change = ((work_orders_completed - prev_wo_completed) / prev_wo_completed * 100) if prev_wo_completed > 0 else None

    # Average job value
    avg_job_value = total_revenue / work_orders_completed if work_orders_completed > 0 else 0
    prev_avg_job = prev_revenue / prev_wo_completed if prev_wo_completed > 0 else 0
    avg_job_change = ((avg_job_value - prev_avg_job) / prev_avg_job * 100) if prev_avg_job > 0 else None

    # New customers (prospect_stage = won, created in period)
    new_customers_result = await db.execute(
        select(func.count()).where(
            and_(
                Customer.prospect_stage == ProspectStage.won,
                func.date(Customer.created_at) >= start,
                func.date(Customer.created_at) <= end,
            )
        )
    )
    new_customers = new_customers_result.scalar() or 0

    # --- REVENUE OVER TIME ---
    revenue_over_time = []
    current_date = start
    while current_date <= end:
        day_revenue_result = await db.execute(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                and_(
                    Invoice.status == InvoiceStatus.paid,
                    Invoice.paid_date == current_date.isoformat(),
                )
            )
        )
        day_revenue = float(day_revenue_result.scalar() or 0)

        day_wo_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.status == WorkOrderStatus.completed,
                    func.date(WorkOrder.completed_at) == current_date,
                )
            )
        )
        day_wo_count = day_wo_result.scalar() or 0

        revenue_over_time.append(RevenueDataPoint(
            date=current_date.isoformat(),
            revenue=day_revenue,
            work_orders=day_wo_count,
        ))
        current_date += timedelta(days=1)

    # --- SERVICE BREAKDOWN ---
    service_breakdown = []
    for job_type in JobType:
        type_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.job_type == job_type,
                    WorkOrder.status == WorkOrderStatus.completed,
                    func.date(WorkOrder.completed_at) >= start,
                    func.date(WorkOrder.completed_at) <= end,
                )
            )
        )
        count = type_result.scalar() or 0
        # Estimate revenue per job type (simplified)
        estimated_revenue = count * avg_job_value
        percentage = (count / work_orders_completed * 100) if work_orders_completed > 0 else 0

        if count > 0:
            service_breakdown.append(ServiceBreakdown(
                service_type=job_type.value,
                count=count,
                revenue=estimated_revenue,
                percentage=percentage,
            ))

    metrics = RevenueMetrics(
        total_revenue=total_revenue,
        total_revenue_change_percent=revenue_change,
        work_orders_completed=work_orders_completed,
        work_orders_completed_change_percent=wo_change,
        average_job_value=avg_job_value,
        average_job_value_change_percent=avg_job_change,
        new_customers=new_customers,
        new_customers_change_percent=None,
        repeat_customer_rate=0.0,  # Would need to calculate from customer history
        repeat_customer_rate_change_percent=None,
        customer_satisfaction_score=None,
        customer_satisfaction_score_change_percent=None,
    )

    return RevenueReport(
        metrics=metrics,
        revenue_over_time=revenue_over_time,
        service_breakdown=service_breakdown,
        date_range={"start_date": start_date, "end_date": end_date},
    )


# ==========================
# Technician Report Endpoint
# ==========================

@router.get("/technician", response_model=TechnicianReport)
async def get_technician_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get technician performance report."""
    # Default to last 30 days
    if not end_date:
        end = date.today()
        end_date = end.isoformat()
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start = end - timedelta(days=30)
        start_date = start.isoformat()
    else:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()

    # Get all technicians
    techs_result = await db.execute(select(Technician).where(Technician.is_active == True))
    technicians = techs_result.scalars().all()

    technician_metrics = []

    for tech in technicians:
        # Jobs completed by this technician
        jobs_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.assigned_technician == f"{tech.first_name} {tech.last_name}",
                    WorkOrder.status == WorkOrderStatus.completed,
                    func.date(WorkOrder.completed_at) >= start,
                    func.date(WorkOrder.completed_at) <= end,
                )
            )
        )
        jobs_completed = jobs_result.scalar() or 0

        # Estimate revenue (jobs * average job value)
        # In reality, this would join with invoices
        avg_job_value = 350.0  # Default estimate
        total_revenue = jobs_completed * avg_job_value

        # Average duration (if actual_duration_hours is tracked)
        duration_result = await db.execute(
            select(func.avg(WorkOrder.actual_duration_hours)).where(
                and_(
                    WorkOrder.assigned_technician == f"{tech.first_name} {tech.last_name}",
                    WorkOrder.status == WorkOrderStatus.completed,
                    func.date(WorkOrder.completed_at) >= start,
                    func.date(WorkOrder.completed_at) <= end,
                    WorkOrder.actual_duration_hours.isnot(None),
                )
            )
        )
        avg_duration = duration_result.scalar()

        technician_metrics.append(TechnicianMetrics(
            technician_id=str(tech.id),
            technician_name=f"{tech.first_name} {tech.last_name}",
            jobs_completed=jobs_completed,
            total_revenue=total_revenue,
            average_job_duration_hours=float(avg_duration) if avg_duration else None,
            customer_satisfaction=None,  # Would need feedback system
            on_time_completion_rate=95.0,  # Would calculate from scheduled vs actual times
        ))

    return TechnicianReport(
        technicians=technician_metrics,
        date_range={"start_date": start_date, "end_date": end_date},
    )


# ======================
# Customer Report Endpoint
# ======================

@router.get("/customers", response_model=CustomerReport)
async def get_customer_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get customer metrics and growth report."""
    # Default to last 30 days
    if not end_date:
        end = date.today()
        end_date = end.isoformat()
    else:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

    if not start_date:
        start = end - timedelta(days=30)
        start_date = start.isoformat()
    else:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()

    # Total customers (won)
    total_result = await db.execute(
        select(func.count()).where(Customer.prospect_stage == ProspectStage.won)
    )
    total_customers = total_result.scalar() or 0

    # Active customers (won + is_active)
    active_result = await db.execute(
        select(func.count()).where(
            and_(
                Customer.prospect_stage == ProspectStage.won,
                Customer.is_active == True,
            )
        )
    )
    active_customers = active_result.scalar() or 0

    # New customers this month
    month_start = date.today().replace(day=1)
    new_month_result = await db.execute(
        select(func.count()).where(
            and_(
                Customer.prospect_stage == ProspectStage.won,
                func.date(Customer.created_at) >= month_start,
            )
        )
    )
    new_customers_this_month = new_month_result.scalar() or 0

    # Growth over time (simplified - weekly snapshots)
    growth_over_time = []
    current_date = start
    while current_date <= end:
        # Count customers created by this date
        cumulative_result = await db.execute(
            select(func.count()).where(
                and_(
                    Customer.prospect_stage == ProspectStage.won,
                    func.date(Customer.created_at) <= current_date,
                )
            )
        )
        cumulative = cumulative_result.scalar() or 0

        # New on this day
        day_new_result = await db.execute(
            select(func.count()).where(
                and_(
                    Customer.prospect_stage == ProspectStage.won,
                    func.date(Customer.created_at) == current_date,
                )
            )
        )
        day_new = day_new_result.scalar() or 0

        growth_over_time.append(CustomerGrowthDataPoint(
            date=current_date.isoformat(),
            total_customers=cumulative,
            new_customers=day_new,
            active_customers=cumulative,  # Simplified
        ))

        # Move to next week for longer ranges
        current_date += timedelta(days=7 if (end - start).days > 30 else 1)

    metrics = CustomerMetrics(
        total_customers=total_customers,
        total_customers_change_percent=None,
        active_customers=active_customers,
        active_customers_change_percent=None,
        new_customers_this_month=new_customers_this_month,
        churn_rate=None,
        average_customer_lifetime_value=None,
    )

    return CustomerReport(
        metrics=metrics,
        growth_over_time=growth_over_time,
        date_range={"start_date": start_date, "end_date": end_date},
    )


# =======================
# Pipeline Report Endpoint
# =======================

@router.get("/pipeline", response_model=PipelineMetrics)
async def get_pipeline_metrics(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get pipeline metrics for prospects/leads."""
    prospect_stages = [
        ProspectStage.new_lead,
        ProspectStage.contacted,
        ProspectStage.qualified,
        ProspectStage.quoted,
        ProspectStage.negotiation,
    ]

    # Total prospects
    total_result = await db.execute(
        select(func.count()).where(Customer.prospect_stage.in_(prospect_stages))
    )
    total_prospects = total_result.scalar() or 0

    # Prospects by stage
    prospects_by_stage = []
    for stage in prospect_stages:
        stage_result = await db.execute(
            select(func.count()).where(Customer.prospect_stage == stage)
        )
        count = stage_result.scalar() or 0

        # Estimate value per stage (would need estimated_value field)
        estimated_value = count * 500  # Default estimate

        prospects_by_stage.append(ProspectsByStage(
            stage=stage.value,
            count=count,
            total_value=estimated_value,
        ))

    # Calculate pipeline value
    total_pipeline_value = sum(p.total_value for p in prospects_by_stage)

    # Conversion rate (won / (won + lost) in last 30 days)
    won_result = await db.execute(
        select(func.count()).where(
            and_(
                Customer.prospect_stage == ProspectStage.won,
                func.date(Customer.updated_at) >= date.today() - timedelta(days=30),
            )
        )
    )
    won_count = won_result.scalar() or 0

    lost_result = await db.execute(
        select(func.count()).where(
            and_(
                Customer.prospect_stage == ProspectStage.lost,
                func.date(Customer.updated_at) >= date.today() - timedelta(days=30),
            )
        )
    )
    lost_count = lost_result.scalar() or 0

    conversion_rate = (won_count / (won_count + lost_count) * 100) if (won_count + lost_count) > 0 else None

    # Average deal size
    average_deal_size = total_pipeline_value / total_prospects if total_prospects > 0 else None

    return PipelineMetrics(
        total_pipeline_value=total_pipeline_value,
        total_prospects=total_prospects,
        prospects_by_stage=prospects_by_stage,
        conversion_rate=conversion_rate,
        average_deal_size=average_deal_size,
    )
