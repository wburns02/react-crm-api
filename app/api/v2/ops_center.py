"""Live Operations Center — "God Mode" aggregate endpoint.

Single endpoint returns everything a dispatcher needs:
technician positions, today's jobs, alerts, weather, and AI dispatch recommendations.
"""

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func, and_, or_, text
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import logging
import httpx
import math

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter()

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"
SAN_MARCOS = {"lat": 29.8833, "lon": -97.9414}

# ─── Haversine ────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 3958.8  # miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Emergency Dispatch Recommendation (inline) ──────────

def _score_tech_for_job(
    tech: dict,
    job_lat: float | None,
    job_lon: float | None,
    job_type: str,
    tech_job_count: int,
) -> dict:
    score = 50
    factors = []

    # Distance
    if tech.get("latitude") and tech.get("longitude") and job_lat and job_lon:
        dist = _haversine(tech["latitude"], tech["longitude"], job_lat, job_lon)
        travel_min = dist * 2  # ~30 mph avg
        if dist < 5:
            score += 30
            factors.append(f"Very close ({dist:.1f} mi)")
        elif dist < 15:
            score += 20
            factors.append(f"Nearby ({dist:.1f} mi)")
        elif dist < 30:
            score += 10
            factors.append(f"Moderate distance ({dist:.1f} mi)")
        else:
            score -= 10
            factors.append(f"Far ({dist:.1f} mi)")
        tech["distance_miles"] = round(dist, 1)
        tech["estimated_travel_minutes"] = round(travel_min, 0)

    # Workload
    if tech_job_count <= 2:
        score += 10
        factors.append("Light workload")
    elif tech_job_count >= 6:
        score -= 5
        factors.append("Heavy workload")

    # Availability
    status = tech.get("status", "offline")
    if status == "available":
        score += 15
        factors.append("Currently available")
    elif status == "on_job":
        score -= 10
        factors.append("Currently on a job")

    tech["dispatch_score"] = max(0, min(100, score))
    tech["dispatch_factors"] = factors
    return tech


# ─── Main Endpoint ────────────────────────────────────────


