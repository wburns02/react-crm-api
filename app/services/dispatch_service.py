"""
Smart dispatch service — recommends technicians for work orders
based on distance, skills, availability, and workload.
"""
import math
import logging
from datetime import date, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two lat/lon points."""
    R = 3959  # Earth's radius in miles
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def estimate_travel_minutes(distance_miles: float) -> float:
    """Estimate travel time from distance (avg 30mph in rural TX)."""
    return round(distance_miles * 2, 1)


async def get_technician_locations(db: AsyncSession, technician_ids: list[str] | None = None):
    """Get most recent location for each technician from various sources."""
    locations = {}

    # 1. Try technician_locations table (GPS broadcast)
    try:
        query = text("""
            SELECT technician_id, latitude, longitude, current_status, captured_at
            FROM technician_locations
            WHERE captured_at > NOW() - INTERVAL '30 minutes'
            ORDER BY captured_at DESC
        """)
        result = await db.execute(query)
        for row in result.fetchall():
            tid = str(row[0])
            if tid not in locations:
                locations[tid] = {
                    "lat": float(row[1]),
                    "lng": float(row[2]),
                    "source": "gps",
                    "status": row[3],
                }
    except Exception:
        logger.debug("technician_locations query failed", exc_info=True)

    # 2. Try Samsara vehicle store
    try:
        from app.api.v2.samsara import _vehicle_store

        for _vid, vehicle in _vehicle_store.items():
            gps = vehicle.get("gps")
            if gps and gps.get("latitude") and gps.get("longitude"):
                # Match vehicle to technician via assigned_vehicle
                assigned_tech_id = vehicle.get("technician_id")
                if assigned_tech_id and str(assigned_tech_id) not in locations:
                    locations[str(assigned_tech_id)] = {
                        "lat": float(gps["latitude"]),
                        "lng": float(gps["longitude"]),
                        "source": "samsara",
                        "status": vehicle.get("status", "unknown"),
                    }
    except Exception:
        logger.debug("Samsara vehicle store access failed", exc_info=True)

    # 3. Fallback to technician home location
    try:
        home_query = text("""
            SELECT id::text, home_latitude, home_longitude
            FROM technicians
            WHERE is_active = true
            AND home_latitude IS NOT NULL
            AND home_longitude IS NOT NULL
        """)
        result = await db.execute(home_query)
        for row in result.fetchall():
            tid = str(row[0])
            if tid not in locations:
                locations[tid] = {
                    "lat": float(row[1]),
                    "lng": float(row[2]),
                    "source": "home",
                    "status": "unknown",
                }
    except Exception:
        logger.debug("Home location query failed", exc_info=True)

    return locations


async def get_technician_workload(db: AsyncSession, target_date: date | None = None):
    """Get job counts per technician for today."""
    target = target_date or date.today()
    workload = {}

    try:
        query = text("""
            SELECT
                COALESCE(technician_id::text, assigned_technician) as tech_key,
                COUNT(*) as job_count,
                COUNT(CASE WHEN status IN ('enroute', 'on_site', 'in_progress') THEN 1 END) as active_count
            FROM work_orders
            WHERE scheduled_date = :target_date
            AND status NOT IN ('completed', 'canceled')
            GROUP BY COALESCE(technician_id::text, assigned_technician)
        """)
        result = await db.execute(query, {"target_date": target.isoformat()})
        for row in result.fetchall():
            if row[0]:
                workload[str(row[0])] = {
                    "scheduled_today": int(row[1]),
                    "active_jobs": int(row[2]),
                }
    except Exception:
        logger.warning("Workload query failed", exc_info=True)

    return workload


async def recommend_technicians(
    db: AsyncSession,
    work_order_id: str,
    max_results: int = 5,
) -> dict:
    """
    Recommend technicians for a work order based on:
    1. Distance (from current location or home)
    2. Skills match (job_type vs technician skills)
    3. Availability (not currently on active job)
    4. Workload (fewer jobs today = higher score)

    Returns ranked list of technician recommendations.
    """
    # 1. Get work order details
    wo_query = text("""
        SELECT wo.id::text, wo.job_type, wo.service_latitude, wo.service_longitude,
               wo.service_address_line1, wo.service_city, wo.service_state,
               wo.scheduled_date, wo.priority,
               c.latitude, c.longitude
        FROM work_orders wo
        LEFT JOIN customers c ON wo.customer_id = c.id
        WHERE wo.id = :wo_id
    """)
    wo_result = await db.execute(wo_query, {"wo_id": work_order_id})
    wo_row = wo_result.fetchone()

    if not wo_row:
        return {"error": "Work order not found", "recommended_technicians": []}

    # Determine job location (prefer WO service coords, fall back to customer coords)
    job_lat = wo_row[2] or (float(wo_row[9]) if wo_row[9] else None)
    job_lng = wo_row[3] or (float(wo_row[10]) if wo_row[10] else None)
    job_type = wo_row[1] or "pumping"
    scheduled_date = wo_row[7]
    priority = wo_row[8] or "normal"

    # 2. Get all active technicians
    tech_query = text("""
        SELECT id::text, first_name, last_name, skills, phone,
               home_latitude, home_longitude
        FROM technicians
        WHERE is_active = true
    """)
    tech_result = await db.execute(tech_query)
    technicians = tech_result.fetchall()

    if not technicians:
        return {
            "work_order_id": work_order_id,
            "recommended_technicians": [],
            "message": "No active technicians found",
        }

    # 3. Get current locations
    locations = await get_technician_locations(db)

    # 4. Get workload
    workload = await get_technician_workload(
        db, scheduled_date if scheduled_date else date.today()
    )

    # 5. Score each technician
    recommendations = []

    for tech in technicians:
        tech_id = str(tech[0])
        tech_name = f"{tech[1] or ''} {tech[2] or ''}".strip()
        tech_skills = tech[3] or []  # PostgreSQL TEXT[] → Python list
        tech_phone = tech[4]

        # If skills is a string (shouldn't be but safety), parse it
        if isinstance(tech_skills, str):
            tech_skills = [s.strip() for s in tech_skills.split(",") if s.strip()]

        # Skills match
        skills_match = job_type in tech_skills if tech_skills else True  # No skills = can do anything
        skills_missing = [] if skills_match else [job_type]

        # Distance calculation
        distance = None
        travel_minutes = None
        location_source = None

        if job_lat and job_lng:
            loc = locations.get(tech_id)
            if loc:
                distance = haversine_distance(loc["lat"], loc["lng"], job_lat, job_lng)
                travel_minutes = estimate_travel_minutes(distance)
                location_source = loc["source"]

        # Workload
        tech_workload = workload.get(tech_id) or workload.get(tech_name, {})
        scheduled_today = tech_workload.get("scheduled_today", 0)
        active_jobs = tech_workload.get("active_jobs", 0)

        # Availability
        availability = "available"
        if active_jobs > 0:
            availability = "on_job"
        elif scheduled_today >= 6:
            availability = "heavy_load"

        # Composite score (0-100)
        score = 50.0  # base

        # Distance factor (-30 to +30 points)
        if distance is not None:
            if distance < 5:
                score += 30
            elif distance < 15:
                score += 20
            elif distance < 30:
                score += 10
            elif distance < 50:
                score += 0
            else:
                score -= 10

        # Skills factor (+20 or -20)
        if skills_match:
            score += 20
        else:
            score -= 20

        # Availability factor
        if availability == "available":
            score += 15
        elif availability == "on_job":
            score -= 10
        elif availability == "heavy_load":
            score -= 15

        # Workload factor (fewer jobs = better)
        if scheduled_today <= 2:
            score += 10
        elif scheduled_today <= 4:
            score += 5
        elif scheduled_today >= 6:
            score -= 5

        # Priority bonus for emergency/urgent
        if priority in ("emergency", "urgent") and availability == "available":
            score += 10

        score = max(0, min(100, score))

        recommendations.append({
            "technician_id": tech_id,
            "name": tech_name,
            "phone": tech_phone,
            "distance_miles": round(distance, 1) if distance is not None else None,
            "estimated_travel_minutes": travel_minutes,
            "location_source": location_source,
            "skills_match": [s for s in tech_skills if s == job_type] if tech_skills else [],
            "skills_missing": skills_missing,
            "availability": availability,
            "job_load": {
                "active_jobs": active_jobs,
                "scheduled_today": scheduled_today,
            },
            "score": round(score, 1),
        })

    # Sort by score descending
    recommendations.sort(key=lambda r: r["score"], reverse=True)

    return {
        "work_order_id": work_order_id,
        "job_type": job_type,
        "job_location": {
            "lat": job_lat,
            "lng": job_lng,
            "address": f"{wo_row[4] or ''}, {wo_row[5] or ''}, {wo_row[6] or ''}".strip(", "),
        },
        "priority": priority,
        "recommended_technicians": recommendations[:max_results],
        "total_active_technicians": len(technicians),
    }
