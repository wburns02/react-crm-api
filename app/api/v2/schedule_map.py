"""Schedule Map API - GPS-based visual scheduling.

Features:
- Technician locations
- Job locations and clustering
- Route optimization
- Real-time updates
"""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, and_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
import logging
import math

from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter()


# Models

class LocationUpdate(BaseModel):
    technician_id: str
    latitude: float
    longitude: float
    heading: Optional[float] = None
    speed: Optional[float] = None
    timestamp: Optional[datetime] = None


class RouteOptimizeRequest(BaseModel):
    technician_id: str
    work_order_ids: List[str]
    optimize_for: str = "distance"  # distance, time, priority


# Helper functions

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in miles."""
    R = 3959  # Earth's radius in miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c


def simple_route_optimize(locations: List[dict], start_location: dict) -> List[dict]:
    """Simple nearest-neighbor route optimization."""
    if not locations:
        return []

    route = []
    remaining = locations.copy()
    current = start_location

    while remaining:
        # Find nearest location
        nearest = min(
            remaining,
            key=lambda loc: haversine_distance(
                current["latitude"], current["longitude"],
                loc["latitude"], loc["longitude"]
            )
        )
        route.append(nearest)
        remaining.remove(nearest)
        current = nearest

    return route


# Endpoints

@router.get("/technicians")
async def get_technician_locations(
    db: DbSession,
    current_user: CurrentUser,
    is_active: bool = True,
):
    """Get all technician locations for map display."""
    query = select(Technician)

    if is_active:
        query = query.where(Technician.is_active == True)

    result = await db.execute(query)
    technicians = result.scalars().all()

    return {
        "technicians": [
            {
                "id": str(t.id),
                "name": f"{t.first_name} {t.last_name}".strip(),
                "home_latitude": t.home_latitude,
                "home_longitude": t.home_longitude,
                "home_address": t.home_address,
                "home_city": t.home_city,
                "assigned_vehicle": t.assigned_vehicle,
                # Current location would come from GPS tracking
                "current_latitude": t.home_latitude,  # Placeholder
                "current_longitude": t.home_longitude,
                "last_update": None,
            }
            for t in technicians
            if t.home_latitude and t.home_longitude
        ],
    }


@router.get("/jobs")
async def get_job_locations(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[date] = None,
    technician_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """Get job locations for map display."""
    query = select(WorkOrder)

    if date_filter:
        query = query.where(WorkOrder.scheduled_date == date_filter)
    else:
        # Default to today
        query = query.where(WorkOrder.scheduled_date == date.today())

    if technician_id:
        query = query.where(WorkOrder.technician_id == technician_id)

    if status_filter:
        query = query.where(WorkOrder.status == status_filter)

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(wo.id),
                "customer_id": str(wo.customer_id),
                "technician_id": wo.technician_id,
                "job_type": wo.job_type,
                "status": wo.status,
                "priority": wo.priority,
                "scheduled_date": wo.scheduled_date.isoformat() if wo.scheduled_date else None,
                "time_window_start": str(wo.time_window_start) if wo.time_window_start else None,
                "time_window_end": str(wo.time_window_end) if wo.time_window_end else None,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "address": wo.service_address_line1,
                "city": wo.service_city,
                "estimated_duration_hours": wo.estimated_duration_hours,
            }
            for wo in work_orders
            if wo.service_latitude and wo.service_longitude
        ],
    }


@router.get("/jobs/unscheduled")
async def get_unscheduled_jobs(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get jobs without scheduled date for drag-and-drop scheduling."""
    query = select(WorkOrder).where(
        WorkOrder.scheduled_date.is_(None),
        WorkOrder.status.notin_(["completed", "cancelled"]),
    )

    result = await db.execute(query)
    work_orders = result.scalars().all()

    return {
        "jobs": [
            {
                "id": str(wo.id),
                "customer_id": str(wo.customer_id),
                "job_type": wo.job_type,
                "priority": wo.priority,
                "latitude": wo.service_latitude,
                "longitude": wo.service_longitude,
                "address": wo.service_address_line1,
                "city": wo.service_city,
                "estimated_duration_hours": wo.estimated_duration_hours,
            }
            for wo in work_orders
        ],
    }


