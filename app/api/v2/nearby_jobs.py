"""
Nearby Jobs API — returns active work orders near a location for the current week.
Used by the call map to show existing jobs near a detected caller location.
"""

from datetime import date, timedelta
from fastapi import APIRouter, Query
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from app.api.deps import DbSession, CurrentUser
from app.models.work_order import WorkOrder
from app.models.customer import Customer
from app.services.location_extractor import haversine_distance

router = APIRouter(prefix="/work-orders", tags=["work-orders"])


@router.get("/nearby")
async def get_nearby_jobs(
    db: DbSession,
    current_user: CurrentUser,
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius_miles: float = Query(30.0, description="Search radius in miles"),
):
    """
    Get active/scheduled work orders for the current week within radius of a point.
    Returns jobs with customer name, address, scheduled date/time, and distance.
    """
    # Current week bounds (Monday to Sunday)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)

    # Query work orders for this week that have a customer with coordinates
    result = await db.execute(
        select(WorkOrder)
        .join(Customer, WorkOrder.customer_id == Customer.id)
        .where(
            and_(
                WorkOrder.scheduled_date >= monday,
                WorkOrder.scheduled_date <= sunday,
                WorkOrder.status.in_(["scheduled", "in_progress", "pending", "dispatched", "confirmed", "enroute", "on_site"]),
                Customer.latitude.isnot(None),
                Customer.longitude.isnot(None),
            )
        )
        .options(selectinload(WorkOrder.customer))
        .limit(100)
    )
    work_orders = result.scalars().all()

    # Filter by distance in Python (haversine)
    nearby = []
    for wo in work_orders:
        c = wo.customer
        if not c or not c.latitude or not c.longitude:
            continue
        dist = haversine_distance(lat, lng, float(c.latitude), float(c.longitude))
        if dist <= radius_miles:
            nearby.append({
                "id": str(wo.id),
                "customer_name": c.full_name,
                "address": f"{c.address_line1 or ''}, {c.city or ''}, {c.state or ''}".strip(", "),
                "lat": float(c.latitude),
                "lng": float(c.longitude),
                "scheduled_date": str(wo.scheduled_date) if wo.scheduled_date else None,
                "status": wo.status,
                "job_type": wo.job_type,
                "distance_miles": round(dist, 1),
            })

    # Sort by distance
    nearby.sort(key=lambda x: x["distance_miles"])
    return nearby
