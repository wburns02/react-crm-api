"""
AI Coaching — Real Data Endpoints

Provides coaching insights derived from work_orders, technicians, and call_logs.
No separate DB models needed — all data derived from existing tables.

Endpoints:
  GET /coaching/technician-performance  — Per-tech WO stats over last 90 days
  GET /coaching/call-insights           — Call log aggregation (graceful if empty)
  GET /coaching/recommendations         — Rule-based coaching flags
  GET /coaching/team-benchmarks         — Team-wide summary
"""

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, case, select, or_
from sqlalchemy.exc import OperationalError

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.call_log import CallLog

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helper: compute per-technician work order stats over the last N days
# ---------------------------------------------------------------------------

async def _compute_tech_stats(db: DbSession, days: int = 90) -> list[dict]:
    """
    Returns a list of dicts with technician stats from work_orders.
    Covers BOTH technician_id (UUID FK) and assigned_technician (name string).
    """
    since = date.today() - timedelta(days=days)

    # -- technician_id-based stats (joined to Technician table for name) --
    uuid_q = select(
        Technician.id.label("tech_id"),
        func.concat(Technician.first_name, " ", Technician.last_name).label("tech_name"),
        func.count(WorkOrder.id).label("total_jobs"),
        func.count(case((WorkOrder.status == "completed", 1))).label("completed_jobs"),
        func.max(WorkOrder.job_type).label("common_job_type"),  # placeholder; real grouping below
    ).join(
        WorkOrder,
        WorkOrder.technician_id == Technician.id,
        isouter=False,
    ).where(
        WorkOrder.scheduled_date >= since,
    ).group_by(Technician.id, Technician.first_name, Technician.last_name)

    uuid_result = await db.execute(uuid_q)
    uuid_rows = uuid_result.all()

    # -- assigned_technician (string) stats — excludes those already counted above --
    name_q = select(
        WorkOrder.assigned_technician.label("tech_name"),
        func.count(WorkOrder.id).label("total_jobs"),
        func.count(case((WorkOrder.status == "completed", 1))).label("completed_jobs"),
    ).where(
        WorkOrder.assigned_technician.isnot(None),
        WorkOrder.assigned_technician != "",
        WorkOrder.technician_id.is_(None),  # only unclaimed by UUID
        WorkOrder.scheduled_date >= since,
    ).group_by(WorkOrder.assigned_technician)

    name_result = await db.execute(name_q)
    name_rows = name_result.all()

    # -- top job_type per technician (separate query) --
    top_job_q = select(
        WorkOrder.assigned_technician,
        WorkOrder.job_type,
        func.count(WorkOrder.id).label("cnt"),
    ).where(
        WorkOrder.assigned_technician.isnot(None),
        WorkOrder.scheduled_date >= since,
    ).group_by(WorkOrder.assigned_technician, WorkOrder.job_type)
    top_job_result = await db.execute(top_job_q)
    top_job_rows = top_job_result.all()

    # Build {name → top_job_type} map
    top_job: dict[str, tuple[str, int]] = {}
    for row in top_job_rows:
        name = row.assigned_technician or ""
        cnt = row.cnt or 0
        if name not in top_job or cnt > top_job[name][1]:
            top_job[name] = (row.job_type or "pumping", cnt)

    # Also get top job for UUID-linked techs
    top_job_uuid_q = select(
        WorkOrder.technician_id,
        WorkOrder.job_type,
        func.count(WorkOrder.id).label("cnt"),
    ).where(
        WorkOrder.technician_id.isnot(None),
        WorkOrder.scheduled_date >= since,
    ).group_by(WorkOrder.technician_id, WorkOrder.job_type)
    top_job_uuid_result = await db.execute(top_job_uuid_q)
    top_job_uuid_rows = top_job_uuid_result.all()

    top_job_by_id: dict[str, tuple[str, int]] = {}
    for row in top_job_uuid_rows:
        tid = str(row.technician_id) if row.technician_id else ""
        cnt = row.cnt or 0
        if tid not in top_job_by_id or cnt > top_job_by_id[tid][1]:
            top_job_by_id[tid] = (row.job_type or "pumping", cnt)

    stats: list[dict] = []

    weeks = max(days / 7, 1)

    for row in uuid_rows:
        total = row.total_jobs or 0
        completed = row.completed_jobs or 0
        rate = round(completed / total, 3) if total > 0 else 0.0
        tid = str(row.tech_id)
        stats.append({
            "id": tid,
            "name": row.tech_name or "Unknown",
            "total_jobs": total,
            "completed_jobs": completed,
            "completion_rate": rate,
            "avg_jobs_per_week": round(total / weeks, 2),
            "top_job_type": top_job_by_id.get(tid, ("pumping", 0))[0],
            "needs_coaching": rate < 0.70 or total / weeks < 1.0,
        })

    # Merge name-based rows (avoid duplicating names that appear in UUID rows)
    uuid_names = {s["name"].lower() for s in stats}
    for row in name_rows:
        name = row.tech_name or "Unknown"
        if name.lower() in uuid_names:
            continue
        total = row.total_jobs or 0
        completed = row.completed_jobs or 0
        rate = round(completed / total, 3) if total > 0 else 0.0
        stats.append({
            "id": None,
            "name": name,
            "total_jobs": total,
            "completed_jobs": completed,
            "completion_rate": rate,
            "avg_jobs_per_week": round(total / weeks, 2),
            "top_job_type": top_job.get(name, ("pumping", 0))[0],
            "needs_coaching": rate < 0.70 or total / weeks < 1.0,
        })

    return stats


