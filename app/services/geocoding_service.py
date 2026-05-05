"""Geocoding service: free Nominatim address -> lat/lng lookups.

Used by customer create/update to auto-populate coordinates when an address
is set but lat/lng are not. Best-effort: returns None on any error.
"""
import logging
import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "MacServicePlatform/1.0 (will@macseptic.com)"}
TIMEOUT_SEC = 5.0


async def geocode_address(
    address_line1: str | None,
    city: str | None,
    state: str | None,
    postal_code: str | None = None,
) -> tuple[float, float] | None:
    """Geocode a single address. Returns (lat, lng) or None on failure.

    Best-effort: any HTTP / parse / network error returns None silently
    (caller should log if useful) so we never break a customer save flow.
    """
    if not (address_line1 and city and state):
        return None

    parts = [address_line1, city, state]
    if postal_code:
        parts.append(postal_code)
    query = ", ".join(p.strip() for p in parts if p)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
            r = await client.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers=NOMINATIM_HEADERS,
            )
            if r.status_code != 200:
                logger.warning(f"Geocode HTTP {r.status_code} for {query!r}")
                return None
            rows = r.json()
            if rows:
                return float(rows[0]["lat"]), float(rows[0]["lon"])
    except Exception as e:
        logger.warning(f"Geocode failed for {query!r}: {e}")
    return None
