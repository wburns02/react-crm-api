"""
Samsara Fleet Tracking API - Stub endpoints for frontend compatibility.

These endpoints return empty data until Samsara integration is configured.
"""
from fastapi import APIRouter
from typing import Optional
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import settings

router = APIRouter()


class VehicleLocation(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    speed: float
    heading: float
    last_updated: str
    status: str


class LocationHistoryPoint(BaseModel):
    latitude: float
    longitude: float
    timestamp: str
    speed: float


@router.get("/vehicles")
async def get_vehicles(current_user: CurrentUser) -> list[VehicleLocation]:
    """
    Get all vehicle locations from Samsara.
    Returns empty list if Samsara is not configured.
    """
    # Check if Samsara is configured
    if not settings.SAMSARA_API_TOKEN:
        return []

    # TODO: Implement actual Samsara API call
    return []


@router.get("/vehicles/{vehicle_id}/history")
async def get_vehicle_history(
    vehicle_id: str,
    current_user: CurrentUser,
    hours: int = 1,
) -> list[LocationHistoryPoint]:
    """
    Get vehicle location history.
    Returns empty list if Samsara is not configured.
    """
    if not settings.SAMSARA_API_TOKEN:
        return []

    # TODO: Implement actual Samsara API call
    return []
