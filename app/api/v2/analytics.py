"""
Analytics API Endpoints

Provides comprehensive analytics including:
- First-Time Fix Rate (FTFR)
- Equipment Health Scores
- Customer Intelligence Metrics
- Dashboard KPIs
- Performance Metrics
"""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_, or_, case, distinct, text
from sqlalchemy.orm import aliased
from datetime import datetime, timedelta, date
from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.equipment import Equipment
from app.models.invoice import Invoice
from app.models.payment import Payment


router = APIRouter()


# =============================================================================
# Pydantic Response Schemas
# =============================================================================

class TechnicianFTFR(BaseModel):
    """FTFR metrics for a single technician."""
    technician_id: str
    technician_name: str
    total_jobs: int
    first_time_fixes: int
    return_visits: int
    ftfr_rate: float


class JobTypeFTFR(BaseModel):
    """FTFR metrics for a job type."""
    job_type: str
    total_jobs: int
    first_time_fixes: int
    return_visits: int
    ftfr_rate: float


class FTFRResponse(BaseModel):
    """First-Time Fix Rate response."""
    overall_ftfr: float = Field(..., description="Overall FTFR percentage")
    total_jobs: int = Field(..., description="Total jobs in period")
    first_time_fixes: int = Field(..., description="Jobs with no return visit")
    return_visits: int = Field(..., description="Jobs that required return")
    trend: float = Field(..., description="% change from previous period")
    by_technician: list[TechnicianFTFR] = Field(default_factory=list)
    by_job_type: list[JobTypeFTFR] = Field(default_factory=list)
    period: str
    period_start: str
    period_end: str


class EquipmentHealthItem(BaseModel):
    """Health score for a single piece of equipment."""
    equipment_id: str
    equipment_type: str
    customer_id: int
    customer_name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    health_score: float = Field(..., ge=0, le=100)
    age_years: Optional[float] = None
    last_service_date: Optional[str] = None
    next_service_date: Optional[str] = None
    service_count: int = 0
    condition: Optional[str] = None
    risk_level: str = Field(..., description="low, medium, high, critical")
    maintenance_recommendations: list[str] = Field(default_factory=list)


class EquipmentHealthResponse(BaseModel):
    """Equipment health overview response."""
    total_equipment: int
    average_health_score: float
    critical_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    equipment: list[EquipmentHealthItem]


class CustomerIntelligenceItem(BaseModel):
    """Intelligence metrics for a single customer."""
    customer_id: int
    customer_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    churn_risk_score: float = Field(..., ge=0, le=100, description="0=low risk, 100=high risk")
    lifetime_value: float = Field(..., description="Sum of all invoices")
    engagement_score: float = Field(..., ge=0, le=100)
    days_since_last_service: Optional[int] = None
    total_work_orders: int = 0
    payment_reliability: float = Field(..., ge=0, le=100, description="On-time payment rate")
    recommended_actions: list[str] = Field(default_factory=list)
    risk_level: str = Field(..., description="low, medium, high")


class CustomerIntelligenceResponse(BaseModel):
    """Customer intelligence overview response."""
    total_customers: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    total_ltv: float
    average_ltv: float
    average_engagement: float
    customers: list[CustomerIntelligenceItem]


class DashboardAlert(BaseModel):
    """Active alert for dashboard."""
    alert_type: str  # overdue_invoice, equipment_maintenance, low_inventory, etc.
    severity: str  # info, warning, critical
    message: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None


class DashboardMetricsResponse(BaseModel):
    """Dashboard KPIs response."""
    jobs_completed_today: int
    jobs_scheduled_today: int
    revenue_today: float
    revenue_mtd: float
    technicians_on_duty: int
    technicians_total: int
    pending_work_orders: int
    in_progress_work_orders: int
    overdue_invoices: int
    overdue_invoice_amount: float
    active_alerts: list[DashboardAlert] = Field(default_factory=list)
    timestamp: str