@router.get("/live-state")
async def get_live_state(db: DbSession, user: CurrentUser):
    """Single aggregated endpoint for the operations center God Mode view."""
    today = date.today()

    # 1. All technicians with GPS positions
    techs_q = await db.execute(
        select(
            Technician.id, Technician.first_name, Technician.last_name,
            Technician.email, Technician.phone,
            Technician.home_latitude, Technician.home_longitude,
        ).where(Technician.is_active == True)
    )
    techs_raw = techs_q.all()

    # Try GPS locations (table may not exist)
    gps_map: dict = {}
    try:
        gps_q = await db.execute(text("""
            SELECT technician_id, latitude, longitude, current_status, speed, captured_at
            FROM technician_locations
            WHERE captured_at > NOW() - INTERVAL '30 minutes'
        """))
        gps_map = {str(r.technician_id): r for r in gps_q.all()}
    except Exception:
        await db.rollback()

    # 2. Today's work orders (with customer name)
    jobs_q = await db.execute(
        select(
            WorkOrder.id, WorkOrder.work_order_number, WorkOrder.customer_id,
            WorkOrder.technician_id, WorkOrder.assigned_technician,
            WorkOrder.job_type, WorkOrder.priority, WorkOrder.status,
            WorkOrder.scheduled_date, WorkOrder.time_window_start, WorkOrder.time_window_end,
            WorkOrder.service_address_line1, WorkOrder.service_city,
            WorkOrder.service_latitude, WorkOrder.service_longitude,
            WorkOrder.total_amount, WorkOrder.actual_start_time,
            Customer.first_name.label("customer_first"),
            Customer.last_name.label("customer_last"),
        ).outerjoin(Customer, WorkOrder.customer_id == Customer.id).where(
            and_(
                WorkOrder.scheduled_date == today,
                WorkOrder.status.notin_(["canceled", "cancelled"]),
            )
        ).order_by(WorkOrder.time_window_start)
    )
    jobs = jobs_q.all()

    # Job counts per tech
    job_count_map: dict[str, int] = {}
    for j in jobs:
        if j.technician_id:
            tid = str(j.technician_id)
            job_count_map[tid] = job_count_map.get(tid, 0) + 1

    # 3. Build technician list with positions
    technicians = []
    for t in techs_raw:
        tid = str(t.id)
        gps = gps_map.get(tid)
        lat = float(gps.latitude) if gps else (float(t.home_latitude) if t.home_latitude else None)
        lon = float(gps.longitude) if gps else (float(t.home_longitude) if t.home_longitude else None)
        location_source = "gps" if gps else ("home" if t.home_latitude else None)

        # Determine live status from jobs
        active_job = None
        for j in jobs:
            if str(j.technician_id) == tid and j.status in ("in_progress", "on_site", "enroute"):
                active_job = {
                    "id": str(j.id),
                    "wo_number": j.work_order_number,
                    "job_type": j.job_type,
                    "status": j.status,
                    "address": f"{j.service_address_line1 or ''}, {j.service_city or ''}".strip(", "),
                }
                break

        live_status = "on_job" if active_job else "available"

        technicians.append({
            "id": tid,
            "name": f"{t.first_name or ''} {t.last_name or ''}".strip(),
            "phone": t.phone,
            "latitude": lat,
            "longitude": lon,
            "location_source": location_source,
            "status": live_status,
            "speed": float(gps.speed) if gps and gps.speed else None,
            "last_seen": gps.captured_at.isoformat() if gps and gps.captured_at else None,
            "jobs_today": job_count_map.get(tid, 0),
            "active_job": active_job,
        })

    # 4. Build jobs list
    job_list = []
    for j in jobs:
        job_list.append({
            "id": str(j.id),
            "wo_number": j.work_order_number,
            "customer_id": str(j.customer_id) if j.customer_id else None,
            "technician_id": str(j.technician_id) if j.technician_id else None,
            "assigned_technician": j.assigned_technician,
            "job_type": j.job_type,
            "priority": j.priority or "normal",
            "status": j.status,
            "time_window_start": str(j.time_window_start) if j.time_window_start else None,
            "time_window_end": str(j.time_window_end) if j.time_window_end else None,
            "address": f"{j.service_address_line1 or ''}, {j.service_city or ''}".strip(", "),
            "latitude": float(j.service_latitude) if j.service_latitude else None,
            "longitude": float(j.service_longitude) if j.service_longitude else None,
            "amount": float(j.total_amount) if j.total_amount else None,
            "is_started": j.actual_start_time is not None,
            "customer_name": f"{j.customer_first or ''} {j.customer_last or ''}".strip() or None,
        })

    # 5. Alerts
    now = datetime.now(timezone.utc)
    alerts = []
    for j in jobs:
        if j.priority in ("emergency", "urgent") and j.status in ("scheduled", "confirmed"):
            alerts.append({
                "type": "emergency",
                "severity": "danger",
                "message": f"Emergency {j.job_type} job {j.work_order_number} not started",
                "work_order_id": str(j.id),
            })
        elif j.time_window_end and j.status in ("scheduled", "confirmed"):
            try:
                end_dt = datetime.combine(today, j.time_window_end, tzinfo=timezone.utc)
                if now > end_dt:
                    alerts.append({
                        "type": "running_late",
                        "severity": "warning",
                        "message": f"Job {j.work_order_number} past scheduled time",
                        "work_order_id": str(j.id),
                    })
            except Exception:
                pass

    # Unassigned jobs
    unassigned = [j for j in job_list if not j["technician_id"]]
    if unassigned:
        alerts.append({
            "type": "unassigned",
            "severity": "warning",
            "message": f"{len(unassigned)} job(s) have no technician assigned",
            "work_order_id": unassigned[0]["id"],
        })

    # 6. Quick stats
    completed = sum(1 for j in jobs if j.status == "completed")
    in_progress = sum(1 for j in jobs if j.status in ("in_progress", "on_site", "enroute"))
    remaining = len(jobs) - completed
    on_duty = sum(1 for t in technicians if t["status"] != "offline")
    revenue_today = sum(float(j.total_amount or 0) for j in jobs if j.status == "completed")

    # 7. Weather (best-effort, don't fail if down)
    weather = None
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(OPEN_METEO_BASE, params={
                "latitude": SAN_MARCOS["lat"],
                "longitude": SAN_MARCOS["lon"],
                "current_weather": "true",
            })
            if resp.status_code == 200:
                cw = resp.json().get("current_weather", {})
                weather = {
                    "temperature_f": round(cw.get("temperature", 0) * 9 / 5 + 32, 1),
                    "windspeed_mph": round(cw.get("windspeed", 0) * 0.621371, 1),
                    "wind_direction": cw.get("winddirection"),
                    "weather_code": cw.get("weathercode"),
                    "is_day": cw.get("is_day") == 1,
                }
    except Exception:
        pass

    return {
        "technicians": technicians,
        "jobs": job_list,
        "alerts": alerts,
        "stats": {
            "total_jobs": len(jobs),
            "completed": completed,
            "in_progress": in_progress,
            "remaining": remaining,
            "unassigned": len(unassigned),
            "on_duty_techs": on_duty,
            "total_techs": len(technicians),
            "revenue_today": round(revenue_today, 2),
            "utilization_pct": round((len(jobs) / max(on_duty * 6, 1)) * 100, 1),
        },
        "weather": weather,
        "timestamp": now.isoformat(),
    }


