"""
Samsara Fleet Tracking API - Real-time vehicle locations from Samsara.

Integrates with Samsara's Fleet API to provide:
- Live vehicle locations with GPS coordinates
- Vehicle status (moving, idling, stopped, offline)
- Driver assignments
- Location history/breadcrumb trails

API Documentation: https://developers.samsara.com/reference
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import httpx
import logging
import asyncio

from app.api.deps import CurrentUser
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Samsara API base URL
SAMSARA_API_BASE = "https://api.samsara.com"

# Simple in-memory cache with TTL
_vehicle_cache: dict = {"data": None, "expires": None}
_cache_lock = asyncio.Lock()
CACHE_TTL_SECONDS = 15  # Cache for 15 seconds to avoid rate limits


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


def determine_vehicle_status(speed_mph: float, time_since_update_minutes: float) -> str:
    """
    Determine vehicle status based on speed and time since last update.

    - moving: speed > 3 mph
    - idling: speed <= 3 mph and speed > 0
    - stopped: speed = 0
    - offline: no update in 10+ minutes
    """
    if time_since_update_minutes > 10:
        return "offline"
    if speed_mph > 3:
        return "moving"
    if speed_mph > 0:
        return "idling"
    return "stopped"


async def fetch_vehicles_from_samsara() -> list[Vehicle]:
    """
    Fetch vehicles with GPS data from Samsara API.
    Uses /fleet/vehicles/stats?types=gps for real-time locations.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        # First, get all vehicles
        vehicles_response = await client.get(
            f"{SAMSARA_API_BASE}/fleet/vehicles",
            headers={"Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}"},
        )

        if vehicles_response.status_code == 401:
            logger.error("Samsara API authentication failed - check SAMSARA_API_TOKEN")
            raise HTTPException(status_code=503, detail="Fleet tracking service authentication failed")

        if vehicles_response.status_code != 200:
            logger.error(f"Samsara vehicles API error: {vehicles_response.status_code} - {vehicles_response.text}")
            raise HTTPException(status_code=503, detail="Fleet tracking service unavailable")

        vehicles_data = vehicles_response.json()
        vehicle_info = {v["id"]: v for v in vehicles_data.get("data", [])}

        # Then get GPS stats for all vehicles
        stats_response = await client.get(
            f"{SAMSARA_API_BASE}/fleet/vehicles/stats",
            headers={"Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}"},
            params={"types": "gps"},
        )

        if stats_response.status_code != 200:
            logger.warning(f"Samsara stats API error: {stats_response.status_code}")
            # Fall back to vehicle list without GPS
            stats_data = {"data": []}
        else:
            stats_data = stats_response.json()

        vehicles = []
        now = datetime.now(timezone.utc)

        for v in stats_data.get("data", []):
            vehicle_id = v.get("id", "")
            gps_data = v.get("gps", {})

            # Get additional vehicle info
            info = vehicle_info.get(vehicle_id, {})

            # Parse the timestamp
            updated_at_str = gps_data.get("time", now.isoformat())
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                time_since_update = (now - updated_at).total_seconds() / 60
            except Exception:
                time_since_update = 0

            # Speed is already in mph from Samsara stats endpoint
            speed_mph = gps_data.get("speedMilesPerHour", 0) or 0

            # Determine status
            status = determine_vehicle_status(speed_mph, time_since_update)

            vehicle = Vehicle(
                id=vehicle_id,
                name=v.get("name", info.get("name", "Unknown Vehicle")),
                vin=info.get("vin"),
                driver_id=None,  # Driver assignment requires separate API call
                driver_name=None,
                location=VehicleLocation(
                    lat=gps_data.get("latitude", 0),
                    lng=gps_data.get("longitude", 0),
                    heading=gps_data.get("headingDegrees", 0) or 0,
                    speed=round(speed_mph, 1),
                    updated_at=updated_at_str,
                ),
                status=status,
            )
            vehicles.append(vehicle)

        # If no GPS data but we have vehicles, add them with offline status
        if not vehicles and vehicle_info:
            for vid, info in vehicle_info.items():
                vehicles.append(Vehicle(
                    id=vid,
                    name=info.get("name", "Unknown Vehicle"),
                    vin=info.get("vin"),
                    driver_id=None,
                    driver_name=None,
                    location=VehicleLocation(
                        lat=0,
                        lng=0,
                        heading=0,
                        speed=0,
                        updated_at=now.isoformat(),
                    ),
                    status="offline",
                ))

        return vehicles


