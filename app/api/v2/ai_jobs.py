"""AI-powered Job Profitability Analysis endpoints.

Provides analytics and AI-driven insights for job profitability:
- Overall margin analysis
- Profitability by service type, technician, and customer segment
- Problem area identification
- Opportunity recommendations
"""

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel
from datetime import date, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.job_cost import JobCost
from app.models.work_order import WorkOrder

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Response Schemas
# ========================


class ServiceTypeProfitability(BaseModel):
    service_type: str
    revenue: float
    cost: float
    margin_percent: float
    job_count: int
    avg_duration_hours: float
    trend: str  # "up", "down", "stable"


class TechnicianProfitability(BaseModel):
    technician_id: str
    technician_name: str
    revenue_generated: float
    margin_percent: float
    efficiency_score: float
    avg_job_time: float
    callback_rate: float
    material_usage_efficiency: float


class SegmentProfitability(BaseModel):
    segment: str
    revenue: float
    margin_percent: float
    customer_count: int
    lifetime_value_avg: float
    acquisition_cost_avg: float


class ProblemArea(BaseModel):
    type: str
    name: str
    issue: str
    impact_monthly: float
    severity: str


class ProfitOpportunity(BaseModel):
    category: str
    title: str
    description: str
    potential_monthly_gain: float
    effort: str
    confidence: float


class ProfitRecommendation(BaseModel):
    priority: str
    action: str
    expected_impact: str
    implementation_steps: List[str]
    timeline: str


class JobProfitabilityAnalysis(BaseModel):
    overall_margin_percent: float
    total_revenue: float
    total_costs: float
    total_profit: float
    trend: str
    trend_percent: float
    by_service_type: List[ServiceTypeProfitability]
    by_technician: List[TechnicianProfitability]
    by_customer_segment: List[SegmentProfitability]
    problem_areas: List[ProblemArea]
    opportunities: List[ProfitOpportunity]
    recommendations: List[ProfitRecommendation]


class JobProfitability(BaseModel):
    job_id: str
    customer_name: str
    service_type: str
    technician_name: str
    revenue: float
    labor_cost: float
    material_cost: float
    overhead_cost: float
    total_cost: float
    profit: float
    margin_percent: float
    duration_hours: float
    profitable: bool
    efficiency_score: float
    issues: Optional[List[str]] = None


class PricingScenarioRequest(BaseModel):
    service_type: str
    price_change_percent: float


class PricingScenarioResponse(BaseModel):
    current_margin: float
    projected_margin: float
    current_volume: int
    projected_volume: int
    net_profit_change: float
    recommendation: str


# ========================
# Endpoints
# ========================


@router.get("/profitability/analysis", response_model=JobProfitabilityAnalysis)
async def get_profitability_analysis(
    db: DbSession,
    current_user: CurrentUser,
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
):
    """Get AI-powered profitability analysis for jobs in date range.

    Analyzes work orders and job costs to provide:
    - Overall margin metrics
    - Breakdown by service type, technician, and customer segment
    - Problem areas and opportunities
    - AI-generated recommendations
    """
    try:
        # Default to last 30 days
        if not end:
            end = date.today()
        if not start:
            start = end - timedelta(days=30)

        # Query work orders in date range
        wo_result = await db.execute(
            select(WorkOrder).where(WorkOrder.scheduled_date >= start, WorkOrder.scheduled_date <= end)
        )
        work_orders = wo_result.scalars().all()

        # Query job costs in date range
        cost_result = await db.execute(select(JobCost).where(JobCost.cost_date >= start, JobCost.cost_date <= end))
        costs = cost_result.scalars().all()

        # Calculate overall metrics
        total_revenue = sum(float(wo.total_amount or 0) for wo in work_orders)
        total_costs = sum(c.total_cost for c in costs)
        total_profit = total_revenue - total_costs
        margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0

        # Group by service type
        by_service_type = []
        service_types = {}
        for wo in work_orders:
            job_type = wo.job_type or "other"
            if job_type not in service_types:
                service_types[job_type] = {"revenue": 0, "count": 0, "duration": 0}
            service_types[job_type]["revenue"] += float(wo.total_amount or 0)
            service_types[job_type]["count"] += 1
            service_types[job_type]["duration"] += float(wo.estimated_duration_hours or 0)

        # Calculate costs by work order for service type breakdown
        costs_by_wo = {}
        for cost in costs:
            wo_id = cost.work_order_id
            if wo_id not in costs_by_wo:
                costs_by_wo[wo_id] = 0
            costs_by_wo[wo_id] += cost.total_cost

        for job_type, data in service_types.items():
            revenue = data["revenue"]
            count = data["count"]
            # Estimate cost based on proportion
            cost_estimate = (revenue / total_revenue * total_costs) if total_revenue > 0 else 0
            margin_pct = ((revenue - cost_estimate) / revenue * 100) if revenue > 0 else 0
            avg_duration = data["duration"] / count if count > 0 else 0

            by_service_type.append(
                ServiceTypeProfitability(
                    service_type=job_type.replace("_", " ").title(),
                    revenue=round(revenue, 2),
                    cost=round(cost_estimate, 2),
                    margin_percent=round(margin_pct, 1),
                    job_count=count,
                    avg_duration_hours=round(avg_duration, 2),
                    trend="stable",
                )
            )

        # Sort by revenue descending
        by_service_type.sort(key=lambda x: x.revenue, reverse=True)

        return JobProfitabilityAnalysis(
            overall_margin_percent=round(margin, 1),
            total_revenue=round(total_revenue, 2),
            total_costs=round(total_costs, 2),
            total_profit=round(total_profit, 2),
            trend="stable",
            trend_percent=0,
            by_service_type=by_service_type[:5],  # Top 5
            by_technician=[],  # TODO: Implement technician analysis
            by_customer_segment=[],  # TODO: Implement segment analysis
            problem_areas=[],  # TODO: Implement problem detection
            opportunities=[],  # TODO: Implement opportunity detection
            recommendations=[],  # TODO: Implement AI recommendations
        )

    except Exception as e:
        logger.error(f"Error in profitability analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/profitability", response_model=JobProfitability)