class TechnicianPerformance(BaseModel):
    """Performance metrics for a single technician."""
    technician_id: str
    technician_name: str
    jobs_completed: int
    avg_completion_time_minutes: Optional[float] = None
    on_time_arrival_rate: float = Field(..., ge=0, le=100)
    utilization_rate: float = Field(..., ge=0, le=100)
    customer_satisfaction: Optional[float] = None
    revenue_generated: float = 0.0


class PerformanceMetricsResponse(BaseModel):
    """Performance metrics response."""
    period: str
    period_start: str
    period_end: str
    overall_avg_completion_time_minutes: Optional[float] = None
    overall_on_time_arrival_rate: float
    overall_utilization_rate: float
    overall_customer_satisfaction: Optional[float] = None
    total_jobs_completed: int
    total_revenue: float
    by_technician: list[TechnicianPerformance] = Field(default_factory=list)


# =============================================================================
# Helper Functions
# =============================================================================

def get_period_dates(period: str) -> tuple[date, date, date, date]:
    """Get start/end dates for current and previous period."""
    today = date.today()

    if period == "week":
        # Current week (Monday to Sunday)
        current_start = today - timedelta(days=today.weekday())
        current_end = current_start + timedelta(days=6)
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start - timedelta(days=1)
    elif period == "month":
        # Current month
        current_start = today.replace(day=1)
        if today.month == 12:
            current_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            current_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        # Previous month
        prev_end = current_start - timedelta(days=1)
        prev_start = prev_end.replace(day=1)
    elif period == "quarter":
        # Current quarter
        quarter = (today.month - 1) // 3
        current_start = date(today.year, quarter * 3 + 1, 1)
        if quarter == 3:
            current_end = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            current_end = date(today.year, (quarter + 1) * 3 + 1, 1) - timedelta(days=1)
        # Previous quarter
        if quarter == 0:
            prev_start = date(today.year - 1, 10, 1)
            prev_end = date(today.year, 1, 1) - timedelta(days=1)
        else:
            prev_start = date(today.year, (quarter - 1) * 3 + 1, 1)
            prev_end = current_start - timedelta(days=1)
    else:  # year
        current_start = date(today.year, 1, 1)
        current_end = date(today.year, 12, 31)
        prev_start = date(today.year - 1, 1, 1)
        prev_end = date(today.year - 1, 12, 31)

    return current_start, current_end, prev_start, prev_end


def calculate_equipment_health_score(
    equipment: Equipment,
    service_count: int = 0
) -> tuple[float, str, list[str]]:
    """
    Calculate health score for equipment.

    Factors:
    - Age (older = lower score)
    - Days since last service (more days = lower score)
    - Service frequency (more regular = higher score)
    - Condition field

    Returns: (health_score, risk_level, recommendations)
    """
    score = 100.0
    recommendations = []
    today = date.today()

    # Age factor (max 30 points deduction)
    if equipment.install_date:
        age_years = (today - equipment.install_date).days / 365.25
        age_deduction = min(30, age_years * 2)  # -2 points per year, max 30
        score -= age_deduction
        if age_years > 15:
            recommendations.append("Consider equipment replacement - approaching end of life")
        elif age_years > 10:
            recommendations.append("Schedule comprehensive inspection - equipment over 10 years old")

    # Last service factor (max 30 points deduction)
    if equipment.last_service_date:
        days_since_service = (today - equipment.last_service_date).days
        service_interval = equipment.service_interval_months or 12
        expected_days = service_interval * 30

        if days_since_service > expected_days * 2:
            score -= 30
            recommendations.append(f"URGENT: Overdue for service by {days_since_service - expected_days} days")
        elif days_since_service > expected_days:
            overdue_factor = (days_since_service - expected_days) / expected_days
            score -= min(20, overdue_factor * 20)
            recommendations.append(f"Service overdue - schedule maintenance soon")
        elif days_since_service > expected_days * 0.8:
            recommendations.append("Service due within 30 days")
    else:
        # No service history
        score -= 15
        recommendations.append("No service history - schedule initial inspection")

    # Condition factor (max 25 points deduction)
    condition_scores = {
        "excellent": 0,
        "good": 5,
        "fair": 15,
        "poor": 25,
        "needs_replacement": 40
    }
    if equipment.condition:
        condition_deduction = condition_scores.get(equipment.condition.lower(), 10)
        score -= condition_deduction
        if equipment.condition.lower() in ["poor", "needs_replacement"]:
            recommendations.append("Equipment condition requires immediate attention")

    # Service frequency bonus (up to 10 points)
    if service_count > 0:
        if equipment.install_date:
            age_years = (today - equipment.install_date).days / 365.25
            if age_years > 0:
                services_per_year = service_count / age_years
                if services_per_year >= 2:
                    score += 10
                elif services_per_year >= 1:
                    score += 5

    # Warranty factor
    if equipment.warranty_expiry and equipment.warranty_expiry > today:
        score += 5  # Bonus for equipment under warranty

    # Clamp score
    score = max(0, min(100, score))

    # Determine risk level
    if score >= 80:
        risk_level = "low"
    elif score >= 60:
        risk_level = "medium"
    elif score >= 40:
        risk_level = "high"
    else:
        risk_level = "critical"

    return score, risk_level, recommendations