@router.get("/vehicles")
async def get_vehicles(current_user: CurrentUser) -> list[Vehicle]:
    """
    Get all vehicle locations from Samsara.

    Calls Samsara Fleet API to get real-time vehicle positions.
    Uses caching to avoid rate limits (15 second TTL).
    Returns empty list if Samsara is not configured.
    """
    if not settings.SAMSARA_API_TOKEN:
        logger.warning("SAMSARA_API_TOKEN not configured - returning empty vehicle list")
        return []

    global _vehicle_cache

    # Check cache first
    async with _cache_lock:
        now = datetime.now(timezone.utc)
        if _vehicle_cache["data"] is not None and _vehicle_cache["expires"] and _vehicle_cache["expires"] > now:
            logger.debug("Returning cached vehicle data")
            return _vehicle_cache["data"]

    try:
        vehicles = await fetch_vehicles_from_samsara()

        # Update cache
        async with _cache_lock:
            _vehicle_cache["data"] = vehicles
            _vehicle_cache["expires"] = datetime.now(timezone.utc) + timedelta(seconds=CACHE_TTL_SECONDS)

        logger.info(f"Retrieved {len(vehicles)} vehicles from Samsara")
        return vehicles

    except HTTPException:
        raise
    except httpx.RequestError as e:
        logger.error(f"Samsara API request failed: {e}")
        raise HTTPException(status_code=503, detail="Fleet tracking service connection failed")
    except Exception as e:
        logger.error(f"Unexpected error fetching vehicles: {e}")
        raise HTTPException(status_code=503, detail="Fleet tracking service error")


@router.get("/vehicles/{vehicle_id}/history")
async def get_vehicle_history(
    vehicle_id: str,
    current_user: CurrentUser,
    hours: int = 1,
) -> list[LocationHistoryPoint]:
    """
    Get vehicle location history from Samsara.

    Returns GPS breadcrumb trail for the specified time period.
    Uses /fleet/vehicles/stats/history?types=gps endpoint.
    """
    if not settings.SAMSARA_API_TOKEN:
        return []

    try:
        # Calculate time range
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{SAMSARA_API_BASE}/fleet/vehicles/stats/history",
                headers={
                    "Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}",
                },
                params={
                    "types": "gps",
                    "vehicleIds": vehicle_id,
                    "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )

            if response.status_code != 200:
                logger.warning(f"Failed to get vehicle history: {response.status_code} - {response.text}")
                return []

            data = response.json()
            history = []

            # Response structure: data[].gps[] array
            for vehicle_data in data.get("data", []):
                if vehicle_data.get("id") == vehicle_id:
                    for point in vehicle_data.get("gps", []):
                        history.append(LocationHistoryPoint(
                            lat=point.get("latitude", 0),
                            lng=point.get("longitude", 0),
                            timestamp=point.get("time", ""),
                            speed=round(point.get("speedMilesPerHour", 0) or 0, 1),
                        ))

            logger.info(f"Retrieved {len(history)} history points for vehicle {vehicle_id}")
            return history

    except httpx.RequestError as e:
        logger.error(f"Samsara history request failed: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching vehicle history: {e}")
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
            "token_prefix": None,
        }

    # Show first 10 chars of token for debugging (safe - not the full token)
    token_prefix = settings.SAMSARA_API_TOKEN[:10] + "..." if len(settings.SAMSARA_API_TOKEN) > 10 else "too_short"

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
                data = response.json()
                vehicle_count = len(data.get("data", []))
                return {
                    "configured": True,
                    "connected": True,
                    "message": "Samsara API connected successfully",
                    "token_prefix": token_prefix,
                    "vehicle_count": vehicle_count,
                }
            elif response.status_code == 401:
                return {
                    "configured": True,
                    "connected": False,
                    "message": "Invalid API token - authentication failed",
                    "token_prefix": token_prefix,
                    "samsara_error": response.text[:200] if response.text else None,
                }
            else:
                return {
                    "configured": True,
                    "connected": False,
                    "message": f"API error: {response.status_code}",
                    "token_prefix": token_prefix,
                    "samsara_error": response.text[:200] if response.text else None,
                }
    except Exception as e:
        return {
            "configured": True,
            "connected": False,
            "message": f"Connection failed: {str(e)}",
            "token_prefix": token_prefix,
        }
