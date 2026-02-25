"""Technician Gamification API — streaks, badges, leaderboard.

No new DB tables. Everything computed from work_orders.
"""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func, and_, case, distinct
from datetime import date, timedelta
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────


async def _get_technician_id(user, db) -> str:
    """Resolve current user to their technician record UUID."""
    result = await db.execute(
        select(Technician.id).where(Technician.email == user.email)
    )
    tech_id = result.scalar_one_or_none()
    if not tech_id:
        raise HTTPException(status_code=404, detail="No technician record for this user")
    return tech_id


async def _completed_dates(db, tech_id, since: date) -> set[date]:
    """Set of calendar dates with ≥1 completed WO for technician."""
    result = await db.execute(
        select(WorkOrder.scheduled_date)
        .where(
            and_(
                WorkOrder.technician_id == tech_id,
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= since,
                WorkOrder.scheduled_date != None,
            )
        )
        .distinct()
    )
    return {row[0] for row in result.all() if row[0]}


def _current_streak(dates: set[date]) -> int:
    """Consecutive calendar days with work, scanning backwards from today."""
    streak = 0
    d = date.today()
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


def _best_streak(dates: set[date]) -> int:
    """Longest consecutive-day run in the date set."""
    if not dates:
        return 0
    sorted_dates = sorted(dates)
    best = current = 1
    for i in range(1, len(sorted_dates)):
        if sorted_dates[i] - sorted_dates[i - 1] == timedelta(days=1):
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


async def _compute_stats(db, tech_id) -> dict:
    today = date.today()
    year_ago = today - timedelta(days=365)
    ninety_ago = today - timedelta(days=90)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    base = and_(WorkOrder.technician_id == tech_id)
    completed = and_(base, WorkOrder.status == "completed")

    # Dates for streak calc
    dates = await _completed_dates(db, tech_id, year_ago)

    # Total assigned last 90 days
    total_90 = (await db.execute(
        select(func.count()).where(and_(base, WorkOrder.scheduled_date >= ninety_ago))
    )).scalar() or 0

    # Completed last 90 days
    completed_90 = (await db.execute(
        select(func.count()).where(and_(completed, WorkOrder.scheduled_date >= ninety_ago))
    )).scalar() or 0

    # Avg duration (completed, 90 days)
    avg_dur = (await db.execute(
        select(func.avg(WorkOrder.total_labor_minutes)).where(
            and_(completed, WorkOrder.scheduled_date >= ninety_ago)
        )
    )).scalar() or 0

    # On-time: completed jobs with actual_start_time set (90 days)
    on_time_count = (await db.execute(
        select(func.count()).where(
            and_(completed, WorkOrder.scheduled_date >= ninety_ago, WorkOrder.actual_start_time != None)
        )
    )).scalar() or 0

    # Week / Month / Lifetime
    week_count = (await db.execute(
        select(func.count()).where(and_(completed, WorkOrder.scheduled_date >= week_ago))
    )).scalar() or 0

    month_count = (await db.execute(
        select(func.count()).where(and_(completed, WorkOrder.scheduled_date >= month_ago))
    )).scalar() or 0

    lifetime_count = (await db.execute(
        select(func.count()).where(completed)
    )).scalar() or 0

    # Distinct job types
    job_types = (await db.execute(
        select(func.count(distinct(WorkOrder.job_type))).where(completed)
    )).scalar() or 0

    return {
        "current_streak": _current_streak(dates),
        "best_streak": _best_streak(dates),
        "completion_rate": round(completed_90 / total_90 * 100, 1) if total_90 else 0,
        "avg_job_duration_minutes": round(float(avg_dur), 1),
        "jobs_completed_week": week_count,
        "jobs_completed_month": month_count,
        "jobs_completed_lifetime": lifetime_count,
        "on_time_rate": round(on_time_count / completed_90 * 100, 1) if completed_90 else 0,
        "job_types_completed": job_types,
    }


# ─── Badge Definitions ───────────────────────────────────

BADGE_DEFS = [
    {"id": "hat_trick", "name": "Hat Trick", "icon": "🎯", "description": "3-day work streak", "field": "current_streak", "target": 3},
    {"id": "on_fire", "name": "On Fire", "icon": "🔥", "description": "5-day work streak", "field": "current_streak", "target": 5},
    {"id": "unstoppable", "name": "Unstoppable", "icon": "💪", "description": "10-day work streak", "field": "current_streak", "target": 10},
    {"id": "iron_will", "name": "Iron Will", "icon": "🏆", "description": "30-day work streak", "field": "current_streak", "target": 30},
    {"id": "speed_demon", "name": "Speed Demon", "icon": "⚡", "description": "Avg job under 60 min (10+ jobs)", "field": "speed", "target": 60},
    {"id": "perfect_week", "name": "Perfect Week", "icon": "✨", "description": "5+ jobs in a week, 100% completion", "field": "perfect_week", "target": 1},
    {"id": "century_club", "name": "Century Club", "icon": "💯", "description": "100 lifetime jobs completed", "field": "jobs_completed_lifetime", "target": 100},
    {"id": "half_century", "name": "Half Century", "icon": "🎖️", "description": "50 lifetime jobs completed", "field": "jobs_completed_lifetime", "target": 50},
    {"id": "jack_of_all_trades", "name": "Jack of All Trades", "icon": "🃏", "description": "Complete all 8 job types", "field": "job_types_completed", "target": 8},
    {"id": "early_bird", "name": "Early Bird", "icon": "🐦", "description": "95%+ on-time rate (20+ jobs)", "field": "on_time", "target": 95},
]