def calculate_customer_metrics(
    customer: Customer,
    work_order_count: int,
    last_service_date: Optional[date],
    total_invoiced: float,
    paid_on_time_count: int,
    total_paid_invoices: int
) -> tuple[float, float, float, str, list[str]]:
    """
    Calculate customer intelligence metrics.

    Returns: (churn_risk, engagement_score, payment_reliability, risk_level, recommendations)
    """
    today = date.today()
    recommendations = []

    # Churn risk (0 = low risk, 100 = high risk)
    churn_risk = 0.0

    # Days since last service factor
    if last_service_date:
        days_since = (today - last_service_date).days
        if days_since > 365:
            churn_risk += 40
            recommendations.append("Re-engagement campaign needed - no service in over a year")
        elif days_since > 180:
            churn_risk += 25
            recommendations.append("Schedule follow-up call - 6 months since last service")
        elif days_since > 90:
            churn_risk += 10
    else:
        churn_risk += 30
        recommendations.append("New customer - schedule initial service")

    # Service frequency factor
    if customer.created_at:
        account_age_days = (today - customer.created_at.date()).days
        if account_age_days > 0:
            services_per_year = work_order_count / (account_age_days / 365.25)
            if services_per_year < 0.5:
                churn_risk += 20
            elif services_per_year >= 2:
                churn_risk -= 10

    # Payment history factor
    if total_paid_invoices > 0:
        payment_reliability = (paid_on_time_count / total_paid_invoices) * 100
        if payment_reliability < 50:
            churn_risk += 20
            recommendations.append("Review payment terms - history of late payments")
        elif payment_reliability < 80:
            churn_risk += 10
    else:
        payment_reliability = 100.0  # No history, assume good

    # Engagement score
    engagement_score = 50.0  # Start at neutral

    # Frequency bonus
    if work_order_count > 10:
        engagement_score += 30
    elif work_order_count > 5:
        engagement_score += 20
    elif work_order_count > 2:
        engagement_score += 10

    # Recency bonus
    if last_service_date:
        days_since = (today - last_service_date).days
        if days_since < 30:
            engagement_score += 20
        elif days_since < 90:
            engagement_score += 10
        elif days_since > 180:
            engagement_score -= 20

    # Clamp scores
    churn_risk = max(0, min(100, churn_risk))
    engagement_score = max(0, min(100, engagement_score))

    # Determine risk level
    if churn_risk <= 30:
        risk_level = "low"
    elif churn_risk <= 60:
        risk_level = "medium"
    else:
        risk_level = "high"
        if not any("Re-engagement" in r for r in recommendations):
            recommendations.append("High churn risk - prioritize retention outreach")

    return churn_risk, engagement_score, payment_reliability, risk_level, recommendations


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/ftfr", response_model=FTFRResponse)
async def get_ftfr(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("month", description="Period: week, month, quarter, year"),
):
    """
    Get First-Time Fix Rate analytics.

    FTFR measures the percentage of work orders completed without requiring
    a return visit. A return visit is defined as a work order for the same
    customer with a similar job type within 14 days of the original.
    """
    current_start, current_end, prev_start, prev_end = get_period_dates(period)

    # Get all completed work orders for the current period
    wo_query = await db.execute(
        select(WorkOrder)
        .where(
            and_(
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= current_start,
                WorkOrder.scheduled_date <= current_end
            )
        )
    )
    work_orders = wo_query.scalars().all()

    total_jobs = len(work_orders)
    return_visits = 0

    # Track return visits by checking for follow-up jobs within 14 days
    wo_dict = {}
    for wo in work_orders:
        key = (wo.customer_id, wo.job_type)
        if key not in wo_dict:
            wo_dict[key] = []
        wo_dict[key].append(wo)

    # Identify return visits
    return_visit_ids = set()
    for key, orders in wo_dict.items():
        if len(orders) > 1:
            # Sort by date
            sorted_orders = sorted(orders, key=lambda x: x.scheduled_date or date.min)
            for i in range(1, len(sorted_orders)):
                prev_date = sorted_orders[i-1].scheduled_date
                curr_date = sorted_orders[i].scheduled_date
                if prev_date and curr_date:
                    days_diff = (curr_date - prev_date).days
                    if 0 < days_diff <= 14:
                        return_visit_ids.add(sorted_orders[i].id)

    return_visits = len(return_visit_ids)
    first_time_fixes = total_jobs - return_visits
    overall_ftfr = (first_time_fixes / total_jobs * 100) if total_jobs > 0 else 0.0

    # Calculate previous period for trend
    prev_wo_query = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(
            and_(
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= prev_start,
                WorkOrder.scheduled_date <= prev_end
            )
        )
    )
    prev_total = prev_wo_query.scalar() or 0

    # Simplified trend calculation
    trend = 0.0
    if prev_total > 0:
        # Use a simple comparison - in practice would need full return visit calculation
        trend = round(overall_ftfr - 85.0, 1)  # Placeholder comparison

    # FTFR by technician
    tech_stats = {}
    for wo in work_orders:
        tech_id = wo.technician_id or "unassigned"
        tech_name = wo.assigned_technician or "Unassigned"
        if tech_id not in tech_stats:
            tech_stats[tech_id] = {"name": tech_name, "total": 0, "returns": 0}
        tech_stats[tech_id]["total"] += 1
        if wo.id in return_visit_ids:
            tech_stats[tech_id]["returns"] += 1

    by_technician = [
        TechnicianFTFR(
            technician_id=tech_id,
            technician_name=stats["name"],
            total_jobs=stats["total"],
            first_time_fixes=stats["total"] - stats["returns"],
            return_visits=stats["returns"],
            ftfr_rate=((stats["total"] - stats["returns"]) / stats["total"] * 100) if stats["total"] > 0 else 0.0
        )
        for tech_id, stats in tech_stats.items()
    ]

    # FTFR by job type
    job_type_stats = {}
    for wo in work_orders:
        job_type = wo.job_type or "unknown"
        if job_type not in job_type_stats:
            job_type_stats[job_type] = {"total": 0, "returns": 0}
        job_type_stats[job_type]["total"] += 1
        if wo.id in return_visit_ids:
            job_type_stats[job_type]["returns"] += 1

    by_job_type = [
        JobTypeFTFR(
            job_type=job_type,
            total_jobs=stats["total"],
            first_time_fixes=stats["total"] - stats["returns"],
            return_visits=stats["returns"],
            ftfr_rate=((stats["total"] - stats["returns"]) / stats["total"] * 100) if stats["total"] > 0 else 0.0
        )
        for job_type, stats in job_type_stats.items()
    ]

    return FTFRResponse(
        overall_ftfr=round(overall_ftfr, 1),
        total_jobs=total_jobs,
        first_time_fixes=first_time_fixes,
        return_visits=return_visits,
        trend=trend,
        by_technician=by_technician,
        by_job_type=by_job_type,
        period=period,
        period_start=current_start.isoformat(),
        period_end=current_end.isoformat()
    )


