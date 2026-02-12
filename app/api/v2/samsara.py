"""
Samsara Fleet Tracking API - Real-time vehicle locations from Samsara.

Integrates with Samsara's Fleet API to provide:
- Live vehicle locations with GPS coordinates
- Vehicle status (moving, idling, stopped, offline)
- Driver assignments
- Location history/breadcrumb trails
- Server-Sent Events (SSE) for real-time push updates

API Documentation: https://developers.samsara.com/reference
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
import httpx
import logging
import asyncio
import json

from app.api.deps import CurrentUser, get_current_user_ws
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Samsara API base URL
SAMSARA_API_BASE = "https://api.samsara.com"

# ── Vehicle cache & SSE infrastructure ──────────────────────────────────────

# In-memory vehicle store (updated by feed poller)
_vehicle_store: dict[str, "Vehicle"] = {}
_vehicle_store_lock = asyncio.Lock()
_last_update_time: datetime | None = None

# SSE client management
_sse_clients: set[asyncio.Queue] = set()
_sse_clients_lock = asyncio.Lock()

# Feed poller state
_feed_cursor: str | None = None
_feed_poller_task: asyncio.Task | None = None

# Legacy cache for /vehicles endpoint fallback
_vehicle_cache: dict = {"data": None, "expires": None}
_cache_lock = asyncio.Lock()
CACHE_TTL_SECONDS = 15


# ── Models ──────────────────────────────────────────────────────────────────

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


# ── Status logic ────────────────────────────────────────────────────────────

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


# ── Samsara API calls ──────────────────────────────────────────────────────

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

        # Check if response is a dict before accessing keys
        if not isinstance(vehicles_data, dict):
            logger.error(f"Unexpected Samsara vehicles response format: {type(vehicles_data).__name__}")
            return []

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

            # Check if response is a dict before accessing keys
            if not isinstance(stats_data, dict):
                logger.warning(f"Unexpected Samsara stats response format: {type(stats_data).__name__}, using empty data")
                stats_data = {"data": []}

        vehicles = []
        now = datetime.now(timezone.utc)

        for v in stats_data.get("data", []):
            if not isinstance(v, dict):
                continue
            vehicle_id = v.get("id", "")
            raw_gps = v.get("gps", {})

            # Samsara may return gps as a list of points or a single dict
            if isinstance(raw_gps, list):
                gps_data = raw_gps[-1] if raw_gps else {}
            elif isinstance(raw_gps, dict):
                gps_data = raw_gps
            else:
                gps_data = {}

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
                vehicles.append(
                    Vehicle(
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
                    )
                )

        return vehicles


# ── Feed poller (background task) ──────────────────────────────────────────

async def _poll_samsara_feed():
    """
    Background task that polls Samsara feed API every 5 seconds.
    Uses cursor-based pagination to only get changed data.
    Falls back to full fetch if feed API is unavailable.
    """
    global _feed_cursor, _last_update_time

    logger.info("Samsara feed poller started")

    while True:
        try:
            if not settings.SAMSARA_API_TOKEN:
                await asyncio.sleep(30)
                continue

            async with httpx.AsyncClient(timeout=15.0) as client:
                params = {"types": "gps"}
                if _feed_cursor:
                    params["after"] = _feed_cursor

                response = await client.get(
                    f"{SAMSARA_API_BASE}/fleet/vehicles/stats/feed",
                    headers={"Authorization": f"Bearer {settings.SAMSARA_API_TOKEN}"},
                    params=params,
                )

                if response.status_code == 200:
                    data = response.json()

                    # Check if response is a dict before accessing keys
                    if isinstance(data, dict):
                        new_cursor = data.get("pagination", {}).get("endCursor")
                        if new_cursor:
                            _feed_cursor = new_cursor

                        changed_vehicles = data.get("data", [])
                        if changed_vehicles:
                            await _process_feed_update(changed_vehicles)
                    else:
                        # Unexpected response format (list or other type)
                        logger.warning(f"Unexpected Samsara feed response format: {type(data).__name__}, falling back to full fetch")
                        await _do_full_fetch()
                elif response.status_code == 429:
                    # Rate limited - back off
                    logger.warning("Samsara API rate limited, backing off 30s")
                    await asyncio.sleep(30)
                    continue
                else:
                    # Feed endpoint may not be available - fall back to full fetch
                    logger.debug(f"Feed API returned {response.status_code}, using full fetch")
                    await _do_full_fetch()

        except httpx.RequestError as e:
            logger.warning(f"Samsara feed poll failed: {e}")
            # Try full fetch as fallback
            try:
                await _do_full_fetch()
            except Exception:
                pass
        except asyncio.CancelledError:
            logger.info("Samsara feed poller cancelled")
            return
        except Exception as e:
            logger.error(f"Unexpected error in feed poller: {e}")

        await asyncio.sleep(30)


async def _do_full_fetch():
    """Full fetch of all vehicles (fallback when feed API unavailable)."""
    global _last_update_time

    try:
        vehicles = await fetch_vehicles_from_samsara()
        now = datetime.now(timezone.utc)

        async with _vehicle_store_lock:
            _vehicle_store.clear()
            for v in vehicles:
                _vehicle_store[v.id] = v
            _last_update_time = now

        # Update legacy cache too
        async with _cache_lock:
            _vehicle_cache["data"] = vehicles
            _vehicle_cache["expires"] = now + timedelta(seconds=CACHE_TTL_SECONDS)

        # Broadcast to SSE clients
        await _broadcast_vehicles(vehicles)
        logger.debug(f"Full fetch: {len(vehicles)} vehicles")
    except Exception as e:
        logger.warning(f"Full fetch failed: {e}")


async def _process_feed_update(changed_data: list):
    """Process incremental feed update and broadcast changes."""
    global _last_update_time
    now = datetime.now(timezone.utc)
    updated_vehicles = []

    async with _vehicle_store_lock:
        for v in changed_data:
            # Samsara feed may return nested lists — skip non-dict items
            if not isinstance(v, dict):
                continue
            vehicle_id = v.get("id", "")
            raw_gps = v.get("gps", {})

            # Samsara feed may return gps as a list of points or a single dict
            if isinstance(raw_gps, list):
                # Take the most recent GPS point (last in the list)
                gps_data = raw_gps[-1] if raw_gps else {}
            elif isinstance(raw_gps, dict):
                gps_data = raw_gps
            else:
                gps_data = {}

            if not gps_data:
                continue

            updated_at_str = gps_data.get("time", now.isoformat())
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                time_since_update = (now - updated_at).total_seconds() / 60
            except Exception:
                time_since_update = 0

            speed_mph = gps_data.get("speedMilesPerHour", 0) or 0
            status = determine_vehicle_status(speed_mph, time_since_update)

            # Update existing or create new entry
            existing = _vehicle_store.get(vehicle_id)
            vehicle = Vehicle(
                id=vehicle_id,
                name=v.get("name", existing.name if existing else "Unknown Vehicle"),
                vin=existing.vin if existing else None,
                driver_id=existing.driver_id if existing else None,
                driver_name=existing.driver_name if existing else None,
                location=VehicleLocation(
                    lat=gps_data.get("latitude", 0),
                    lng=gps_data.get("longitude", 0),
                    heading=gps_data.get("headingDegrees", 0) or 0,
                    speed=round(speed_mph, 1),
                    updated_at=updated_at_str,
                ),
                status=status,
            )
            _vehicle_store[vehicle_id] = vehicle
            updated_vehicles.append(vehicle)

        _last_update_time = now

    if updated_vehicles:
        # Broadcast full vehicle list (all vehicles, not just changes)
        all_vehicles = list(_vehicle_store.values())
        await _broadcast_vehicles(all_vehicles)

        # Update legacy cache
        async with _cache_lock:
            _vehicle_cache["data"] = all_vehicles
            _vehicle_cache["expires"] = now + timedelta(seconds=CACHE_TTL_SECONDS)

        logger.debug(f"Feed update: {len(updated_vehicles)} vehicles changed")


# ── SSE broadcasting ───────────────────────────────────────────────────────

async def _broadcast_vehicles(vehicles: list[Vehicle]):
    """Send vehicle data to all connected SSE clients."""
    if not _sse_clients:
        return

    data = json.dumps([v.model_dump() for v in vehicles])
    message = f"event: vehicles\ndata: {data}\n\n"

    dead_clients = []
    async with _sse_clients_lock:
        for queue in _sse_clients:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead_clients.append(queue)

        for q in dead_clients:
            _sse_clients.discard(q)


def start_feed_poller():
    """Start the Samsara feed poller background task."""
    global _feed_poller_task
    if _feed_poller_task is not None:
        return
    _feed_poller_task = asyncio.create_task(_poll_samsara_feed())
    logger.info("Samsara feed poller background task created")


def stop_feed_poller():
    """Stop the Samsara feed poller background task."""
    global _feed_poller_task
    if _feed_poller_task:
        _feed_poller_task.cancel()
        _feed_poller_task = None
        logger.info("Samsara feed poller stopped")


# ── API Endpoints ──────────────────────────────────────────────────────────

@router.get("/vehicles")
async def get_vehicles(current_user: CurrentUser) -> list[Vehicle]:
    """
    Get all vehicle locations from Samsara.

    Calls Samsara Fleet API to get real-time vehicle positions.
    Uses feed poller cache if available, falls back to direct fetch.
    Returns empty list if Samsara is not configured.
    """
    if not settings.SAMSARA_API_TOKEN:
        logger.warning("SAMSARA_API_TOKEN not configured - returning empty vehicle list")
        return []

    # Try vehicle store first (populated by feed poller)
    async with _vehicle_store_lock:
        if _vehicle_store:
            return list(_vehicle_store.values())

    # Fall back to legacy cache / direct fetch
    global _vehicle_cache

    async with _cache_lock:
        now = datetime.now(timezone.utc)
        if _vehicle_cache["data"] is not None and _vehicle_cache["expires"] and _vehicle_cache["expires"] > now:
            logger.debug("Returning cached vehicle data")
            return _vehicle_cache["data"]

    try:
        vehicles = await fetch_vehicles_from_samsara()

        # Update both stores
        async with _vehicle_store_lock:
            for v in vehicles:
                _vehicle_store[v.id] = v

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


@router.get("/stream")
async def stream_vehicles(
    request: Request,
    token: Optional[str] = Query(None),
):
    """
    Server-Sent Events endpoint for real-time vehicle updates.

    Accepts auth via:
    - Bearer token in Authorization header (standard endpoints)
    - `token` query parameter (required for EventSource/SSE since it can't set headers)

    Streams vehicle location updates as they arrive from the Samsara feed poller.
    Sends heartbeat every 15 seconds to keep connection alive.
    """
    # EventSource can't set headers, so accept token from query param or header
    jwt_token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        jwt_token = auth_header[7:]
    elif token:
        jwt_token = token

    if not jwt_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await get_current_user_ws(jwt_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)

    async with _sse_clients_lock:
        _sse_clients.add(queue)
    logger.info(f"SSE client connected (total: {len(_sse_clients)})")

    async def event_generator():
        try:
            # Send initial data immediately
            async with _vehicle_store_lock:
                if _vehicle_store:
                    vehicles = list(_vehicle_store.values())
                    data = json.dumps([v.model_dump() for v in vehicles])
                    yield f"event: vehicles\ndata: {data}\n\n"

            # Send connection confirmation
            yield f"event: connected\ndata: {{\"status\": \"ok\", \"clients\": {len(_sse_clients)}}}\n\n"

            heartbeat_interval = 15
            while True:
                try:
                    # Wait for messages with timeout for heartbeat
                    message = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    yield message
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield f"event: heartbeat\ndata: {{\"time\": \"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"
                except asyncio.CancelledError:
                    break

                # Check if client disconnected
                if await request.is_disconnected():
                    break
        finally:
            async with _sse_clients_lock:
                _sse_clients.discard(queue)
            logger.info(f"SSE client disconnected (remaining: {len(_sse_clients)})")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
                        history.append(
                            LocationHistoryPoint(
                                lat=point.get("latitude", 0),
                                lng=point.get("longitude", 0),
                                timestamp=point.get("time", ""),
                                speed=round(point.get("speedMilesPerHour", 0) or 0, 1),
                            )
                        )

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
                    "sse_clients": len(_sse_clients),
                    "feed_poller_active": _feed_poller_task is not None and not _feed_poller_task.done(),
                    "cached_vehicles": len(_vehicle_store),
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