@router.get("/clusters")
async def get_job_clusters(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[date] = None,
    cluster_radius_miles: float = 5.0,
):
    """Get job clusters for overview map."""
    # Get all jobs for the date
    query = select(WorkOrder)

    if date_filter:
        query = query.where(WorkOrder.scheduled_date == date_filter)
    else:
        query = query.where(WorkOrder.scheduled_date == date.today())

    result = await db.execute(query)
    work_orders = result.scalars().all()

    # Simple clustering by proximity
    jobs_with_location = [
        {
            "id": str(wo.id),
            "latitude": wo.service_latitude,
            "longitude": wo.service_longitude,
            "status": wo.status,
        }
        for wo in work_orders
        if wo.service_latitude and wo.service_longitude
    ]

    if not jobs_with_location:
        return {"clusters": []}

    # Group nearby jobs
    clusters = []
    used = set()

    for job in jobs_with_location:
        if job["id"] in used:
            continue

        cluster = {
            "center_latitude": job["latitude"],
            "center_longitude": job["longitude"],
            "job_count": 1,
            "job_ids": [job["id"]],
        }
        used.add(job["id"])

        # Find nearby jobs
        for other in jobs_with_location:
            if other["id"] in used:
                continue

            distance = haversine_distance(
                job["latitude"], job["longitude"],
                other["latitude"], other["longitude"]
            )

            if distance <= cluster_radius_miles:
                cluster["job_count"] += 1
                cluster["job_ids"].append(other["id"])
                used.add(other["id"])

        clusters.append(cluster)

    return {"clusters": clusters}


@router.post("/route/optimize")
async def optimize_route(
    request: RouteOptimizeRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Optimize route for a technician's jobs."""
    # Get technician home location
    tech_result = await db.execute(
        select(Technician).where(Technician.id == request.technician_id)
    )
    technician = tech_result.scalar_one_or_none()

    if not technician:
        raise HTTPException(status_code=404, detail="Technician not found")

    if not technician.home_latitude or not technician.home_longitude:
        raise HTTPException(status_code=400, detail="Technician has no home location")

    # Get work orders
    wo_result = await db.execute(
        select(WorkOrder).where(WorkOrder.id.in_(request.work_order_ids))
    )
    work_orders = wo_result.scalars().all()

    # Build location list
    locations = [
        {
            "work_order_id": str(wo.id),
            "latitude": wo.service_latitude,
            "longitude": wo.service_longitude,
            "priority": wo.priority,
            "time_window_start": wo.time_window_start,
        }
        for wo in work_orders
        if wo.service_latitude and wo.service_longitude
    ]

    start = {
        "latitude": technician.home_latitude,
        "longitude": technician.home_longitude,
    }

    # Optimize route (simple nearest-neighbor)
    optimized = simple_route_optimize(locations, start)

    # Calculate total distance
    total_distance = 0.0
    prev = start
    for loc in optimized:
        total_distance += haversine_distance(
            prev["latitude"], prev["longitude"],
            loc["latitude"], loc["longitude"]
        )
        prev = loc

    return {
        "optimized_route": [loc["work_order_id"] for loc in optimized],
        "total_distance_miles": round(total_distance, 1),
        "estimated_drive_time_minutes": round(total_distance * 2, 0),  # Rough estimate
    }


@router.post("/location")
async def update_technician_location(
    request: LocationUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update technician's current location (from GPS)."""
    # TODO: Store in a separate real-time location table
    # For now, just acknowledge

    return {
        "status": "received",
        "technician_id": request.technician_id,
        "timestamp": request.timestamp or datetime.utcnow(),
    }


@router.get("/bounds")
async def get_map_bounds(
    db: DbSession,
    current_user: CurrentUser,
    date_filter: Optional[date] = None,
):
    """Get map bounds to fit all jobs and technicians."""
    # Get job locations
    query = select(WorkOrder)
    if date_filter:
        query = query.where(WorkOrder.scheduled_date == date_filter)
    else:
        query = query.where(WorkOrder.scheduled_date == date.today())

    wo_result = await db.execute(query)
    work_orders = wo_result.scalars().all()

    # Get technician locations
    tech_result = await db.execute(
        select(Technician).where(Technician.is_active == True)
    )
    technicians = tech_result.scalars().all()

    # Collect all coordinates
    lats = []
    lons = []

    for wo in work_orders:
        if wo.service_latitude and wo.service_longitude:
            lats.append(wo.service_latitude)
            lons.append(wo.service_longitude)

    for tech in technicians:
        if tech.home_latitude and tech.home_longitude:
            lats.append(tech.home_latitude)
            lons.append(tech.home_longitude)

    if not lats or not lons:
        # Default to a reasonable area if no data
        return {
            "bounds": {
                "north": 30.0,
                "south": 29.0,
                "east": -95.0,
                "west": -96.0,
            },
        }

    # Add padding
    padding = 0.1

    return {
        "bounds": {
            "north": max(lats) + padding,
            "south": min(lats) - padding,
            "east": max(lons) + padding,
            "west": min(lons) - padding,
        },
        "center": {
            "latitude": sum(lats) / len(lats),
            "longitude": sum(lons) / len(lons),
        },
    }