def _evaluate_badges(stats: dict) -> list[dict]:
    badges = []
    for b in BADGE_DEFS:
        field = b["field"]
        target = b["target"]

        if field in ("current_streak",):
            # Use best_streak for unlock check (earned once = earned forever)
            progress = max(stats.get("current_streak", 0), stats.get("best_streak", 0))
            unlocked = progress >= target
        elif field == "speed":
            avg = stats.get("avg_job_duration_minutes", 999)
            total = stats.get("jobs_completed_lifetime", 0)
            unlocked = avg > 0 and avg < target and total >= 10
            progress = max(0, target - avg) if total >= 10 else 0
        elif field == "perfect_week":
            unlocked = stats.get("jobs_completed_week", 0) >= 5 and stats.get("completion_rate", 0) == 100
            progress = 1 if unlocked else 0
        elif field == "on_time":
            unlocked = stats.get("on_time_rate", 0) >= target and stats.get("jobs_completed_lifetime", 0) >= 20
            progress = stats.get("on_time_rate", 0)
        else:
            progress = stats.get(field, 0)
            unlocked = progress >= target

        badges.append({
            "id": b["id"],
            "name": b["name"],
            "icon": b["icon"],
            "description": b["description"],
            "unlocked": unlocked,
            "progress": min(progress, target),
            "target": target,
        })
    return badges


# ─── Endpoints ────────────────────────────────────────────


@router.get("/my-stats")
async def get_my_stats(db: DbSession, user: CurrentUser):
    tech_id = await _get_technician_id(user, db)
    stats = await _compute_stats(db, tech_id)
    return stats


@router.get("/badges")
async def get_badges(db: DbSession, user: CurrentUser):
    tech_id = await _get_technician_id(user, db)
    stats = await _compute_stats(db, tech_id)
    return _evaluate_badges(stats)


@router.get("/leaderboard")
async def get_leaderboard(db: DbSession, user: CurrentUser):
    tech_id = await _get_technician_id(user, db)
    today = date.today()
    month_start = today.replace(day=1)

    # All techs with completed jobs this month
    tech_name = func.concat(Technician.first_name, " ", Technician.last_name).label("tech_name")
    result = await db.execute(
        select(
            Technician.id,
            tech_name,
            func.count().label("jobs_completed"),
        )
        .join(WorkOrder, WorkOrder.technician_id == Technician.id)
        .where(
            and_(
                WorkOrder.status == "completed",
                WorkOrder.scheduled_date >= month_start,
            )
        )
        .group_by(Technician.id, Technician.first_name, Technician.last_name)
        .order_by(func.count().desc())
    )
    rows = result.all()

    leaderboard = []
    my_position = None
    for i, row in enumerate(rows):
        entry = {
            "rank": i + 1,
            "technician_id": str(row.id),
            "name": row.tech_name or "Unknown",
            "jobs_completed": row.jobs_completed,
            "is_current_user": str(row.id) == str(tech_id),
        }
        if entry["is_current_user"]:
            my_position = entry
        leaderboard.append(entry)

    return {
        "leaderboard": leaderboard[:10],
        "my_position": my_position,
        "total_technicians": len(leaderboard),
    }


@router.get("/next-milestones")
async def get_next_milestones(db: DbSession, user: CurrentUser):
    tech_id = await _get_technician_id(user, db)
    stats = await _compute_stats(db, tech_id)
    milestones = []

    streak = stats["current_streak"]
    if streak < 3:
        milestones.append(f"{3 - streak} more day{'s' if 3 - streak > 1 else ''} for Hat Trick!")
    elif streak < 5:
        milestones.append(f"{5 - streak} more day{'s' if 5 - streak > 1 else ''} for On Fire!")
    elif streak < 10:
        milestones.append(f"{10 - streak} more day{'s' if 10 - streak > 1 else ''} for Unstoppable!")
    elif streak < 30:
        milestones.append(f"{30 - streak} more day{'s' if 30 - streak > 1 else ''} for Iron Will!")

    lifetime = stats["jobs_completed_lifetime"]
    if lifetime < 50:
        milestones.append(f"{50 - lifetime} jobs to Half Century!")
    elif lifetime < 100:
        milestones.append(f"{100 - lifetime} jobs to Century Club!")

    jt = stats["job_types_completed"]
    if jt < 8:
        milestones.append(f"{8 - jt} more job type{'s' if 8 - jt > 1 else ''} to Jack of All Trades!")

    if not milestones:
        milestones.append("You've unlocked all milestones — legendary status!")

    return {"milestones": milestones[:3]}
