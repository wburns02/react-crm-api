"""
Service Markets API — read-only for now, admin can view market configs.
"""

from fastapi import APIRouter, HTTPException
from app.api.deps import CurrentUser
from app.services.market_config import MARKETS, CITY_TABLES
from app.services.location_extractor import haversine_distance, estimate_drive_minutes
from app.services.market_config import get_zone

router = APIRouter(prefix="/service-markets", tags=["service-markets"])


@router.get("")
async def list_markets(current_user: CurrentUser):
    """List all configured service markets."""
    result = []
    for slug, market in MARKETS.items():
        result.append({
            "slug": market["slug"],
            "name": market["name"],
            "area_codes": market["area_codes"],
            "center": market["center"],
            "has_polygons": market.get("polygons") is not None,
            "city_count": len(CITY_TABLES.get(slug, {})),
        })
    return result


@router.get("/{slug}")
async def get_market(slug: str, current_user: CurrentUser):
    """Get full market config including polygons."""
    market = MARKETS.get(slug)
    if not market:
        raise HTTPException(status_code=404, detail=f"Market '{slug}' not found")
    return {
        **market,
        "cities": list(CITY_TABLES.get(slug, {}).values()),
    }


@router.get("/{slug}/zone-check")
async def check_zone(slug: str, lat: float, lng: float, current_user: CurrentUser):
    """Check which zone a coordinate falls in for a given market."""
    market = MARKETS.get(slug)
    if not market:
        raise HTTPException(status_code=404, detail=f"Market '{slug}' not found")

    zone = get_zone(lat, lng, slug)
    center = market["center"]
    distance = haversine_distance(center["lat"], center["lng"], lat, lng)
    drive_minutes = estimate_drive_minutes(distance)

    return {
        "zone": zone,
        "drive_minutes": drive_minutes,
        "distance_miles": round(distance, 1),
        "market": market["name"],
    }
