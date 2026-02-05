"""Predictions API - ML-powered business intelligence.

Features:
- Lead scoring
- Churn prediction
- Revenue forecasting
- Deal health analysis
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.prediction import LeadScore, ChurnPrediction, RevenueForecast, DealHealth
from app.models.customer import Customer
from app.services.ml_scoring import (
    calculate_lead_scores_batch,
    calculate_customer_lead_score,
    get_lead_scoring_summary,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# Lead Scoring Endpoints


@router.get("/lead-scores")
async def list_lead_scores(
    db: DbSession,
    current_user: CurrentUser,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    label: Optional[str] = None,  # hot, warm, cold
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List lead scores with filtering."""
    query = select(LeadScore)

    if min_score is not None:
        query = query.where(LeadScore.score >= min_score)
    if max_score is not None:
        query = query.where(LeadScore.score <= max_score)
    if label:
        query = query.where(LeadScore.score_label == label)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate and sort by score desc
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(LeadScore.score.desc())

    result = await db.execute(query)
    scores = result.scalars().all()

    return {
        "items": [
            {
                "customer_id": str(s.customer_id),
                "score": s.score,
                "score_label": s.score_label,
                "confidence": s.confidence,
                "factors": s.factors,
                "scored_at": s.scored_at.isoformat() if s.scored_at else None,
            }
            for s in scores
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/lead-scores/{customer_id}")
async def get_lead_score(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    calculate_if_missing: bool = Query(True, description="Calculate score on-demand if not exists"),
):
    """Get lead score for a customer. Optionally calculates on-demand if missing."""
    result = await db.execute(select(LeadScore).where(LeadScore.customer_id == customer_id))
    score = result.scalar_one_or_none()

    if not score:
        if calculate_if_missing:
            # Calculate on-demand
            customer_result = await db.execute(select(Customer).where(Customer.id == customer_id))
            customer = customer_result.scalar_one_or_none()

            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Customer not found",
                )

            # Calculate score
            score_data = await calculate_customer_lead_score(db, customer)

            return {
                "customer_id": customer_id,
                "score": score_data["score"],
                "score_label": score_data["score_label"],
                "confidence": score_data["confidence"],
                "factors": score_data["factors"],
                "scored_at": datetime.utcnow().isoformat(),
                "calculated_on_demand": True,
            }
        else:
            return {
                "customer_id": customer_id,
                "score": None,
                "score_label": "unknown",
                "message": "Lead score not yet calculated",
            }

    return {
        "customer_id": customer_id,
        "score": score.score,
        "score_label": score.score_label,
        "confidence": score.confidence,
        "factors": score.factors,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
    }


class LeadScoreRequest(BaseModel):
    customer_ids: Optional[List[str]] = Field(
        None, description="List of customer IDs to score. If empty, scores all active customers."
    )


@router.post("/lead-scores/calculate")
async def calculate_lead_scores(
    request: Optional[LeadScoreRequest] = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """
    Calculate/recalculate lead scores using rule-based scoring.

    If no customer_ids provided, calculates for all active customers.

    Scoring factors:
    - Recent activity (< 7 days: +20, < 30 days: +10)
    - Open quotes: +15+
    - Previous work orders: +10+
    - Property size (tank size): +5-15
    - Customer type (commercial premium): +10-15
    - Lead source quality: varies
    - Engagement signals: +5-10

    Labels: hot (75+), warm (50-74), cold (<50)
    """
    customer_ids = None
    if request and request.customer_ids:
        customer_ids = request.customer_ids

    try:
        results = await calculate_lead_scores_batch(db, customer_ids)

        return {
            "status": "completed",
            "message": f"Successfully scored {results['calculated']} customers",
            "results": {
                "calculated": results["calculated"],
                "hot_leads": results["hot_leads"],
                "warm_leads": results["warm_leads"],
                "cold_leads": results["cold_leads"],
                "errors": results["errors"],
            },
        }
    except Exception as e:
        logger.error(f"Lead scoring failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lead scoring failed: {str(e)}",
        )


@router.get("/lead-scores/summary")
async def get_lead_scores_summary(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get summary statistics for lead scoring."""
    try:
        summary = await get_lead_scoring_summary(db)
        return summary
    except Exception as e:
        logger.error(f"Failed to get scoring summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve scoring summary",
        )


# Churn Prediction Endpoints


@router.get("/churn")
async def list_churn_predictions(
    db: DbSession,
    current_user: CurrentUser,
    risk_level: Optional[str] = None,  # low, medium, high, critical
    min_probability: Optional[float] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List churn predictions sorted by risk."""
    query = select(ChurnPrediction)

    if risk_level:
        query = query.where(ChurnPrediction.risk_level == risk_level)
    if min_probability is not None:
        query = query.where(ChurnPrediction.churn_probability >= min_probability)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate and sort by probability desc
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(ChurnPrediction.churn_probability.desc())

    result = await db.execute(query)
    predictions = result.scalars().all()

    return {
        "items": [
            {
                "customer_id": str(p.customer_id),
                "churn_probability": p.churn_probability,
                "risk_level": p.risk_level,
                "days_to_churn": p.days_to_churn,
                "risk_factors": p.risk_factors,
                "recommended_actions": p.recommended_actions,
                "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
            }
            for p in predictions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/churn/{customer_id}")
async def get_churn_prediction(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get churn prediction for a customer."""
    result = await db.execute(select(ChurnPrediction).where(ChurnPrediction.customer_id == customer_id))
    prediction = result.scalar_one_or_none()

    if not prediction:
        return {
            "customer_id": customer_id,
            "churn_probability": None,
            "risk_level": "unknown",
            "message": "Churn prediction not yet calculated",
        }

    return {
        "customer_id": customer_id,
        "churn_probability": prediction.churn_probability,
        "risk_level": prediction.risk_level,
        "days_to_churn": prediction.days_to_churn,
        "risk_factors": prediction.risk_factors,
        "recommended_actions": prediction.recommended_actions,
        "predicted_at": prediction.predicted_at.isoformat() if prediction.predicted_at else None,
    }


@router.get("/churn/at-risk")
async def get_at_risk_customers(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    """Get customers with highest churn risk."""
    result = await db.execute(
        select(ChurnPrediction)
        .where(ChurnPrediction.risk_level.in_(["high", "critical"]))
        .order_by(ChurnPrediction.churn_probability.desc())
        .limit(limit)
    )
    predictions = result.scalars().all()

    return {
        "at_risk_customers": [
            {
                "customer_id": str(p.customer_id),
                "churn_probability": p.churn_probability,
                "risk_level": p.risk_level,
                "recommended_actions": p.recommended_actions,
            }
            for p in predictions
        ],
    }


# Revenue Forecast Endpoints


@router.get("/revenue-forecast")
async def get_revenue_forecast(
    db: DbSession,
    current_user: CurrentUser,
    period_type: str = Query("monthly"),  # daily, weekly, monthly
    periods_ahead: int = Query(3, ge=1, le=12),
):
    """Get revenue forecasts."""
    result = await db.execute(
        select(RevenueForecast)
        .where(RevenueForecast.period_type == period_type)
        .where(RevenueForecast.period_start >= datetime.utcnow())
        .order_by(RevenueForecast.period_start)
        .limit(periods_ahead)
    )
    forecasts = result.scalars().all()

    return {
        "period_type": period_type,
        "forecasts": [
            {
                "period_start": f.period_start.isoformat() if f.period_start else None,
                "period_end": f.period_end.isoformat() if f.period_end else None,
                "predicted_revenue": f.predicted_revenue,
                "predicted_jobs": f.predicted_jobs,
                "confidence_lower": f.confidence_lower,
                "confidence_upper": f.confidence_upper,
                "breakdown": f.breakdown,
            }
            for f in forecasts
        ],
    }


@router.get("/revenue-forecast/accuracy")
async def get_forecast_accuracy(
    db: DbSession,
    current_user: CurrentUser,
    period_type: str = Query("monthly"),
    lookback_periods: int = Query(6, ge=1, le=24),
):
    """Get historical forecast accuracy."""
    cutoff = datetime.utcnow()

    result = await db.execute(
        select(RevenueForecast)
        .where(RevenueForecast.period_type == period_type)
        .where(RevenueForecast.period_end < cutoff)
        .where(RevenueForecast.actual_revenue.isnot(None))
        .order_by(RevenueForecast.period_start.desc())
        .limit(lookback_periods)
    )
    forecasts = result.scalars().all()

    # Calculate average accuracy
    accuracies = [f.accuracy for f in forecasts if f.accuracy is not None]
    avg_accuracy = sum(accuracies) / len(accuracies) if accuracies else None

    return {
        "period_type": period_type,
        "average_accuracy": avg_accuracy,
        "periods": [
            {
                "period_start": f.period_start.isoformat() if f.period_start else None,
                "predicted_revenue": f.predicted_revenue,
                "actual_revenue": f.actual_revenue,
                "accuracy": f.accuracy,
            }
            for f in forecasts
        ],
    }


# Deal Health Endpoints


@router.get("/deal-health")
async def list_deal_health(
    db: DbSession,
    current_user: CurrentUser,
    health_status: Optional[str] = None,  # healthy, at_risk, stale, dead
    entity_type: Optional[str] = None,  # quote, prospect
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List deal health assessments."""
    query = select(DealHealth)

    if health_status:
        query = query.where(DealHealth.health_status == health_status)
    if entity_type:
        query = query.where(DealHealth.entity_type == entity_type)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(DealHealth.health_score)

    result = await db.execute(query)
    deals = result.scalars().all()

    return {
        "items": [
            {
                "entity_type": d.entity_type,
                "entity_id": d.entity_id,
                "customer_id": str(d.customer_id),
                "health_score": d.health_score,
                "health_status": d.health_status,
                "days_in_stage": d.days_in_stage,
                "days_since_activity": d.days_since_activity,
                "warning_signs": d.warning_signs,
                "recommended_actions": d.recommended_actions,
                "analyzed_at": d.analyzed_at.isoformat() if d.analyzed_at else None,
            }
            for d in deals
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/deal-health/rotting")
async def get_rotting_deals(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    """Get deals that need immediate attention (rotting)."""
    result = await db.execute(
        select(DealHealth)
        .where(DealHealth.health_status.in_(["at_risk", "stale"]))
        .order_by(DealHealth.health_score)
        .limit(limit)
    )
    deals = result.scalars().all()

    return {
        "rotting_deals": [
            {
                "entity_type": d.entity_type,
                "entity_id": d.entity_id,
                "customer_id": str(d.customer_id),
                "health_score": d.health_score,
                "health_status": d.health_status,
                "days_since_activity": d.days_since_activity,
                "warning_signs": d.warning_signs,
                "recommended_actions": d.recommended_actions,
            }
            for d in deals
        ],
    }


# Dashboard Summary


@router.get("/summary")
async def get_predictions_summary(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get summary of all predictions for dashboard."""
    # Hot leads count
    hot_leads_result = await db.execute(
        select(func.count()).select_from(LeadScore).where(LeadScore.score_label == "hot")
    )
    hot_leads = hot_leads_result.scalar() or 0

    # At-risk customers
    at_risk_result = await db.execute(
        select(func.count()).select_from(ChurnPrediction).where(ChurnPrediction.risk_level.in_(["high", "critical"]))
    )
    at_risk_customers = at_risk_result.scalar() or 0

    # Rotting deals
    rotting_result = await db.execute(
        select(func.count()).select_from(DealHealth).where(DealHealth.health_status.in_(["at_risk", "stale"]))
    )
    rotting_deals = rotting_result.scalar() or 0

    # Next month forecast
    next_month = datetime.utcnow().replace(day=1) + timedelta(days=32)
    next_month = next_month.replace(day=1)

    forecast_result = await db.execute(
        select(RevenueForecast)
        .where(
            RevenueForecast.period_type == "monthly",
            RevenueForecast.period_start >= next_month,
        )
        .limit(1)
    )
    forecast = forecast_result.scalar_one_or_none()

    return {
        "hot_leads": hot_leads,
        "at_risk_customers": at_risk_customers,
        "rotting_deals": rotting_deals,
        "next_month_forecast": {
            "revenue": forecast.predicted_revenue if forecast else None,
            "jobs": forecast.predicted_jobs if forecast else None,
        }
        if forecast
        else None,
    }
