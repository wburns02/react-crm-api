"""
Tank Size Estimation API - PUBLIC endpoint (no auth required).

Estimates septic tank size from a Nashville-area address using property records.
"""

import logging
import re
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, text, func

from app.api.deps import DbSession
from app.models.property_lookup import PropertyLookup

logger = logging.getLogger(__name__)

router = APIRouter()


class TankEstimateResponse(BaseModel):
    """Response from tank size estimation."""
    estimated_gallons: int
    confidence: str  # high, medium, low
    source: str  # sqft, acres_value, system_type, default
    message: str  # Human-friendly message
    overage_gallons: int  # Gallons over 1,000 included
    estimated_overage_cost: float  # At $0.45/gal
    estimated_total: float  # $625 base + overage
    address_matched: Optional[str] = None
    county: Optional[str] = None
    sqft: Optional[int] = None


class TankEstimateStats(BaseModel):
    """Stats about the property lookup database."""
    total_properties: int
    counties: list[str]


# Nashville booking pricing constants
BASE_PRICE = 625.0
INCLUDED_GALLONS = 1000
OVERAGE_RATE = 0.45


def _normalize_address(address: str) -> str:
    """Normalize address for matching."""
    addr = address.upper().strip()
    # Remove common suffixes and abbreviations for better matching
    replacements = {
        " STREET": " ST",
        " DRIVE": " DR",
        " ROAD": " RD",
        " AVENUE": " AVE",
        " BOULEVARD": " BLVD",
        " LANE": " LN",
        " COURT": " CT",
        " CIRCLE": " CIR",
        " PLACE": " PL",
        " PIKE": " PK",
        " HIGHWAY": " HWY",
        " PARKWAY": " PKWY",
        ",": "",
        ".": "",
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)
    # Collapse multiple spaces
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def _extract_street_for_matching(address: str) -> str:
    """Extract just the street number + name from a full address for fuzzy matching."""
    addr = _normalize_address(address)
    # Remove city, state, zip from end (e.g. "123 MAIN ST NASHVILLE TN 37201")
    # Try to find state abbreviation and cut there
    tn_match = re.search(r"\s+TN\s*\d{0,5}\s*$", addr)
    if tn_match:
        addr = addr[:tn_match.start()].strip()
    # Remove trailing city names
    cities = [
        "NASHVILLE", "FRANKLIN", "MURFREESBORO", "BRENTWOOD", "ANTIOCH",
        "HERMITAGE", "MADISON", "GOODLETTSVILLE", "MT JULIET", "MOUNT JULIET",
        "LEBANON", "GALLATIN", "SPRING HILL", "SMYRNA", "LA VERGNE",
        "LAVERGNE", "HENDERSONVILLE", "NOLENSVILLE", "OLD HICKORY",
        "JOELTON", "WHITES CREEK", "CHRISTIANA", "ROCKVALE",
    ]
    for city in cities:
        if addr.endswith(f" {city}"):
            addr = addr[: -(len(city) + 1)].strip()
            break
    return addr


@router.get("/estimate-tank", response_model=TankEstimateResponse)
async def estimate_tank_size(
    db: DbSession,
    address: str = Query(..., min_length=3, description="Property address to look up"),
) -> TankEstimateResponse:
    """
    Estimate septic tank size from a Nashville-area address.

    PUBLIC endpoint - no authentication required.

    Uses property records (sqft, acres, improvement value, system type) to estimate
    the likely tank size. Returns estimated cost including any overage.
    """
    street = _extract_street_for_matching(address)
    normalized = _normalize_address(address)

    if len(street) < 3:
        return _default_estimate()

    # Strategy 1: Exact normalized address match
    result = await db.execute(
        select(PropertyLookup)
        .where(PropertyLookup.address_normalized == street)
        .limit(1)
    )
    match = result.scalars().first()

    # Strategy 2: Try with full normalized address
    if not match:
        result = await db.execute(
            select(PropertyLookup)
            .where(PropertyLookup.address_normalized == normalized)
            .limit(1)
        )
        match = result.scalars().first()

    # Strategy 3: Trigram fuzzy match (requires pg_trgm extension)
    if not match:
        try:
            result = await db.execute(
                select(PropertyLookup)
                .where(
                    func.similarity(PropertyLookup.address_normalized, street) > 0.4
                )
                .order_by(
                    func.similarity(PropertyLookup.address_normalized, street).desc()
                )
                .limit(1)
            )
            match = result.scalars().first()
        except Exception as e:
            logger.warning(f"Trigram search failed (pg_trgm may not be available): {e}")

    # Strategy 4: LIKE prefix match on street number + first word
    if not match and street:
        parts = street.split()
        if len(parts) >= 2 and parts[0].isdigit():
            prefix = f"{parts[0]} {parts[1]}%"
            result = await db.execute(
                select(PropertyLookup)
                .where(PropertyLookup.address_normalized.like(prefix))
                .limit(1)
            )
            match = result.scalars().first()

    if not match:
        return _default_estimate()

    # Build response from match
    gallons = match.estimated_tank_gallons
    overage = max(0, gallons - INCLUDED_GALLONS)
    overage_cost = round(overage * OVERAGE_RATE, 2)
    total = BASE_PRICE + overage_cost

    if overage > 0:
        message = (
            f"Based on your property records, your estimated tank size is "
            f"~{gallons:,} gallons. Estimated overage: {overage:,} gal "
            f"(~${overage_cost:.0f} additional)."
        )
    else:
        message = (
            f"Based on your property records, your estimated tank size is "
            f"~{gallons:,} gallons — no overage expected!"
        )

    return TankEstimateResponse(
        estimated_gallons=gallons,
        confidence=match.estimation_confidence or "medium",
        source=match.estimation_source or "default",
        message=message,
        overage_gallons=overage,
        estimated_overage_cost=overage_cost,
        estimated_total=total,
        address_matched=match.address_raw or match.address_normalized,
        county=match.county,
        sqft=match.sqft,
    )


@router.get("/estimate-tank/stats", response_model=TankEstimateStats)
async def tank_estimate_stats(db: DbSession) -> TankEstimateStats:
    """Get stats about the property lookup database. Public endpoint."""
    count_result = await db.execute(
        select(func.count()).select_from(PropertyLookup)
    )
    total = count_result.scalar() or 0

    county_result = await db.execute(
        select(PropertyLookup.county).distinct()
    )
    counties = [r[0] for r in county_result.all()]

    return TankEstimateStats(total_properties=total, counties=sorted(counties))


def _default_estimate() -> TankEstimateResponse:
    """Return default estimate when no property match is found."""
    return TankEstimateResponse(
        estimated_gallons=1000,
        confidence="low",
        source="default",
        message=(
            "We couldn't find your property in our records, but most Nashville-area "
            "homes have a 1,000-gallon tank — no overage expected!"
        ),
        overage_gallons=0,
        estimated_overage_cost=0.0,
        estimated_total=BASE_PRICE,
    )