# ---------------------------------------------------------------------------
# Endpoint 1: GET /coaching/technician-performance
# ---------------------------------------------------------------------------

@router.get("/technician-performance")
async def get_technician_performance(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Returns per-technician work order performance stats over the last 90 days.
    Maps technician_id → name via Technician table.
    Falls back to assigned_technician string for unclaimed orders.
    """
    try:
        stats = await _compute_tech_stats(db, days=90)
        total_rate = (
            sum(s["completion_rate"] for s in stats) / len(stats)
            if stats else 0.0
        )
        return {
            "technicians": stats,
            "team_avg_completion_rate": round(total_rate, 3),
            "period_days": 90,
        }
    except Exception as e:
        logger.error(f"Error in technician-performance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoint 2: GET /coaching/call-insights
# ---------------------------------------------------------------------------

@router.get("/call-insights")
async def get_call_insights(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Aggregates call_logs table into coaching insights.
    Returns graceful empty state if table is empty or doesn't exist.
    """
    try:
        # Total calls
        total_q = select(func.count(CallLog.id))
        total_result = await db.execute(total_q)
        total_calls = total_result.scalar() or 0

        if total_calls == 0:
            return {
                "total_calls": 0,
                "avg_duration_minutes": 0.0,
                "by_outcome": {},
                "conversion_rate": 0.0,
                "top_agents": [],
                "coaching_flags": [],
                "message": "No call data available yet. Connect your phone system to enable call insights.",
            }

        # Average duration
        avg_dur_q = select(func.avg(CallLog.duration_seconds))
        avg_dur_result = await db.execute(avg_dur_q)
        avg_dur_seconds = avg_dur_result.scalar() or 0
        avg_dur_minutes = round((avg_dur_seconds or 0) / 60, 1)

        # Outcomes/dispositions breakdown
        outcome_q = select(
            CallLog.call_disposition,
            func.count(CallLog.id).label("cnt"),
        ).group_by(CallLog.call_disposition)
        outcome_result = await db.execute(outcome_q)
        outcome_rows = outcome_result.all()

        by_outcome: dict[str, int] = {}
        booked_count = 0
        for row in outcome_rows:
            key = (row.call_disposition or "unknown").lower().strip()
            if not key:
                key = "unknown"
            by_outcome[key] = row.cnt or 0
            # Count "booked" or "appointment" outcomes as conversions
            if any(w in key for w in ["book", "appoint", "schedule", "confirm", "sold"]):
                booked_count += row.cnt or 0

        conversion_rate = round(booked_count / total_calls, 3) if total_calls > 0 else 0.0

        # Per-agent stats (using assigned_to column)
        agent_q = select(
            CallLog.assigned_to.label("agent_name"),
            func.count(CallLog.id).label("total_calls"),
            func.count(case((
                CallLog.call_disposition.ilike("%book%") |
                CallLog.call_disposition.ilike("%appoint%") |
                CallLog.call_disposition.ilike("%schedule%") |
                CallLog.call_disposition.ilike("%confirm%") |
                CallLog.call_disposition.ilike("%sold%"),
                1,
            ))).label("converted"),
        ).where(
            CallLog.assigned_to.isnot(None),
            CallLog.assigned_to != "",
        ).group_by(CallLog.assigned_to)

        agent_result = await db.execute(agent_q)
        agent_rows = agent_result.all()

        top_agents = []
        coaching_flags = []
        for row in agent_rows:
            total = row.total_calls or 0
            converted = row.converted or 0
            rate = round(converted / total, 3) if total > 0 else 0.0
            agent_info = {
                "name": row.agent_name,
                "calls": total,
                "conversion_rate": rate,
            }
            top_agents.append(agent_info)
            # Flag agents with low conversion
            if rate < 0.40 and total >= 5:
                coaching_flags.append({
                    "agent": row.agent_name,
                    "issue": "Low conversion rate",
                    "rate": rate,
                })

        # Sort top agents by conversion rate descending
        top_agents.sort(key=lambda x: x["conversion_rate"], reverse=True)

        return {
            "total_calls": total_calls,
            "avg_duration_minutes": avg_dur_minutes,
            "by_outcome": by_outcome,
            "conversion_rate": conversion_rate,
            "top_agents": top_agents[:10],
            "coaching_flags": coaching_flags,
        }

    except OperationalError as e:
        logger.warning(f"Call logs table unavailable: {e}")
        return {
            "total_calls": 0,
            "avg_duration_minutes": 0.0,
            "by_outcome": {},
            "conversion_rate": 0.0,
            "top_agents": [],
            "coaching_flags": [],
            "message": "Call data not yet available.",
        }
    except Exception as e:
        logger.error(f"Error in call-insights: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoint 3: GET /coaching/recommendations
# ---------------------------------------------------------------------------

@router.get("/recommendations")
async def get_recommendations(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Rule-based coaching recommendations.
    Generates flags from tech completion rates and call conversion rates.
    No ML required.
    """
    try:
        stats = await _compute_tech_stats(db, days=90)
        total_rate = (
            sum(s["completion_rate"] for s in stats) / len(stats)
            if stats else 0.0
        )

        recommendations: list[dict] = []

        # Technician rules
        for tech in stats:
            rate = tech["completion_rate"]
            avg_rate = total_rate
            if rate < 0.50:
                severity = "critical"
                title = "Critically low completion rate"
                detail = (
                    f"{round(rate * 100, 1)}% completion rate "
                    f"(team avg: {round(avg_rate * 100, 1)}%) over last 90 days."
                )
                action = "Immediate 1:1 review required"
            elif rate < 0.70:
                severity = "warning"
                title = "Below-average completion rate"
                detail = (
                    f"{round(rate * 100, 1)}% completion rate "
                    f"(team avg: {round(avg_rate * 100, 1)}%) over last 90 days."
                )
                action = "Schedule 1:1 review"
            elif tech["avg_jobs_per_week"] < 1.0 and tech["total_jobs"] > 0:
                severity = "info"
                title = "Low activity"
                detail = (
                    f"{tech['avg_jobs_per_week']} jobs/week average. "
                    "May need schedule adjustment."
                )
                action = "Review availability and schedule"
            else:
                continue  # No flag needed

            recommendations.append({
                "type": "technician",
                "target": tech["name"],
                "severity": severity,
                "title": title,
                "detail": detail,
                "action": action,
            })

        # Call agent rules (if call data available)
        try:
            total_calls_q = select(func.count(CallLog.id))
            total_calls_result = await db.execute(total_calls_q)
            total_calls = total_calls_result.scalar() or 0

            if total_calls > 0:
                agent_q = select(
                    CallLog.assigned_to.label("agent_name"),
                    func.count(CallLog.id).label("total_calls"),
                    func.count(case((
                        CallLog.call_disposition.ilike("%book%") |
                        CallLog.call_disposition.ilike("%appoint%") |
                        CallLog.call_disposition.ilike("%schedule%"),
                        1,
                    ))).label("converted"),
                ).where(
                    CallLog.assigned_to.isnot(None),
                    CallLog.assigned_to != "",
                ).group_by(CallLog.assigned_to)

                agent_result = await db.execute(agent_q)
                for row in agent_result.all():
                    total = row.total_calls or 0
                    converted = row.converted or 0
                    rate = converted / total if total > 0 else 0.0
                    if rate < 0.40 and total >= 5:
                        recommendations.append({
                            "type": "call_agent",
                            "target": row.agent_name,
                            "severity": "warning",
                            "title": "Low call conversion rate",
                            "detail": (
                                f"{round(rate * 100, 1)}% conversion rate "
                                f"across {total} calls."
                            ),
                            "action": "Review call scripts and booking objections",
                        })
        except OperationalError:
            pass  # call_logs table unavailable — skip call agent rules

        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        recommendations.sort(key=lambda x: severity_order.get(x["severity"], 3))

        return {"recommendations": recommendations}

    except Exception as e:
        logger.error(f"Error in recommendations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Endpoint 4: GET /coaching/team-benchmarks
# ---------------------------------------------------------------------------

@router.get("/team-benchmarks")
async def get_team_benchmarks(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Team-level benchmark summary over the last 90 days.
    """
    try:
        since = date.today() - timedelta(days=90)

        # Total WOs
        total_q = select(
            func.count(WorkOrder.id).label("total"),
            func.count(case((WorkOrder.status == "completed", 1))).label("completed"),
        ).where(
            WorkOrder.scheduled_date >= since,
        )
        total_result = await db.execute(total_q)
        totals = total_result.one()
        total_wos = totals.total or 0
        completed_wos = totals.completed or 0
        team_rate = round(completed_wos / total_wos, 3) if total_wos > 0 else 0.0

        # Per-tech stats for top performer / most active
        stats = await _compute_tech_stats(db, days=90)

        top_performer = {"name": "N/A", "completion_rate": 0.0}
        most_active = {"name": "N/A", "total_jobs": 0}

        if stats:
            top = max(stats, key=lambda s: s["completion_rate"])
            top_performer = {
                "name": top["name"],
                "completion_rate": top["completion_rate"],
            }
            active = max(stats, key=lambda s: s["total_jobs"])
            most_active = {
                "name": active["name"],
                "total_jobs": active["total_jobs"],
            }

        return {
            "period_days": 90,
            "total_work_orders": total_wos,
            "completed": completed_wos,
            "team_completion_rate": team_rate,
            "top_performer": top_performer,
            "most_active": most_active,
        }

    except Exception as e:
        logger.error(f"Error in team-benchmarks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
