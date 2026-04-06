"""
Location extraction from call transcripts.

Parses transcript text for addresses, city names, and street references.
Geocodes via local city lookup (instant) or Nominatim (free, OSM).
Determines service zone and estimates drive time.
Deduplicates to avoid flooding the frontend with repeated events.
"""

import re
import math
import logging
import httpx
from typing import Optional

from app.services.market_config import (
    lookup_city,
    get_zone,
    get_market_by_slug,
)

logger = logging.getLogger(__name__)

# Columbia, TN base coordinates
BASE_LAT = 35.6145
BASE_LNG = -87.0353

# Dedup threshold: must be >0.5 miles apart to count as a new location
DEDUP_DISTANCE_MILES = 0.5

# Nominatim base URL (free, OSM-based geocoding)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "MacServicePlatform/1.0"}

# Regex patterns
ADDRESS_PATTERN = re.compile(
    r"(\d{1,5})\s+"                              # house number
    r"([\w\s]{2,30})"                             # street name
    r"\b(pike|road|rd|drive|dr|lane|ln|street|st|avenue|ave|boulevard|blvd|way|court|ct|circle|cir|highway|hwy)\b",
    re.IGNORECASE,
)

STREET_MENTION_PATTERN = re.compile(
    r"\bon\s+"                                    # "on"
    r"([\w\s]{2,30})"                             # street name
    r"\b(pike|road|rd|drive|dr|lane|ln|street|st|avenue|ave|boulevard|blvd|highway|hwy)\b",
    re.IGNORECASE,
)

SERVICE_QUESTION_PATTERN = re.compile(
    r"(?:do you|can you|you guys)\s+(?:service|cover|come to|go to|work in)\s+(.+?)(?:\?|$)",
    re.IGNORECASE,
)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in miles."""
    R = 3959  # Earth radius in miles
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def estimate_drive_minutes(distance_miles: float) -> int:
    """Estimate drive time at 35 mph average."""
    return round(distance_miles / 35.0 * 60)


class LocationExtractor:
    """
    Extracts location from transcript text for a single call session.

    Usage:
        extractor = LocationExtractor(call_sid="CA123", market_slug="nashville")
        result = extractor.extract_location_from_text("I'm in Spring Hill")
        if result:
            # broadcast to frontend
    """

    def __init__(self, call_sid: str, market_slug: str):
        self.call_sid = call_sid
        self.market_slug = market_slug
        self.market = get_market_by_slug(market_slug)
        self.last_location: Optional[dict] = None

    def extract_location_from_text(self, text: str) -> Optional[dict]:
        """
        Parse transcript text for location signals. Returns location dict or None.

        Tries in order: full address, street mention, "do you service" pattern, city name.
        Returns None if no location found or if deduped.
        """
        result = None

        # 1. Full address ("1205 Hampshire Pike")
        addr_match = ADDRESS_PATTERN.search(text)
        if addr_match:
            number = addr_match.group(1)
            street = addr_match.group(2).strip()
            suffix = addr_match.group(3)
            address_text = f"{number} {street} {suffix}".title()
            # Try to find city context in the same text
            city_result = self._find_city_in_text(text)
            if city_result:
                result = {
                    **city_result,
                    "address_text": f"{address_text}, {city_result['address_text']}",
                    "confidence": 0.9,
                    "source": "transcript",
                }
            else:
                # Address without city — try geocoding the street in market context
                result = self._geocode_address(address_text)
                if result:
                    result["confidence"] = 0.8
            if result:
                return self._dedup_and_enrich(result, text)

        # 2. Street mention ("on Bear Creek Pike")
        street_match = STREET_MENTION_PATTERN.search(text)
        if street_match:
            street = street_match.group(1).strip()
            suffix = street_match.group(2)
            address_text = f"{street} {suffix}".title()
            result = self._geocode_address(address_text)
            if result:
                result["confidence"] = 0.8
                return self._dedup_and_enrich(result, text)

        # 3. "Do you service [City]?" pattern
        svc_match = SERVICE_QUESTION_PATTERN.search(text)
        if svc_match:
            candidate = svc_match.group(1).strip().rstrip("?.,!")
            city_result = lookup_city(candidate, self.market_slug)
            if city_result:
                result = {
                    "lat": city_result["lat"],
                    "lng": city_result["lng"],
                    "address_text": city_result["name"],
                    "confidence": 0.7,
                    "source": "transcript",
                }
                return self._dedup_and_enrich(result, text)

        # 4. City name anywhere in text
        city_result = self._find_city_in_text(text)
        if city_result:
            result = {
                **city_result,
                "confidence": 0.7,
                "source": "transcript",
            }
            return self._dedup_and_enrich(result, text)

        return None

    def _find_city_in_text(self, text: str) -> Optional[dict]:
        """Scan text for known city names in this market."""
        from app.services.market_config import CITY_TABLES

        table = CITY_TABLES.get(self.market_slug, {})
        text_lower = text.lower()
        best_match = None
        best_len = 0

        for city_key, city_data in table.items():
            if city_key in text_lower and len(city_key) > best_len:
                best_match = city_data
                best_len = len(city_key)

        if best_match:
            return {
                "lat": best_match["lat"],
                "lng": best_match["lng"],
                "address_text": best_match["name"],
                "source": "transcript",
            }
        return None

    def _geocode_address(self, address_text: str) -> Optional[dict]:
        """Geocode an address via Nominatim. Synchronous fallback for transcript parsing."""
        if not self.market:
            return None
        center = self.market["center"]
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(
                    NOMINATIM_URL,
                    params={
                        "q": f"{address_text}, {self.market['name']}",
                        "format": "json",
                        "limit": 1,
                        "viewbox": f"{center['lng']-1},{center['lat']+1},{center['lng']+1},{center['lat']-1}",
                        "bounded": 1,
                    },
                    headers=NOMINATIM_HEADERS,
                )
                if resp.status_code == 200 and resp.json():
                    data = resp.json()[0]
                    return {
                        "lat": float(data["lat"]),
                        "lng": float(data["lon"]),
                        "address_text": address_text,
                        "source": "transcript",
                    }
        except Exception as e:
            logger.warning("Nominatim geocode failed for '%s': %s", address_text, e)
        return None

    def _dedup_and_enrich(self, result: dict, transcript_text: str) -> Optional[dict]:
        """Check dedup, add zone + drive time, update last_location."""
        lat, lng = result["lat"], result["lng"]
        confidence = result.get("confidence", 0.5)

        if self.last_location:
            dist = haversine_distance(
                self.last_location["lat"],
                self.last_location["lng"],
                lat,
                lng,
            )
            if dist < DEDUP_DISTANCE_MILES and confidence <= self.last_location.get("confidence", 0):
                return None  # Same place, same or lower confidence

        zone = get_zone(lat, lng, self.market_slug)
        base = self.market["center"] if self.market else {"lat": BASE_LAT, "lng": BASE_LNG}
        distance = haversine_distance(base["lat"], base["lng"], lat, lng)
        drive_minutes = estimate_drive_minutes(distance)

        enriched = {
            "lat": lat,
            "lng": lng,
            "source": result.get("source", "transcript"),
            "address_text": result["address_text"],
            "zone": zone,
            "drive_minutes": drive_minutes,
            "customer_id": result.get("customer_id"),
            "confidence": confidence,
            "transcript_excerpt": transcript_text.strip()[:120],
        }
        self.last_location = enriched
        return enriched