async def get_job_profitability(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get profitability analysis for a specific job/work order."""
    try:
        # Get work order
        wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == job_id))
        work_order = wo_result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(status_code=404, detail="Work order not found")

        # Get costs for this work order
        cost_result = await db.execute(select(JobCost).where(JobCost.work_order_id == job_id))
        costs = cost_result.scalars().all()

        revenue = float(work_order.total_amount or 0)
        labor_cost = sum(c.total_cost for c in costs if c.cost_type == "labor")
        material_cost = sum(c.total_cost for c in costs if c.cost_type == "materials")
        other_cost = sum(c.total_cost for c in costs if c.cost_type not in ("labor", "materials"))
        total_cost = labor_cost + material_cost + other_cost
        profit = revenue - total_cost
        margin = (profit / revenue * 100) if revenue > 0 else 0
        duration = float(work_order.estimated_duration_hours or 0)

        # Calculate efficiency score (simplified)
        efficiency_score = min(100, max(0, 50 + margin))

        return JobProfitability(
            job_id=job_id,
            customer_name="Customer",  # TODO: Join with customer table
            service_type=work_order.job_type or "unknown",
            technician_name=work_order.assigned_technician or "Unassigned",
            revenue=round(revenue, 2),
            labor_cost=round(labor_cost, 2),
            material_cost=round(material_cost, 2),
            overhead_cost=round(other_cost, 2),
            total_cost=round(total_cost, 2),
            profit=round(profit, 2),
            margin_percent=round(margin, 1),
            duration_hours=round(duration, 2),
            profitable=profit > 0,
            efficiency_score=round(efficiency_score, 0),
            issues=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job profitability for {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profitability/scenario", response_model=PricingScenarioResponse)
async def analyze_pricing_scenario(
    params: PricingScenarioRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Analyze what-if pricing scenarios for a service type.

    Simulates the impact of price changes on volume and profitability.
    """
    try:
        price_change = params.price_change_percent

        # Simplified price elasticity model
        # Assume -0.5 elasticity (10% price increase -> 5% volume decrease)
        elasticity = -0.5
        volume_change = price_change * elasticity

        # Base metrics (would come from actual data in production)
        current_margin = 32.0
        current_volume = 150

        projected_margin = current_margin + (price_change * 0.8)  # Not all price change flows to margin
        projected_volume = int(current_volume * (1 + volume_change / 100))

        # Net profit change estimate
        current_profit = current_margin / 100 * current_volume * 500  # Assume $500 avg job
        projected_profit = projected_margin / 100 * projected_volume * 500
        net_profit_change = projected_profit - current_profit

        # Generate recommendation
        if price_change > 10:
            recommendation = "Price increase may significantly impact volume. Consider phased approach."
        elif price_change > 0:
            recommendation = "Moderate price increase recommended with value justification."
        elif price_change < -10:
            recommendation = "Large price reduction may attract customers but significantly impact margins."
        else:
            recommendation = "Price reduction may attract new customers but impact margins."

        return PricingScenarioResponse(
            current_margin=current_margin,
            projected_margin=round(projected_margin, 1),
            current_volume=current_volume,
            projected_volume=projected_volume,
            net_profit_change=round(net_profit_change, 2),
            recommendation=recommendation,
        )

    except Exception as e:
        logger.error(f"Error analyzing pricing scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))
