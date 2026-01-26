"""
Samsara Fleet Tracking API - Real-time vehicle locations from Samsara.

Integrates with Samsara's Fleet API to provide:
- Live vehicle locations with GPS coordinates
- Vehicle status (moving, idling, stopped, offline)
- Driver assignments
- Location history/breadcrumb trails
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import httpx
import logging

from app.api.deps import CurrentUser
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Samsara API base URL
SAMSARA_API_BASE = "https://api.samsara.com"


class VehicleLocation(BaseModel):
    """Vehicle location with GPS data and status."""
    lat: float
    lng: float
    heading: float
    speed: float  # mph
    updated_at: str


class Vehicle(BaseModel):
    """Full vehicle data matching frontend schema."""
    id: str
    name: str
    vin: Optional[str] = None
    driver_id: Optional[str] = None
    driver_name: Optional[str] = None
    location: VehicleLocation
    status: str  # moving, idling, stopped, offline


class LocationHistoryPoint(BaseModel):
    """Single point in location history."""
    lat: float
    lng: float
    timestamp: str
    speed: float


def determine_vehicle_status(speed_mph: float, engine_state: str | None, time_since_update_minutes: float) -> str:
    """
    Determine vehicle status based on speed and engine state.

    - moving: speed > 3 mph
    - idling: speed <= 3 mph but engine on
    - stopped: speed = 0, engine off
    - offline: no update in 10+ minutes
    """
    if time_since_update_minutes > 10:
        return "offline"
    if speed_mph > 3:
        return "moving"
    if engine_state == "On" or speed_mph > 0:
        return "idling"
    return "stopped"


@router.get("/vehicles")
async def get_vehicles(current_user: CurrentUser) -> list[Vehicle]:
    """
    Get all vehicle locations from Samsara.

    Calls Samsara Fleet API to get real-time vehicle positions.
    Returns empty list if Samsara is not configured.
    """
    if not settings.SAMSARA_API_TOKEN:
        logger.warning("SAMSARA_API_TOKEN not configured - returning empty vehicle list")
        return []

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get vehicles with current locations
            response = await client.get(
                f"{SAMSARA_API_BASE}/fleet/vehicles/locations",
                headers={
                    "Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 401:
                logger.error("Samsara API authentication failed - check SAMSARA_API_TOKEN")
                raise HTTPException(status_code=503, detail="Fleet tracking service authentication failed")

            if response.status_code != 200:
                logger.error(f"Samsara API error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=503, detail="Fleet tracking service unavailable")

            data = response.json()
            vehicles = []
            now = datetime.utcnow()

            for v in data.get("data", []):
                location_data = v.get("location", {})

                # Parse the timestamp
                updated_at_str = location_data.get("time", now.isoformat())
                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    time_since_update = (now - updated_at.replace(tzinfo=None)).total_seconds() / 60
                except:
                    time_since_update = 0

                # Convert speed from m/s to mph
                speed_ms = location_data.get("speed", 0) or 0
                speed_mph = speed_ms * 2.237

                # Get driver info if available
                driver_data = v.get("driver", {}) or {}
                driver_id = driver_data.get("id")
                driver_name = driver_data.get("name")

                # Determine status
                engine_state = v.get("engineState", {}).get("value") if v.get("engineState") else None
                status = determine_vehicle_status(speed_mph, engine_state, time_since_update)

                vehicle = Vehicle(
                    id=v.get("id", ""),
                    name=v.get("name", "Unknown Vehicle"),
                    vin=v.get("vin"),
                    driver_id=driver_id,
                    driver_name=driver_name,
                    location=VehicleLocation(
                        lat=location_data.get("latitude", 0),
                        lng=location_data.get("longitude", 0),
                        heading=location_data.get("heading", 0) or 0,
                        speed=round(speed_mph, 1),
                        updated_at=updated_at_str,
                    ),
                    status=status,
                )
                vehicles.append(vehicle)

            logger.info(f"Retrieved {len(vehicles)} vehicles from Samsara")
            return vehicles

    except httpx.RequestError as e:
        logger.error(f"Samsara API request failed: {e}")
        raise HTTPException(status_code=503, detail="Fleet tracking service connection failed")


@router.get("/vehicles/{vehicle_id}/history")
async def get_vehicle_history(
    vehicle_id: str,
    current_user: CurrentUser,
    hours: int = 1,
) -> list[LocationHistoryPoint]:
    """
    Get vehicle location history from Samsara.

    Returns GPS breadcrumb trail for the specified time period.
    """
    if not settings.SAMSARA_API_TOKEN:
        return []

    try:
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SAMSARA_API_BASE}/fleet/vehicles/{vehicle_id}/locations/history",
                headers={
                    "Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}",
                    "Content-Type": "application/json",
                },
                params={
                    "startTime": start_time.isoformat() + "Z",
                    "endTime": end_time.isoformat() + "Z",
                },
            )

            if response.status_code != 200:
                logger.warning(f"Failed to get vehicle history: {response.status_code}")
                return []

            data = response.json()
            history = []

            for point in data.get("data", []):
                # Convert speed from m/s to mph
                speed_ms = point.get("speed", 0) or 0
                speed_mph = speed_ms * 2.237

                history.append(LocationHistoryPoint(
                    lat=point.get("latitude", 0),
                    lng=point.get("longitude", 0),
                    timestamp=point.get("time", ""),
                    speed=round(speed_mph, 1),
                ))

            return history

    except httpx.RequestError as e:
        logger.error(f"Samsara history request failed: {e}")
        return []


@router.get("/status")
async def get_samsara_status(current_user: CurrentUser) -> dict:
    """
    Check Samsara API connectivity status.
    Useful for debugging and integration health checks.
    """
    if not settings.SAMSARA_API_TOKEN:
        return {
            "configured": False,
            "connected": False,
            "message": "SAMSARA_API_TOKEN not set in environment",
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SAMSARA_API_BASE}/fleet/vehicles",
                headers={
                    "Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}",
                },
                params={"limit": 1},
            )

            if response.status_code == 200:
                return {
                    "configured": True,
                    "connected": True,
                    "message": "Samsara API connected successfully",
                }
            elif response.status_code == 401:
                return {
                    "configured": True,
                    "connected": False,
                    "message": "Invalid API token - authentication failed",
                }
            else:
                return {
                    "configured": True,
                    "connected": False,
                    "message": f"API error: {response.status_code}",
                }
    except Exception as e:
        return {
            "configured": True,
            "connected": False,
            "message": f"Connection failed: {str(e)}",
        }
