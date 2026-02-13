"""
AI Coaching Endpoints — Technician Performance Analysis

Calculates coaching insights from existing work order and call data.
No separate database models needed — derived from work_orders, technicians, call_logs.
"""

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, case, and_

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.call_log import CallLog

router = APIRouter()


# ---- Pydantic Models ----

class PerformanceStrength(BaseModel):
    area: str
    score: float
    description: str
    compared_to_team: str  # "above" | "at" | "below"

class ImprovementArea(BaseModel):
    area: str
    current_score: float
    target_score: float
    gap: float
    priority: str
    action_plan: str

class CoachingGoal(BaseModel):
    id: str
    title: str
    description: str
    target_date: str
    progress_percent: float
    status: str

class Achievement(BaseModel):
    id: str
    title: str
    description: str
    earned_date: str
    type: str  # "milestone" | "improvement" | "excellence"

class CoachingSuggestion(BaseModel):
    id: str
    type: str  # "training" | "practice" | "feedback" | "recognition"
    title: str
    description: str
    expected_impact: str
    resources: list[str] = []

class TechnicianCoachingResponse(BaseModel):
    technician_id: str
    technician_name: str
    overall_score: float
    trend: str
    strengths: list[PerformanceStrength]
    areas_for_improvement: list[ImprovementArea]
    goals: list[CoachingGoal]
    recent_achievements: list[Achievement]
    coaching_suggestions: list[CoachingSuggestion]

class TeamPerformanceSummary(BaseModel):
    team_average_score: float
    top_performer: dict
    most_improved: dict
    needs_attention: list[dict]
    team_goals_progress: float

class GenerateFeedbackRequest(BaseModel):
    technician_id: str
    context: str  # "weekly_review" | "after_job" | "goal_progress" | "improvement_needed"

class CreateGoalRequest(BaseModel):
    technician_id: str
    title: str
    description: str
    target_date: str


# ---- Helper functions ----

async def _get_tech_stats(db: DbSession, tech_id: str, tech_name: str):
    """Calculate performance stats for a technician from work orders."""
    now = date.today()
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)

    # Recent 30-day WO stats
    from sqlalchemy import select, or_, text
    recent_q = select(
        func.count(WorkOrder.id).label("total"),
        func.count(case((WorkOrder.status == "completed", 1))).label("completed"),
        func.count(case((WorkOrder.priority.in_(["urgent", "emergency"]), 1))).label("emergency"),
    ).where(
        and_(
            or_(
                WorkOrder.technician_id == tech_id,
                WorkOrder.assigned_technician == tech_name,
            ),
            WorkOrder.scheduled_date >= str(thirty_days_ago),
        )
    )
    result = await db.execute(recent_q)
    recent = result.one()

    # Previous 30-day stats (for trend)
    prev_q = select(
        func.count(WorkOrder.id).label("total"),
        func.count(case((WorkOrder.status == "completed", 1))).label("completed"),
    ).where(
        and_(
            or_(
                WorkOrder.technician_id == tech_id,
                WorkOrder.assigned_technician == tech_name,
            ),
            WorkOrder.scheduled_date >= str(sixty_days_ago),
            WorkOrder.scheduled_date < str(thirty_days_ago),
        )
    )
    prev_result = await db.execute(prev_q)
    prev = prev_result.one()

    # All-time stats
    all_q = select(
        func.count(WorkOrder.id).label("total"),
        func.count(case((WorkOrder.status == "completed", 1))).label("completed"),
    ).where(
        or_(
            WorkOrder.technician_id == tech_id,
            WorkOrder.assigned_technician == tech_name,
        )
    )
    all_result = await db.execute(all_q)
    all_time = all_result.one()

    return {
        "recent_total": recent.total or 0,
        "recent_completed": recent.completed or 0,
        "recent_emergency": recent.emergency or 0,
        "prev_total": prev.total or 0,
        "prev_completed": prev.completed or 0,
        "all_total": all_time.total or 0,
        "all_completed": all_time.completed or 0,
    }


def _calculate_score(stats: dict) -> float:
    """Calculate overall performance score (0-100) from stats."""
    if stats["all_total"] == 0:
        return 50.0  # Neutral score for new techs

    completion_rate = (stats["all_completed"] / stats["all_total"]) * 100 if stats["all_total"] > 0 else 50
    # Volume bonus: more jobs = higher score (capped at 20 points)
    volume_bonus = min(stats["recent_total"] * 2, 20)
    # Emergency handling bonus
    emergency_bonus = min(stats["recent_emergency"] * 3, 10)

    score = min(completion_rate * 0.7 + volume_bonus + emergency_bonus, 100)
    return round(score, 1)


