"""
Health Score API Endpoints for Enterprise Customer Success Platform
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime, timedelta

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import HealthScore, HealthScoreEvent
from app.schemas.customer_success.health_score import (
    HealthScoreCreate,
    HealthScoreUpdate,
    HealthScoreResponse,
    HealthScoreListResponse,
    HealthScoreEventCreate,
    HealthScoreEventResponse,
    HealthScoreEventListResponse,
    HealthScoreBulkCalculateRequest,
    HealthScoreTrendResponse,
    HealthStatus,
    ScoreTrend,
    HealthEventType,
)

router = APIRouter()


@router.get("/", response_model=HealthScoreListResponse)
async def list_health_scores(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    health_status: Optional[str] = None,
    min_score: Optional[int] = Query(None, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    trend: Optional[str] = None,
):
    """List health scores with filtering."""
    query = select(HealthScore)

    if health_status:
        query = query.where(HealthScore.health_status == health_status)
    if min_score is not None:
        query = query.where(HealthScore.overall_score >= min_score)
    if max_score is not None:
        query = query.where(HealthScore.overall_score <= max_score)
    if trend:
        query = query.where(HealthScore.score_trend == trend)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(HealthScore.overall_score.asc())

    result = await db.execute(query)
    scores = result.scalars().all()

    return HealthScoreListResponse(
        items=scores,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customer/{customer_id}", response_model=HealthScoreResponse)
async def get_customer_health_score(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get health score for a specific customer."""
    result = await db.execute(select(HealthScore).where(HealthScore.customer_id == customer_id))
    score = result.scalar_one_or_none()

    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health score not found for this customer",
        )

    return score


@router.post("/", response_model=HealthScoreResponse, status_code=status.HTTP_201_CREATED)
async def create_health_score(
    data: HealthScoreCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a health score for a customer."""
    # Check customer exists
    customer_result = await db.execute(select(Customer).where(Customer.id == data.customer_id))
    if not customer_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Check if health score already exists
    existing = await db.execute(select(HealthScore).where(HealthScore.customer_id == data.customer_id))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Health score already exists for this customer",
        )

    # Determine health status based on score
    health_status = _calculate_health_status(data.overall_score)

    score = HealthScore(
        **data.model_dump(),
        health_status=health_status,
        calculated_at=datetime.utcnow(),
    )
    db.add(score)
    await db.commit()
    await db.refresh(score)

    # Create initial event
    event = HealthScoreEvent(
        health_score_id=score.id,
        event_type=HealthEventType.SCORE_CALCULATED.value,
        new_score=score.overall_score,
        reason="Initial health score created",
        triggered_by_user_id=current_user.id,
    )
    db.add(event)
    await db.commit()

    return score


@router.patch("/customer/{customer_id}", response_model=HealthScoreResponse)
async def update_health_score(
    customer_id: str,
    data: HealthScoreUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a customer's health score."""
    result = await db.execute(select(HealthScore).where(HealthScore.customer_id == customer_id))
    score = result.scalar_one_or_none()

    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health score not found for this customer",
        )

    old_score = score.overall_score
    update_data = data.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(score, field, value)

    # Update health status if score changed
    if "overall_score" in update_data:
        score.health_status = _calculate_health_status(score.overall_score)
        score.previous_score = old_score
        score.previous_score_date = score.calculated_at
        score.calculated_at = datetime.utcnow()

        # Determine trend
        if score.overall_score > old_score:
            score.score_trend = ScoreTrend.IMPROVING.value
        elif score.overall_score < old_score:
            score.score_trend = ScoreTrend.DECLINING.value
        else:
            score.score_trend = ScoreTrend.STABLE.value

        score.trend_percentage = ((score.overall_score - old_score) / old_score * 100) if old_score > 0 else 0

        # Create event
        event_type = (
            HealthEventType.MANUAL_OVERRIDE.value if data.is_manually_set else HealthEventType.SCORE_CALCULATED.value
        )
        event = HealthScoreEvent(
            health_score_id=score.id,
            event_type=event_type,
            old_score=old_score,
            new_score=score.overall_score,
            change_amount=score.overall_score - old_score,
            reason=data.manual_override_reason or "Score updated",
            triggered_by_user_id=current_user.id,
        )
        db.add(event)

    await db.commit()
    await db.refresh(score)
    return score


