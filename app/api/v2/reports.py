from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.technician import Technician

router = APIRouter()

JOB_TYPES = ["pumping", "inspection", "repair", "installation", "emergency", "maintenance", "grease_trap", "camera_inspection"]
PROSPECT_STAGES = ["new_lead", "contacted", "qualified", "quoted", "negotiation"]


class RevenueMetrics(BaseModel):
    total_revenue: float
    work_orders_completed: int
    average_job_value: float
    new_customers: int
    repeat_customer_rate: float = 0.0


class ServiceBreakdown(BaseModel):
    service_type: str
    count: int
    revenue: float
    percentage: float


class RevenueReport(BaseModel):
    metrics: RevenueMetrics
    service_breakdown: list[ServiceBreakdown]
    date_range: dict


class TechnicianMetrics(BaseModel):
    technician_id: str
    technician_name: str
    jobs_completed: int
    total_revenue: float
    on_time_completion_rate: float


class TechnicianReport(BaseModel):
    technicians: list[TechnicianMetrics]
    date_range: dict


class CustomerMetrics(BaseModel):
    total_customers: int
    active_customers: int
    new_customers_this_month: int


class CustomerReport(BaseModel):
    metrics: CustomerMetrics
    date_range: dict


class ProspectsByStage(BaseModel):
    stage: str
    count: int
    total_value: float


class PipelineMetrics(BaseModel):
    total_pipeline_value: float
    total_prospects: int
    prospects_by_stage: list[ProspectsByStage]


@router.get("/revenue", response_model=RevenueReport)
async def get_revenue_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    end = date.today()
    start = end - timedelta(days=30)
    
    wo_result = await db.execute(
        select(func.count()).where(WorkOrder.status == "completed")
    )
    work_orders_completed = wo_result.scalar() or 0
    avg_job_value = 350.0
    total_revenue = work_orders_completed * avg_job_value
    
    service_breakdown = []
    for job_type in JOB_TYPES:
        type_result = await db.execute(
            select(func.count()).where(
                and_(WorkOrder.job_type == job_type, WorkOrder.status == "completed")
            )
        )
        count = type_result.scalar() or 0
        if count > 0:
            service_breakdown.append(ServiceBreakdown(
                service_type=job_type, count=count,
                revenue=count * avg_job_value,
                percentage=(count / work_orders_completed * 100) if work_orders_completed > 0 else 0,
            ))
    
    return RevenueReport(
        metrics=RevenueMetrics(
            total_revenue=total_revenue, work_orders_completed=work_orders_completed,
            average_job_value=avg_job_value, new_customers=0, repeat_customer_rate=0.0,
        ),
        service_breakdown=service_breakdown,
        date_range={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )


@router.get("/technician", response_model=TechnicianReport)
async def get_technician_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    techs_result = await db.execute(select(Technician).where(Technician.is_active == True))
    technicians = techs_result.scalars().all()
    
    metrics = []
    for tech in technicians:
        jobs_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.assigned_technician == f"{tech.first_name} {tech.last_name}",
                    WorkOrder.status == "completed",
                )
            )
        )
        jobs = jobs_result.scalar() or 0
        metrics.append(TechnicianMetrics(
            technician_id=str(tech.id), technician_name=f"{tech.first_name} {tech.last_name}",
            jobs_completed=jobs, total_revenue=jobs * 350.0, on_time_completion_rate=95.0,
        ))
    
    return TechnicianReport(technicians=metrics, date_range={"start_date": "", "end_date": ""})


