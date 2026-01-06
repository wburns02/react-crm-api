"""
Customer Success Dashboard API Endpoints
"""

from fastapi import APIRouter, Query
from sqlalchemy import select, func, and_
from typing import Optional
from datetime import datetime, timedelta, date

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.models.customer_success import (
    HealthScore, Segment, CustomerSegment,
    Journey, JourneyEnrollment,
    Playbook, PlaybookExecution,
    CSTask, Touchpoint,
)
from app.schemas.customer_success.health_score import HealthStatus
from app.schemas.customer_success.journey import EnrollmentStatus
from app.schemas.customer_success.playbook import PlaybookExecStatus
from app.schemas.customer_success.task import TaskStatus, TaskPriority

router = APIRouter()


@router.get("/overview")
async def get_cs_overview(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get Customer Success platform overview metrics."""
    # Health Score Distribution
    health_counts = {}
    for status in HealthStatus:
        count_result = await db.execute(
            select(func.count()).where(HealthScore.health_status == status.value)
        )
        health_counts[status.value] = count_result.scalar()

    # Average health score
    avg_health_result = await db.execute(select(func.avg(HealthScore.overall_score)))
    avg_health = avg_health_result.scalar() or 0

    # Active enrollments
    active_enrollments_result = await db.execute(
        select(func.count()).where(JourneyEnrollment.status == EnrollmentStatus.ACTIVE.value)
    )
    active_enrollments = active_enrollments_result.scalar()

    # Active playbook executions
    active_playbooks_result = await db.execute(
        select(func.count()).where(PlaybookExecution.status == PlaybookExecStatus.ACTIVE.value)
    )
    active_playbooks = active_playbooks_result.scalar()

    # Open tasks
    open_tasks_result = await db.execute(
        select(func.count()).where(
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value])
        )
    )
    open_tasks = open_tasks_result.scalar()

    # Overdue tasks
    today = date.today()
    overdue_tasks_result = await db.execute(
        select(func.count()).where(
            CSTask.due_date < today,
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
        )
    )
    overdue_tasks = overdue_tasks_result.scalar()

    # Recent touchpoints (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_touchpoints_result = await db.execute(
        select(func.count()).where(Touchpoint.occurred_at >= week_ago)
    )
    recent_touchpoints = recent_touchpoints_result.scalar()

    # Total segments
    segments_result = await db.execute(
        select(func.count()).where(Segment.is_active == True)
    )
    active_segments = segments_result.scalar()

    return {
        "health_distribution": health_counts,
        "avg_health_score": round(avg_health, 1),
        "total_at_risk": health_counts.get(HealthStatus.AT_RISK.value, 0) + health_counts.get(HealthStatus.CRITICAL.value, 0),
        "active_journey_enrollments": active_enrollments,
        "active_playbook_executions": active_playbooks,
        "open_tasks": open_tasks,
        "overdue_tasks": overdue_tasks,
        "recent_touchpoints_7d": recent_touchpoints,
        "active_segments": active_segments,
    }


@router.get("/at-risk-customers")
async def get_at_risk_customers(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    """Get customers with at-risk or critical health scores."""
    result = await db.execute(
        select(HealthScore)
        .where(HealthScore.health_status.in_([HealthStatus.AT_RISK.value, HealthStatus.CRITICAL.value]))
        .order_by(HealthScore.overall_score.asc())
        .limit(limit)
    )
    scores = result.scalars().all()

    return {
        "items": [
            {
                "customer_id": s.customer_id,
                "overall_score": s.overall_score,
                "health_status": s.health_status,
                "churn_probability": s.churn_probability,
                "score_trend": s.score_trend,
            }
            for s in scores
        ],
        "total": len(scores),
    }


@router.get("/my-tasks")
async def get_my_tasks(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50),
):
    """Get current user's tasks summary."""
    today = date.today()

    # Get tasks assigned to current user
    result = await db.execute(
        select(CSTask)
        .where(
            CSTask.assigned_to_user_id == current_user.id,
            CSTask.status.in_([TaskStatus.PENDING.value, TaskStatus.IN_PROGRESS.value]),
        )
        .order_by(
            CSTask.due_date.asc().nullslast(),
        )
        .limit(limit)
    )
    tasks = result.scalars().all()

    # Categorize tasks
    overdue = [t for t in tasks if t.due_date and t.due_date < today]
    due_today = [t for t in tasks if t.due_date and t.due_date == today]
    upcoming = [t for t in tasks if not t.due_date or t.due_date > today]

    return {
        "total_open": len(tasks),
        "overdue": len(overdue),
        "due_today": len(due_today),
        "upcoming": len(upcoming),
        "tasks": tasks,
    }


@router.get("/journey-performance")
async def get_journey_performance(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
):
    """Get journey performance metrics."""
    period_start = datetime.utcnow() - timedelta(days=days)

    # Get active journeys with their stats
    result = await db.execute(
        select(Journey)
        .where(Journey.status == "active")
        .order_by(Journey.total_enrolled.desc().nullslast())
        .limit(10)
    )
    journeys = result.scalars().all()

    journey_stats = []
    for journey in journeys:
        # Completed enrollments in period
        completed_result = await db.execute(
            select(func.count()).where(
                JourneyEnrollment.journey_id == journey.id,
                JourneyEnrollment.status == EnrollmentStatus.COMPLETED.value,
                JourneyEnrollment.completed_at >= period_start,
            )
        )
        completed = completed_result.scalar()

        # Goal achieved
        goal_achieved_result = await db.execute(
            select(func.count()).where(
                JourneyEnrollment.journey_id == journey.id,
                JourneyEnrollment.goal_achieved == True,
                JourneyEnrollment.completed_at >= period_start,
            )
        )
        goal_achieved = goal_achieved_result.scalar()

        journey_stats.append({
            "id": journey.id,
            "name": journey.name,
            "type": journey.journey_type,
            "active_enrolled": journey.active_enrolled,
            "total_enrolled": journey.total_enrolled,
            "completed_in_period": completed,
            "goals_achieved_in_period": goal_achieved,
            "conversion_rate": journey.conversion_rate,
        })

    return {
        "period_days": days,
        "journeys": journey_stats,
    }


@router.get("/playbook-performance")
async def get_playbook_performance(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
):
    """Get playbook performance metrics."""
    period_start = datetime.utcnow() - timedelta(days=days)

    # Get active playbooks with their stats
    result = await db.execute(
        select(Playbook)
        .where(Playbook.is_active == True)
        .order_by(Playbook.times_triggered.desc().nullslast())
        .limit(10)
    )
    playbooks = result.scalars().all()

    playbook_stats = []
    for playbook in playbooks:
        # Triggered in period
        triggered_result = await db.execute(
            select(func.count()).where(
                PlaybookExecution.playbook_id == playbook.id,
                PlaybookExecution.started_at >= period_start,
            )
        )
        triggered = triggered_result.scalar()

        # Completed in period
        completed_result = await db.execute(
            select(func.count()).where(
                PlaybookExecution.playbook_id == playbook.id,
                PlaybookExecution.status == PlaybookExecStatus.COMPLETED.value,
                PlaybookExecution.completed_at >= period_start,
            )
        )
        completed = completed_result.scalar()

        playbook_stats.append({
            "id": playbook.id,
            "name": playbook.name,
            "category": playbook.category,
            "times_triggered_total": playbook.times_triggered,
            "triggered_in_period": triggered,
            "completed_in_period": completed,
            "success_rate": playbook.success_rate,
            "avg_completion_days": playbook.avg_completion_days,
        })

    return {
        "period_days": days,
        "playbooks": playbook_stats,
    }


@router.get("/segment-insights")
async def get_segment_insights(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get segment insights and distribution."""
    result = await db.execute(
        select(Segment)
        .where(Segment.is_active == True)
        .order_by(Segment.customer_count.desc().nullslast())
        .limit(20)
    )
    segments = result.scalars().all()

    return {
        "segments": [
            {
                "id": s.id,
                "name": s.name,
                "type": s.segment_type,
                "customer_count": s.customer_count,
                "total_arr": s.total_arr,
                "avg_health_score": s.avg_health_score,
                "churn_risk_count": s.churn_risk_count,
                "color": s.color,
            }
            for s in segments
        ],
        "total": len(segments),
    }


@router.get("/activity-feed")
async def get_activity_feed(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(20, ge=1, le=50),
):
    """Get recent customer success activity feed."""
    # Get recent touchpoints
    touchpoints_result = await db.execute(
        select(Touchpoint)
        .where(Touchpoint.is_internal == False)
        .order_by(Touchpoint.occurred_at.desc())
        .limit(limit)
    )
    touchpoints = touchpoints_result.scalars().all()

    activities = []
    for t in touchpoints:
        activities.append({
            "type": "touchpoint",
            "id": t.id,
            "customer_id": t.customer_id,
            "touchpoint_type": t.touchpoint_type,
            "subject": t.subject,
            "sentiment_label": t.sentiment_label,
            "occurred_at": t.occurred_at.isoformat() if t.occurred_at else None,
            "user_id": t.user_id,
        })

    return {"items": activities, "total": len(activities)}


@router.get("/health-trends")
async def get_health_trends(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
):
    """Get health score trends over time."""
    # This would typically query health score history/events
    # For now, return current distribution
    healthy_result = await db.execute(
        select(func.count()).where(HealthScore.health_status == HealthStatus.HEALTHY.value)
    )
    at_risk_result = await db.execute(
        select(func.count()).where(HealthScore.health_status == HealthStatus.AT_RISK.value)
    )
    critical_result = await db.execute(
        select(func.count()).where(HealthScore.health_status == HealthStatus.CRITICAL.value)
    )

    return {
        "period_days": days,
        "current_distribution": {
            "healthy": healthy_result.scalar(),
            "at_risk": at_risk_result.scalar(),
            "critical": critical_result.scalar(),
        },
        "trend_data": [],  # Would be populated from historical data
    }


@router.get("/csm-leaderboard")
async def get_csm_leaderboard(
    db: DbSession,
    current_user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
):
    """Get CSM performance leaderboard."""
    period_start = datetime.utcnow() - timedelta(days=days)

    # Tasks completed by user
    tasks_result = await db.execute(
        select(
            CSTask.assigned_to_user_id,
            func.count(CSTask.id).label("completed_tasks"),
        )
        .where(
            CSTask.status == TaskStatus.COMPLETED.value,
            CSTask.completed_at >= period_start,
        )
        .group_by(CSTask.assigned_to_user_id)
        .order_by(func.count(CSTask.id).desc())
        .limit(10)
    )
    tasks_data = tasks_result.all()

    # Touchpoints by user
    touchpoints_result = await db.execute(
        select(
            Touchpoint.user_id,
            func.count(Touchpoint.id).label("touchpoints"),
        )
        .where(Touchpoint.occurred_at >= period_start)
        .group_by(Touchpoint.user_id)
        .order_by(func.count(Touchpoint.id).desc())
        .limit(10)
    )
    touchpoints_data = touchpoints_result.all()

    return {
        "period_days": days,
        "by_tasks_completed": [
            {"user_id": t[0], "completed_tasks": t[1]}
            for t in tasks_data if t[0]
        ],
        "by_touchpoints": [
            {"user_id": t[0], "touchpoints": t[1]}
            for t in touchpoints_data if t[0]
        ],
    }