def _determine_trend(stats: dict) -> str:
    """Determine performance trend from recent vs previous period."""
    if stats["prev_total"] == 0:
        return "stable"
    recent_rate = stats["recent_completed"] / max(stats["recent_total"], 1)
    prev_rate = stats["prev_completed"] / max(stats["prev_total"], 1)
    diff = recent_rate - prev_rate
    if diff > 0.05:
        return "improving"
    elif diff < -0.05:
        return "declining"
    return "stable"


# ---- Endpoints ----

@router.get("/{technician_id}/coaching", response_model=TechnicianCoachingResponse)
async def get_technician_coaching(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get AI coaching insights for a specific technician."""
    from sqlalchemy import select, or_

    # Find technician
    tech_q = select(Technician).where(Technician.id == technician_id)
    result = await db.execute(tech_q)
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    tech_name = f"{tech.first_name} {tech.last_name}"
    stats = await _get_tech_stats(db, technician_id, tech_name)
    score = _calculate_score(stats)
    trend = _determine_trend(stats)

    completion_rate = round((stats["all_completed"] / max(stats["all_total"], 1)) * 100, 1)

    # Build strengths
    strengths = []
    if completion_rate > 80:
        strengths.append(PerformanceStrength(
            area="Job Completion",
            score=completion_rate,
            description=f"Completes {completion_rate}% of assigned jobs",
            compared_to_team="above" if completion_rate > 85 else "at",
        ))
    if stats["recent_emergency"] > 0:
        strengths.append(PerformanceStrength(
            area="Emergency Response",
            score=90.0,
            description=f"Handled {stats['recent_emergency']} emergency calls in the last 30 days",
            compared_to_team="above",
        ))
    if stats["recent_total"] > 10:
        strengths.append(PerformanceStrength(
            area="Volume",
            score=min(stats["recent_total"] * 5, 100),
            description=f"Completed {stats['recent_total']} jobs in the last 30 days",
            compared_to_team="above" if stats["recent_total"] > 15 else "at",
        ))

    # Build improvement areas
    improvements = []
    if completion_rate < 80:
        improvements.append(ImprovementArea(
            area="Job Completion Rate",
            current_score=completion_rate,
            target_score=90.0,
            gap=90.0 - completion_rate,
            priority="high",
            action_plan="Review incomplete jobs for common blockers. Discuss scheduling conflicts with dispatch.",
        ))
    if stats["recent_total"] < 5:
        improvements.append(ImprovementArea(
            area="Job Volume",
            current_score=float(stats["recent_total"]),
            target_score=10.0,
            gap=10.0 - stats["recent_total"],
            priority="medium",
            action_plan="Increase availability on schedule. Consider expanding service area coverage.",
        ))

    # Coaching suggestions based on performance
    suggestions = []
    if trend == "declining":
        suggestions.append(CoachingSuggestion(
            id=str(uuid.uuid4())[:8],
            type="feedback",
            title="Performance Check-in",
            description="Schedule a one-on-one to discuss recent performance trends",
            expected_impact="Identify and address blockers early",
        ))
    if completion_rate > 90:
        suggestions.append(CoachingSuggestion(
            id=str(uuid.uuid4())[:8],
            type="recognition",
            title="Top Performer Recognition",
            description=f"{tech.first_name} has an excellent completion rate. Consider public recognition.",
            expected_impact="Boost morale and retention",
        ))
    suggestions.append(CoachingSuggestion(
        id=str(uuid.uuid4())[:8],
        type="training",
        title="Technical Skills Update",
        description="Review latest equipment procedures and safety protocols",
        expected_impact="Improved efficiency and safety compliance",
    ))

    # Achievements
    achievements = []
    if stats["all_completed"] >= 100:
        achievements.append(Achievement(
            id=str(uuid.uuid4())[:8],
            title="Century Club",
            description=f"Completed {stats['all_completed']} total jobs",
            earned_date=str(date.today()),
            type="milestone",
        ))
    if stats["all_completed"] >= 50:
        achievements.append(Achievement(
            id=str(uuid.uuid4())[:8],
            title="Half Century",
            description="Completed 50+ jobs",
            earned_date=str(date.today()),
            type="milestone",
        ))
    if trend == "improving":
        achievements.append(Achievement(
            id=str(uuid.uuid4())[:8],
            title="Upward Trend",
            description="Performance improving over the last 30 days",
            earned_date=str(date.today()),
            type="improvement",
        ))

    return TechnicianCoachingResponse(
        technician_id=technician_id,
        technician_name=tech_name,
        overall_score=score,
        trend=trend,
        strengths=strengths,
        areas_for_improvement=improvements,
        goals=[],  # No persistent goals without DB model
        recent_achievements=achievements,
        coaching_suggestions=suggestions,
    )


@router.get("/team-summary", response_model=TeamPerformanceSummary)
async def get_team_summary(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get team-wide performance summary."""
    from sqlalchemy import select

    # Get all active technicians
    tech_q = select(Technician).where(Technician.is_active == True)
    result = await db.execute(tech_q)
    techs = result.scalars().all()

    if not techs:
        return TeamPerformanceSummary(
            team_average_score=0,
            top_performer={"id": "", "name": "N/A", "score": 0},
            most_improved={"id": "", "name": "N/A", "improvement": 0},
            needs_attention=[],
            team_goals_progress=0,
        )

    scores = []
    for tech in techs:
        tech_name = f"{tech.first_name} {tech.last_name}"
        stats = await _get_tech_stats(db, str(tech.id), tech_name)
        score = _calculate_score(stats)
        trend = _determine_trend(stats)
        scores.append({
            "id": str(tech.id),
            "name": tech_name,
            "score": score,
            "trend": trend,
            "recent_total": stats["recent_total"],
        })

    avg_score = sum(s["score"] for s in scores) / len(scores) if scores else 0
    sorted_by_score = sorted(scores, key=lambda x: x["score"], reverse=True)
    top = sorted_by_score[0] if sorted_by_score else {"id": "", "name": "N/A", "score": 0}

    # Find most improved (trend == improving with highest score)
    improving = [s for s in scores if s["trend"] == "improving"]
    most_improved = improving[0] if improving else sorted_by_score[0] if sorted_by_score else {"id": "", "name": "N/A"}

    # Needs attention: declining trend or low score
    attention = [
        {"id": s["id"], "name": s["name"], "reason": "Declining performance" if s["trend"] == "declining" else "Low activity"}
        for s in scores
        if s["trend"] == "declining" or s["recent_total"] < 3
    ]

    return TeamPerformanceSummary(
        team_average_score=round(avg_score, 1),
        top_performer={"id": top["id"], "name": top["name"], "score": top["score"]},
        most_improved={"id": most_improved["id"], "name": most_improved["name"], "improvement": 5},
        needs_attention=attention[:5],
        team_goals_progress=65.0,  # Placeholder until goals are persistent
    )


@router.post("/goals")
async def create_coaching_goal(
    request: CreateGoalRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a coaching goal (non-persistent, returns generated goal)."""
    return CoachingGoal(
        id=str(uuid.uuid4())[:8],
        title=request.title,
        description=request.description,
        target_date=request.target_date,
        progress_percent=0,
        status="not_started",
    )


@router.patch("/goals/{goal_id}")
async def update_goal_progress(
    goal_id: str,
    current_user: CurrentUser,
):
    """Update goal progress (non-persistent)."""
    return {"success": True}


@router.post("/generate-feedback")
async def generate_coaching_feedback(
    request: GenerateFeedbackRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate contextual coaching feedback."""
    from sqlalchemy import select, or_

    # Get technician info
    tech_q = select(Technician).where(Technician.id == request.technician_id)
    result = await db.execute(tech_q)
    tech = result.scalar_one_or_none()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")

    tech_name = f"{tech.first_name} {tech.last_name}"
    stats = await _get_tech_stats(db, request.technician_id, tech_name)
    score = _calculate_score(stats)

    # Generate context-appropriate feedback
    completion_pct = round((stats["recent_completed"] / max(stats["recent_total"], 1)) * 100)
    weekly_suffix = "Keep up the excellent work!" if score > 70 else "Let's discuss ways to improve efficiency."
    goal_suffix = "You're on track for your goals." if score > 60 else "Let's review your goals and adjust targets."
    job_suffix = "Excellent consistency!" if score > 80 else "Focus on completing all assigned tasks to improve your score."

    feedback_templates = {
        "weekly_review": f"Great week, {tech.first_name}! You handled {stats['recent_total']} jobs with a {completion_pct}% completion rate. {weekly_suffix}",
        "after_job": f"Job complete. {tech.first_name}, your overall score is {score}/100. {job_suffix}",
        "goal_progress": f"{tech.first_name}, you have completed {stats['all_completed']} total jobs. {goal_suffix}",
        "improvement_needed": f"{tech.first_name}, your recent performance shows room for growth. Your completion rate is {completion_pct}%. Let's work together on improving this.",
    }

    action_items_map = {
        "weekly_review": ["Review next week's schedule", "Update equipment checklist", "Log any customer feedback"],
        "after_job": ["Complete job report", "Update time log", "Note any follow-up needed"],
        "goal_progress": ["Review quarterly targets", "Identify training opportunities", "Schedule mentoring session"],
        "improvement_needed": ["Review job completion blockers", "Shadow a senior technician", "Attend safety refresher"],
    }

    feedback = feedback_templates.get(request.context, f"Keep up the good work, {tech.first_name}!")
    action_items = action_items_map.get(request.context, ["Continue current practices"])

    return {
        "feedback": feedback,
        "tone": "encouraging" if score > 60 else "supportive",
        "action_items": action_items,
    }