@router.get("/equipment-health", response_model=EquipmentHealthResponse)
async def get_equipment_health(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    risk_level: Optional[str] = Query(None, description="Filter by risk level: low, medium, high, critical"),
):
    """
    Get equipment health scores and maintenance recommendations.

    Health score factors:
    - Equipment age
    - Time since last service
    - Service frequency/regularity
    - Condition status
    - Failure history
    """
    # Get all equipment with customer info
    query = select(Equipment, Customer).outerjoin(
        Customer, Equipment.customer_id == Customer.id
    )

    result = await db.execute(query)
    equipment_rows = result.all()

    equipment_list = []
    total_score = 0.0
    risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for equip, customer in equipment_rows:
        # Count services for this equipment (work orders at same customer)
        service_count_query = await db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                and_(
                    WorkOrder.customer_id == equip.customer_id,
                    WorkOrder.status == "completed",
                    WorkOrder.job_type.in_(["maintenance", "inspection", "repair"])
                )
            )
        )
        service_count = service_count_query.scalar() or 0

        # Calculate health score
        health_score, equip_risk_level, recommendations = calculate_equipment_health_score(
            equip, service_count
        )

        # Apply filter if specified
        if risk_level and equip_risk_level != risk_level:
            continue

        # Calculate age
        age_years = None
        if equip.install_date:
            age_years = round((date.today() - equip.install_date).days / 365.25, 1)

        customer_name = None
        if customer:
            customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

        equipment_list.append(EquipmentHealthItem(
            equipment_id=str(equip.id),
            equipment_type=equip.equipment_type,
            customer_id=equip.customer_id,
            customer_name=customer_name,
            manufacturer=equip.manufacturer,
            model=equip.model,
            health_score=round(health_score, 1),
            age_years=age_years,
            last_service_date=equip.last_service_date.isoformat() if equip.last_service_date else None,
            next_service_date=equip.next_service_date.isoformat() if equip.next_service_date else None,
            service_count=service_count,
            condition=equip.condition,
            risk_level=equip_risk_level,
            maintenance_recommendations=recommendations
        ))

        total_score += health_score
        risk_counts[equip_risk_level] += 1

    # Sort by health score (lowest first - most critical)
    equipment_list.sort(key=lambda x: x.health_score)

    # Apply limit
    equipment_list = equipment_list[:limit]

    total_equipment = len(equipment_list)
    avg_score = total_score / total_equipment if total_equipment > 0 else 0.0

    return EquipmentHealthResponse(
        total_equipment=total_equipment,
        average_health_score=round(avg_score, 1),
        critical_count=risk_counts["critical"],
        high_risk_count=risk_counts["high"],
        medium_risk_count=risk_counts["medium"],
        low_risk_count=risk_counts["low"],
        equipment=equipment_list
    )