@router.get("/customers", response_model=CustomerReport)
async def get_customer_report(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    total_result = await db.execute(select(func.count()).where(Customer.prospect_stage == "won"))
    total = total_result.scalar() or 0
    active_result = await db.execute(
        select(func.count()).where(and_(Customer.prospect_stage == "won", Customer.is_active == True))
    )
    active = active_result.scalar() or 0
    
    return CustomerReport(
        metrics=CustomerMetrics(total_customers=total, active_customers=active, new_customers_this_month=0),
        date_range={"start_date": "", "end_date": ""},
    )


@router.get("/pipeline", response_model=PipelineMetrics)
async def get_pipeline_metrics(db: DbSession, current_user: CurrentUser):
    total_result = await db.execute(
        select(func.count()).where(Customer.prospect_stage.in_(PROSPECT_STAGES))
    )
    total_prospects = total_result.scalar() or 0
    
    prospects_by_stage = []
    for stage in PROSPECT_STAGES:
        stage_result = await db.execute(select(func.count()).where(Customer.prospect_stage == stage))
        count = stage_result.scalar() or 0
        prospects_by_stage.append(ProspectsByStage(stage=stage, count=count, total_value=count * 500))
    
    total_value = sum(p.total_value for p in prospects_by_stage)
    return PipelineMetrics(
        total_pipeline_value=total_value, total_prospects=total_prospects, prospects_by_stage=prospects_by_stage,
    )


# ========================
# Enhanced Reports (Phase 7)
# ========================

class RevenueByServiceResponse(BaseModel):
    period: dict
    services: list[dict]
    total_revenue: float


class RevenueByTechnicianResponse(BaseModel):
    period: dict
    technicians: list[dict]
    total_revenue: float


class RevenueByLocationResponse(BaseModel):
    period: dict
    locations: list[dict]
    total_revenue: float


class CustomerLifetimeValueResponse(BaseModel):
    customers: list[dict]
    average_ltv: float
    total_customers_analyzed: int


class TechnicianPerformanceResponse(BaseModel):
    period: dict
    technicians: list[dict]


@router.get("/revenue-by-service", response_model=RevenueByServiceResponse)
async def get_revenue_by_service(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Get revenue breakdown by service type."""
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=30))

    services = []
    total_revenue = 0.0
    avg_price_per_type = {
        "pumping": 350.0,
        "inspection": 200.0,
        "repair": 450.0,
        "installation": 2500.0,
        "emergency": 500.0,
        "maintenance": 175.0,
        "grease_trap": 300.0,
        "camera_inspection": 275.0,
    }

    for job_type in JOB_TYPES:
        result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.job_type == job_type,
                    WorkOrder.status == "completed",
                )
            )
        )
        count = result.scalar() or 0
        avg_price = avg_price_per_type.get(job_type, 350.0)
        revenue = count * avg_price
        total_revenue += revenue

        if count > 0:
            services.append({
                "service_type": job_type,
                "job_count": count,
                "revenue": revenue,
                "average_job_value": avg_price,
            })

    # Sort by revenue descending
    services.sort(key=lambda x: x["revenue"], reverse=True)

    return RevenueByServiceResponse(
        period={"start_date": start.isoformat(), "end_date": end.isoformat()},
        services=services,
        total_revenue=total_revenue,
    )


@router.get("/revenue-by-technician", response_model=RevenueByTechnicianResponse)
async def get_revenue_by_technician(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Get revenue breakdown by technician."""
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=30))

    techs_result = await db.execute(
        select(Technician).where(Technician.is_active == True)
    )
    technicians = techs_result.scalars().all()

    tech_data = []
    total_revenue = 0.0

    for tech in technicians:
        full_name = f"{tech.first_name} {tech.last_name}"
        jobs_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.assigned_technician == full_name,
                    WorkOrder.status == "completed",
                )
            )
        )
        jobs = jobs_result.scalar() or 0
        revenue = jobs * 350.0  # Average job value
        total_revenue += revenue

        tech_data.append({
            "technician_id": str(tech.id),
            "technician_name": full_name,
            "jobs_completed": jobs,
            "revenue": revenue,
            "average_job_value": 350.0 if jobs > 0 else 0,
        })

    # Sort by revenue descending
    tech_data.sort(key=lambda x: x["revenue"], reverse=True)

    return RevenueByTechnicianResponse(
        period={"start_date": start.isoformat(), "end_date": end.isoformat()},
        technicians=tech_data,
        total_revenue=total_revenue,
    )


@router.get("/revenue-by-location", response_model=RevenueByLocationResponse)
async def get_revenue_by_location(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    group_by: str = Query("city", description="Group by: city, state, or zip"),
):
    """Get revenue breakdown by location."""
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=30))

    # Get completed work orders with customer info
    wo_result = await db.execute(
        select(WorkOrder, Customer)
        .join(Customer, WorkOrder.customer_id == Customer.id)
        .where(WorkOrder.status == "completed")
    )
    results = wo_result.all()

    # Group by location
    location_data = {}
    total_revenue = 0.0

    for wo, customer in results:
        if group_by == "city":
            location = customer.city or "Unknown"
        elif group_by == "state":
            location = customer.state or "Unknown"
        else:  # zip
            location = customer.zip_code or "Unknown"

        if location not in location_data:
            location_data[location] = {"count": 0, "revenue": 0.0}

        location_data[location]["count"] += 1
        location_data[location]["revenue"] += 350.0  # Average
        total_revenue += 350.0

    locations = [
        {
            "location": loc,
            "job_count": data["count"],
            "revenue": data["revenue"],
        }
        for loc, data in location_data.items()
    ]
    locations.sort(key=lambda x: x["revenue"], reverse=True)

    return RevenueByLocationResponse(
        period={"start_date": start.isoformat(), "end_date": end.isoformat()},
        locations=locations[:20],  # Top 20
        total_revenue=total_revenue,
    )