@router.get("/recommend-dispatch/{work_order_id}")
async def recommend_dispatch(db: DbSession, user: CurrentUser, work_order_id: str):
    """Quick AI recommendation for who should handle a specific job."""
    # Get the work order
    wo_q = await db.execute(
        select(WorkOrder).where(WorkOrder.id == work_order_id)
    )
    wo = wo_q.scalar_one_or_none()
    if not wo:
        raise HTTPException(404, "Work order not found")

    job_lat = float(wo.service_latitude) if wo.service_latitude else None
    job_lon = float(wo.service_longitude) if wo.service_longitude else None

    # Get active techs
    techs_q = await db.execute(
        select(
            Technician.id, Technician.first_name, Technician.last_name,
            Technician.phone,
            Technician.home_latitude, Technician.home_longitude,
        ).where(Technician.is_active == True)
    )
    techs = techs_q.all()

    # GPS (table may not exist)
    gps_map: dict = {}
    try:
        gps_q = await db.execute(text("""
            SELECT technician_id, latitude, longitude, current_status
            FROM technician_locations
            WHERE captured_at > NOW() - INTERVAL '30 minutes'
        """))
        gps_map = {str(r.technician_id): r for r in gps_q.all()}
    except Exception:
        await db.rollback()

    # Job counts today
    today = date.today()
    counts_q = await db.execute(
        select(WorkOrder.technician_id, func.count().label("cnt"))
        .where(and_(WorkOrder.scheduled_date == today, WorkOrder.status != "canceled"))
        .group_by(WorkOrder.technician_id)
    )
    count_map = {str(r.technician_id): r.cnt for r in counts_q.all()}

    recommendations = []
    for t in techs:
        tid = str(t.id)
        gps = gps_map.get(tid)
        tech_data = {
            "id": tid,
            "name": f"{t.first_name or ''} {t.last_name or ''}".strip(),
            "phone": t.phone,
            "latitude": float(gps.latitude) if gps else (float(t.home_latitude) if t.home_latitude else None),
            "longitude": float(gps.longitude) if gps else (float(t.home_longitude) if t.home_longitude else None),
            "location_source": "gps" if gps else "home",
            "status": (gps.current_status if gps and gps.current_status else "available"),
        }
        scored = _score_tech_for_job(tech_data, job_lat, job_lon, wo.job_type or "", count_map.get(tid, 0))
        recommendations.append(scored)

    recommendations.sort(key=lambda x: x.get("dispatch_score", 0), reverse=True)

    return {
        "work_order_id": str(wo.id),
        "wo_number": wo.work_order_number,
        "job_type": wo.job_type,
        "priority": wo.priority,
        "recommendations": recommendations[:5],
    }