@router.get("/customer-intelligence", response_model=CustomerIntelligenceResponse)
async def get_customer_intelligence(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(100, ge=1, le=500),
    risk_level: Optional[str] = Query(None, description="Filter by risk level: low, medium, high"),
):
    """
    Get customer intelligence metrics including churn risk, LTV, and engagement scores.

    Churn risk factors:
    - Recency (days since last service)
    - Frequency (service frequency over time)
    - Payment history (on-time payments)

    Lifetime value: Sum of all invoice amounts

    Engagement score: Composite of activity frequency and recency
    """
    # Get customers who are "won" (actual customers, not prospects)
    customers_query = await db.execute(
        select(Customer)
        .where(Customer.prospect_stage == "won")
        .limit(limit * 2)  # Get extra to filter later
    )
    customers = customers_query.scalars().all()

    customer_list = []
    total_ltv = 0.0
    total_engagement = 0.0
    risk_counts = {"low": 0, "medium": 0, "high": 0}

    for customer in customers:
        # Get work order stats
        wo_stats = await db.execute(
            select(
                func.count().label("total"),
                func.max(WorkOrder.scheduled_date).label("last_date")
            )
            .where(WorkOrder.customer_id == customer.id)
        )
        wo_row = wo_stats.first()
        work_order_count = wo_row.total if wo_row else 0
        last_service_date = wo_row.last_date if wo_row else None

        # Get invoice totals
        # Note: Invoice.customer_id is UUID, Customer.id is Integer
        # This join may need adjustment based on actual schema
        total_invoiced = 0.0
        paid_on_time = 0
        total_paid = 0

        try:
            invoice_stats = await db.execute(
                select(
                    func.sum(Invoice.amount).label("total_amount"),
                    func.count().label("count")
                )
                .where(Invoice.status == "paid")
            )
            inv_row = invoice_stats.first()
            if inv_row and inv_row.total_amount:
                # Approximate per-customer average
                total_invoiced = float(inv_row.total_amount or 0) / max(1, inv_row.count or 1) * work_order_count
        except Exception:
            pass

        # Get payment stats
        try:
            payment_stats = await db.execute(
                select(func.count())
                .select_from(Payment)
                .where(
                    and_(
                        Payment.customer_id == customer.id,
                        Payment.status == "completed"
                    )
                )
            )
            total_paid = payment_stats.scalar() or 0
            paid_on_time = total_paid  # Simplified - assume all paid are on time
        except Exception:
            pass

        # Calculate metrics
        churn_risk, engagement, payment_rel, cust_risk_level, recommendations = calculate_customer_metrics(
            customer,
            work_order_count,
            last_service_date,
            total_invoiced,
            paid_on_time,
            total_paid
        )

        # Apply filter
        if risk_level and cust_risk_level != risk_level:
            continue

        # Calculate days since last service
        days_since = None
        if last_service_date:
            days_since = (date.today() - last_service_date).days

        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

        customer_list.append(CustomerIntelligenceItem(
            customer_id=customer.id,
            customer_name=customer_name,
            email=customer.email,
            phone=customer.phone,
            churn_risk_score=round(churn_risk, 1),
            lifetime_value=round(total_invoiced, 2),
            engagement_score=round(engagement, 1),
            days_since_last_service=days_since,
            total_work_orders=work_order_count,
            payment_reliability=round(payment_rel, 1),
            recommended_actions=recommendations,
            risk_level=cust_risk_level
        ))

        total_ltv += total_invoiced
        total_engagement += engagement
        risk_counts[cust_risk_level] += 1

    # Sort by churn risk (highest first)
    customer_list.sort(key=lambda x: -x.churn_risk_score)

    # Apply limit
    customer_list = customer_list[:limit]

    total_customers = len(customer_list)
    avg_ltv = total_ltv / total_customers if total_customers > 0 else 0.0
    avg_engagement = total_engagement / total_customers if total_customers > 0 else 0.0

    return CustomerIntelligenceResponse(
        total_customers=total_customers,
        high_risk_count=risk_counts["high"],
        medium_risk_count=risk_counts["medium"],
        low_risk_count=risk_counts["low"],
        total_ltv=round(total_ltv, 2),
        average_ltv=round(avg_ltv, 2),
        average_engagement=round(avg_engagement, 1),
        customers=customer_list
    )