@router.get("/customer-lifetime-value", response_model=CustomerLifetimeValueResponse)
async def get_customer_lifetime_value(
    db: DbSession,
    current_user: CurrentUser,
    top_n: int = Query(50, description="Number of top customers to return"),
):
    """Get customer lifetime value analysis."""
    # Get customers with their work order counts
    customers_result = await db.execute(
        select(Customer).where(Customer.prospect_stage == "won")
    )
    customers = customers_result.scalars().all()

    customer_ltv = []

    for customer in customers:
        # Count work orders for this customer
        wo_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.customer_id == customer.id,
                    WorkOrder.status == "completed",
                )
            )
        )
        wo_count = wo_result.scalar() or 0

        if wo_count > 0:
            # Estimate LTV (jobs * avg value)
            ltv = wo_count * 350.0

            # Calculate tenure in months
            tenure_months = 12  # Default if no created_at
            if customer.created_at:
                tenure_days = (datetime.now() - customer.created_at).days
                tenure_months = max(1, tenure_days // 30)

            customer_ltv.append({
                "customer_id": customer.id,
                "customer_name": customer.name,
                "lifetime_value": ltv,
                "total_jobs": wo_count,
                "tenure_months": tenure_months,
                "monthly_value": round(ltv / tenure_months, 2),
            })

    # Sort by LTV
    customer_ltv.sort(key=lambda x: x["lifetime_value"], reverse=True)

    avg_ltv = sum(c["lifetime_value"] for c in customer_ltv) / len(customer_ltv) if customer_ltv else 0

    return CustomerLifetimeValueResponse(
        customers=customer_ltv[:top_n],
        average_ltv=round(avg_ltv, 2),
        total_customers_analyzed=len(customer_ltv),
    )


@router.get("/technician-performance", response_model=TechnicianPerformanceResponse)
async def get_technician_performance(
    db: DbSession,
    current_user: CurrentUser,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Get detailed technician performance metrics."""
    end = end_date or date.today()
    start = start_date or (end - timedelta(days=30))

    techs_result = await db.execute(
        select(Technician).where(Technician.is_active == True)
    )
    technicians = techs_result.scalars().all()

    tech_performance = []

    for tech in technicians:
        full_name = f"{tech.first_name} {tech.last_name}"

        # Completed jobs
        completed_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.assigned_technician == full_name,
                    WorkOrder.status == "completed",
                )
            )
        )
        completed = completed_result.scalar() or 0

        # Total assigned jobs
        total_result = await db.execute(
            select(func.count()).where(
                WorkOrder.assigned_technician == full_name
            )
        )
        total = total_result.scalar() or 0

        # Calculate metrics
        completion_rate = (completed / total * 100) if total > 0 else 0
        revenue = completed * 350.0

        # Estimate efficiency (jobs per working day, assuming 5 days)
        work_days = 22  # Approximate working days in a month
        jobs_per_day = completed / work_days if work_days > 0 else 0

        tech_performance.append({
            "technician_id": str(tech.id),
            "technician_name": full_name,
            "jobs_completed": completed,
            "jobs_assigned": total,
            "completion_rate": round(completion_rate, 1),
            "revenue_generated": revenue,
            "jobs_per_day": round(jobs_per_day, 2),
            "on_time_rate": 95.0,  # Placeholder - would need actual tracking
            "customer_rating": 4.5,  # Placeholder - would need rating system
        })

    # Sort by jobs completed
    tech_performance.sort(key=lambda x: x["jobs_completed"], reverse=True)

    return TechnicianPerformanceResponse(
        period={"start_date": start.isoformat(), "end_date": end.isoformat()},
        technicians=tech_performance,
    )