@router.get("/customer/{customer_id}/events", response_model=HealthScoreEventListResponse)
async def list_health_score_events(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List health score events for a customer."""
    # Get health score
    score_result = await db.execute(select(HealthScore).where(HealthScore.customer_id == customer_id))
    score = score_result.scalar_one_or_none()

    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health score not found for this customer",
        )

    query = select(HealthScoreEvent).where(HealthScoreEvent.health_score_id == score.id)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(HealthScoreEvent.created_at.desc())

    result = await db.execute(query)
    events = result.scalars().all()

    return HealthScoreEventListResponse(
        items=events,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/customer/{customer_id}/trend", response_model=HealthScoreTrendResponse)
async def get_health_score_trend(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=7, le=365),
):
    """Get health score trend data for charts."""
    # Get health score
    score_result = await db.execute(select(HealthScore).where(HealthScore.customer_id == customer_id))
    score = score_result.scalar_one_or_none()

    if not score:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health score not found for this customer",
        )

    period_end = datetime.utcnow()
    period_start = period_end - timedelta(days=days)

    # Get events within period
    events_result = await db.execute(
        select(HealthScoreEvent)
        .where(
            and_(
                HealthScoreEvent.health_score_id == score.id,
                HealthScoreEvent.created_at >= period_start,
                HealthScoreEvent.new_score.isnot(None),
            )
        )
        .order_by(HealthScoreEvent.created_at.asc())
    )
    events = events_result.scalars().all()

    data_points = []
    scores = []
    for event in events:
        if event.new_score is not None:
            data_points.append(
                {
                    "date": event.created_at.isoformat() if event.created_at else None,
                    "score": event.new_score,
                    "status": _calculate_health_status(event.new_score),
                }
            )
            scores.append(event.new_score)

    # Calculate statistics
    avg_score = sum(scores) / len(scores) if scores else score.overall_score
    min_score = min(scores) if scores else score.overall_score
    max_score = max(scores) if scores else score.overall_score

    # Determine trend
    if len(scores) >= 2:
        first_half_avg = sum(scores[: len(scores) // 2]) / (len(scores) // 2)
        second_half_avg = sum(scores[len(scores) // 2 :]) / (len(scores) - len(scores) // 2)
        if second_half_avg > first_half_avg + 5:
            trend = ScoreTrend.IMPROVING
        elif second_half_avg < first_half_avg - 5:
            trend = ScoreTrend.DECLINING
        else:
            trend = ScoreTrend.STABLE
        change_percentage = ((second_half_avg - first_half_avg) / first_half_avg * 100) if first_half_avg > 0 else 0
    else:
        trend = ScoreTrend.STABLE
        change_percentage = 0

    return HealthScoreTrendResponse(
        customer_id=customer_id,
        data_points=data_points,
        period_start=period_start,
        period_end=period_end,
        average_score=avg_score,
        min_score=min_score,
        max_score=max_score,
        trend=trend,
        change_percentage=change_percentage,
    )


@router.post("/calculate/bulk")
async def bulk_calculate_health_scores(
    request: HealthScoreBulkCalculateRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Trigger bulk health score calculation."""
    # This would normally trigger a background job
    # For now, return acknowledgment
    return {
        "status": "accepted",
        "message": "Bulk health score calculation queued",
        "customer_ids": request.customer_ids,
        "segment_id": request.segment_id,
        "force_recalculate": request.force_recalculate,
    }


@router.get("/summary")
async def get_health_summary(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get summary statistics for health scores."""
    # Count by status
    status_counts = {}
    for status_val in HealthStatus:
        count_result = await db.execute(select(func.count()).where(HealthScore.health_status == status_val.value))
        status_counts[status_val.value] = count_result.scalar()

    # Average score
    avg_result = await db.execute(select(func.avg(HealthScore.overall_score)))
    avg_score = avg_result.scalar() or 0

    # Scores below threshold (at risk)
    at_risk_result = await db.execute(select(func.count()).where(HealthScore.overall_score < 50))
    at_risk_count = at_risk_result.scalar()

    # Declining trend count
    declining_result = await db.execute(
        select(func.count()).where(HealthScore.score_trend == ScoreTrend.DECLINING.value)
    )
    declining_count = declining_result.scalar()

    return {
        "total_customers_scored": sum(status_counts.values()),
        "status_breakdown": status_counts,
        "average_score": round(avg_score, 1),
        "at_risk_count": at_risk_count,
        "declining_trend_count": declining_count,
    }


def _calculate_health_status(score: int) -> str:
    """Calculate health status based on score."""
    if score >= 70:
        return HealthStatus.HEALTHY.value
    elif score >= 40:
        return HealthStatus.AT_RISK.value
    elif score >= 20:
        return HealthStatus.CRITICAL.value
    else:
        return HealthStatus.CHURNED.value