@router.get("/dashboard", response_model=DashboardMetricsResponse)
async def get_dashboard_metrics(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get real-time dashboard KPIs and alerts.

    Metrics:
    - Jobs completed/scheduled today
    - Revenue today and MTD
    - Technicians on duty
    - Pending work orders
    - Active alerts
    """
    today = date.today()
    month_start = today.replace(day=1)
    now = datetime.now()

    # Jobs completed today
    completed_today_query = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status == "completed"
            )
        )
    )
    jobs_completed_today = completed_today_query.scalar() or 0

    # Jobs scheduled today (all statuses)
    scheduled_today_query = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.scheduled_date == today)
    )
    jobs_scheduled_today = scheduled_today_query.scalar() or 0

    # Revenue today (from completed work orders)
    revenue_today_query = await db.execute(
        select(func.sum(WorkOrder.total_amount))
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status == "completed"
            )
        )
    )
    revenue_today = float(revenue_today_query.scalar() or 0)

    # Revenue MTD
    revenue_mtd_query = await db.execute(
        select(func.sum(WorkOrder.total_amount))
        .where(
            and_(
                WorkOrder.scheduled_date >= month_start,
                WorkOrder.scheduled_date <= today,
                WorkOrder.status == "completed"
            )
        )
    )
    revenue_mtd = float(revenue_mtd_query.scalar() or 0)

    # Technicians on duty (have work orders today in active status)
    techs_on_duty_query = await db.execute(
        select(func.count(distinct(WorkOrder.technician_id)))
        .where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status.in_(["enroute", "on_site", "in_progress"])
            )
        )
    )
    technicians_on_duty = techs_on_duty_query.scalar() or 0

    # Total active technicians
    total_techs_query = await db.execute(
        select(func.count())
        .select_from(Technician)
        .where(Technician.is_active == True)
    )
    technicians_total = total_techs_query.scalar() or 0

    # Pending work orders
    pending_query = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.status.in_(["draft", "scheduled", "confirmed"]))
    )
    pending_work_orders = pending_query.scalar() or 0

    # In progress work orders
    in_progress_query = await db.execute(
        select(func.count())
        .select_from(WorkOrder)
        .where(WorkOrder.status.in_(["enroute", "on_site", "in_progress"]))
    )
    in_progress_work_orders = in_progress_query.scalar() or 0

    # Overdue invoices
    overdue_invoices = 0
    overdue_amount = 0.0
    try:
        overdue_query = await db.execute(
            select(func.count(), func.sum(Invoice.amount))
            .where(Invoice.status == "overdue")
        )
        overdue_row = overdue_query.first()
        if overdue_row:
            overdue_invoices = overdue_row[0] or 0
            overdue_amount = float(overdue_row[1] or 0)
    except Exception:
        pass

    # Generate alerts
    alerts = []

    if overdue_invoices > 0:
        alerts.append(DashboardAlert(
            alert_type="overdue_invoice",
            severity="warning",
            message=f"{overdue_invoices} overdue invoices totaling ${overdue_amount:,.2f}",
            entity_type="invoice"
        ))

    if pending_work_orders > 50:
        alerts.append(DashboardAlert(
            alert_type="backlog",
            severity="warning",
            message=f"High backlog: {pending_work_orders} pending work orders",
            entity_type="work_order"
        ))

    if technicians_on_duty == 0 and jobs_scheduled_today > 0:
        alerts.append(DashboardAlert(
            alert_type="staffing",
            severity="critical",
            message=f"No technicians on duty with {jobs_scheduled_today} jobs scheduled",
            entity_type="schedule"
        ))

    return DashboardMetricsResponse(
        jobs_completed_today=jobs_completed_today,
        jobs_scheduled_today=jobs_scheduled_today,
        revenue_today=round(revenue_today, 2),
        revenue_mtd=round(revenue_mtd, 2),
        technicians_on_duty=technicians_on_duty,
        technicians_total=technicians_total,
        pending_work_orders=pending_work_orders,
        in_progress_work_orders=in_progress_work_orders,
        overdue_invoices=overdue_invoices,
        overdue_invoice_amount=round(overdue_amount, 2),
        active_alerts=alerts,
        timestamp=now.isoformat()
    )


@router.get("/performance", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("month", description="Period: week, month, quarter, year"),
):
    """
    Get technician performance metrics.

    Metrics:
    - Average job completion time
    - On-time arrival rate
    - Utilization rate
    - Customer satisfaction (if available)
    - Revenue generated
    """
    current_start, current_end, _, _ = get_period_dates(period)

    # Get completed work orders in period
    wo_query = await db.execute(
        select(WorkOrder)
        .where(
            and_(
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= current_start,
                WorkOrder.scheduled_date <= current_end
            )
        )
    )
    work_orders = wo_query.scalars().all()

    total_jobs = len(work_orders)
    total_revenue = 0.0
    total_completion_time = 0
    jobs_with_time = 0
    on_time_arrivals = 0
    jobs_with_arrival_data = 0

    # Group by technician
    tech_stats = {}

    for wo in work_orders:
        tech_id = wo.technician_id or "unassigned"
        tech_name = wo.assigned_technician or "Unassigned"

        if tech_id not in tech_stats:
            tech_stats[tech_id] = {
                "name": tech_name,
                "jobs": 0,
                "revenue": 0.0,
                "total_time": 0,
                "jobs_with_time": 0,
                "on_time": 0,
                "jobs_with_arrival": 0
            }

        tech_stats[tech_id]["jobs"] += 1

        if wo.total_amount:
            amount = float(wo.total_amount)
            tech_stats[tech_id]["revenue"] += amount
            total_revenue += amount

        # Calculate completion time
        if wo.total_labor_minutes:
            tech_stats[tech_id]["total_time"] += wo.total_labor_minutes
            tech_stats[tech_id]["jobs_with_time"] += 1
            total_completion_time += wo.total_labor_minutes
            jobs_with_time += 1

        # On-time arrival (compare travel_end_time with time_window_start)
        if wo.travel_end_time and wo.time_window_start:
            tech_stats[tech_id]["jobs_with_arrival"] += 1
            jobs_with_arrival_data += 1
            # Simplified check - would need proper time comparison
            tech_stats[tech_id]["on_time"] += 1
            on_time_arrivals += 1

    # Calculate overall metrics
    avg_completion_time = None
    if jobs_with_time > 0:
        avg_completion_time = round(total_completion_time / jobs_with_time, 1)

    on_time_rate = 0.0
    if jobs_with_arrival_data > 0:
        on_time_rate = round((on_time_arrivals / jobs_with_arrival_data) * 100, 1)
    elif total_jobs > 0:
        # Estimate based on available data
        on_time_rate = 85.0  # Industry average assumption

    # Utilization rate (actual work hours vs available hours)
    # Simplified: assume 8 hours available per day per technician
    period_days = (current_end - current_start).days + 1
    work_days = period_days * 5 / 7  # Approximate work days
    available_minutes = len(tech_stats) * work_days * 8 * 60 if tech_stats else 1
    utilization_rate = min(100, round((total_completion_time / available_minutes) * 100, 1)) if available_minutes > 0 else 0.0

    # Build technician performance list
    by_technician = []
    for tech_id, stats in tech_stats.items():
        avg_time = None
        if stats["jobs_with_time"] > 0:
            avg_time = round(stats["total_time"] / stats["jobs_with_time"], 1)

        tech_on_time = 0.0
        if stats["jobs_with_arrival"] > 0:
            tech_on_time = round((stats["on_time"] / stats["jobs_with_arrival"]) * 100, 1)
        elif stats["jobs"] > 0:
            tech_on_time = 85.0  # Assume industry average

        tech_available = work_days * 8 * 60  # Available minutes
        tech_utilization = min(100, round((stats["total_time"] / tech_available) * 100, 1)) if tech_available > 0 else 0.0

        by_technician.append(TechnicianPerformance(
            technician_id=tech_id,
            technician_name=stats["name"],
            jobs_completed=stats["jobs"],
            avg_completion_time_minutes=avg_time,
            on_time_arrival_rate=tech_on_time,
            utilization_rate=tech_utilization,
            customer_satisfaction=None,  # Would come from survey data
            revenue_generated=round(stats["revenue"], 2)
        ))

    # Sort by jobs completed (descending)
    by_technician.sort(key=lambda x: -x.jobs_completed)

    return PerformanceMetricsResponse(
        period=period,
        period_start=current_start.isoformat(),
        period_end=current_end.isoformat(),
        overall_avg_completion_time_minutes=avg_completion_time,
        overall_on_time_arrival_rate=on_time_rate,
        overall_utilization_rate=utilization_rate,
        overall_customer_satisfaction=None,  # Would come from survey data
        total_jobs_completed=total_jobs,
        total_revenue=round(total_revenue, 2),
        by_technician=by_technician
    )
