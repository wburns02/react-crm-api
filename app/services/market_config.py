"""
Market configuration: area codes, centers, service area polygons, city lookup.

Static data — no database required. Markets are defined in MARKETS dict.
City lookup tables are pre-populated with lat/lng for instant geocoding.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_MARKET_SLUG = "nashville"

# Nashville service area polygons (approximate from Google Earth KML)
# Core: Columbia / Spring Hill / Maury County area
NASHVILLE_CORE_POLYGON = [
    (35.76, -86.93),   # North (Spring Hill)
    (35.73, -86.76),   # Northeast
    (35.60, -86.70),   # East
    (35.46, -86.78),   # Southeast
    (35.42, -86.95),   # South
    (35.45, -87.12),   # Southwest
    (35.55, -87.20),   # West
    (35.68, -87.15),   # Northwest
    (35.76, -86.93),   # Close polygon
]

# Extended: Broader Nashville metro down through Columbia
NASHVILLE_EXTENDED_POLYGON = [
    (36.32, -86.80),   # North (Nashville)
    (36.28, -86.30),   # Northeast
    (36.05, -86.05),   # East (Murfreesboro)
    (35.78, -86.25),   # Southeast
    (35.40, -86.55),   # South-southeast
    (35.30, -87.00),   # South
    (35.35, -87.30),   # Southwest
    (35.55, -87.45),   # West
    (35.85, -87.45),   # West-northwest
    (36.15, -87.25),   # Northwest (Dickson)
    (36.32, -87.05),   # North-northwest
    (36.32, -86.80),   # Close polygon
]

MARKETS: dict[str, dict] = {
    "nashville": {
        "slug": "nashville",
        "name": "Nashville / Middle TN",
        "area_codes": ["615", "629", "931"],
        "center": {"lat": 35.6145, "lng": -87.0353},
        "polygons": {
            "core": NASHVILLE_CORE_POLYGON,
            "extended": NASHVILLE_EXTENDED_POLYGON,
        },
    },
    "san_marcos": {
        "slug": "san_marcos",
        "name": "San Marcos / Central TX",
        "area_codes": ["737", "512"],
        "center": {"lat": 29.8833, "lng": -97.9414},
        "polygons": None,
    },
}

# Area code -> market slug reverse lookup
_AREA_CODE_MAP: dict[str, str] = {}
for slug, market in MARKETS.items():
    for code in market["area_codes"]:
        _AREA_CODE_MAP[code] = slug

# City lookup tables per market: {normalized_name: {lat, lng, name}}
CITY_TABLES: dict[str, dict[str, dict]] = {
    "nashville": {
        "columbia": {"lat": 35.6145, "lng": -87.0353, "name": "Columbia"},
        "spring hill": {"lat": 35.7512, "lng": -86.9300, "name": "Spring Hill"},
        "franklin": {"lat": 35.9260, "lng": -86.8689, "name": "Franklin"},
        "brentwood": {"lat": 36.0331, "lng": -86.7828, "name": "Brentwood"},
        "nashville": {"lat": 36.1627, "lng": -86.7816, "name": "Nashville"},
        "murfreesboro": {"lat": 35.8456, "lng": -86.3903, "name": "Murfreesboro"},
        "mt pleasant": {"lat": 35.5342, "lng": -87.2067, "name": "Mt Pleasant"},
        "mount pleasant": {"lat": 35.5342, "lng": -87.2067, "name": "Mt Pleasant"},
        "lewisburg": {"lat": 35.4495, "lng": -86.7889, "name": "Lewisburg"},
        "shelbyville": {"lat": 35.4834, "lng": -86.4603, "name": "Shelbyville"},
        "pulaski": {"lat": 35.1998, "lng": -87.0306, "name": "Pulaski"},
        "lawrenceburg": {"lat": 35.2423, "lng": -87.3347, "name": "Lawrenceburg"},
        "centerville": {"lat": 35.7790, "lng": -87.4667, "name": "Centerville"},
        "dickson": {"lat": 36.0770, "lng": -87.3878, "name": "Dickson"},
        "fairview": {"lat": 35.9820, "lng": -87.1214, "name": "Fairview"},
        "nolensville": {"lat": 35.9523, "lng": -86.6694, "name": "Nolensville"},
        "smyrna": {"lat": 35.9828, "lng": -86.5186, "name": "Smyrna"},
        "la vergne": {"lat": 36.0156, "lng": -86.5819, "name": "La Vergne"},
        "gallatin": {"lat": 36.3884, "lng": -86.4467, "name": "Gallatin"},
        "hendersonville": {"lat": 36.3048, "lng": -86.6200, "name": "Hendersonville"},
        "lebanon": {"lat": 36.2081, "lng": -86.2911, "name": "Lebanon"},
        "cookeville": {"lat": 36.1628, "lng": -85.5016, "name": "Cookeville"},
        "clarksville": {"lat": 36.5298, "lng": -87.3595, "name": "Clarksville"},
        "thompson station": {"lat": 35.8012, "lng": -86.9111, "name": "Thompson Station"},
        "chapel hill": {"lat": 35.6267, "lng": -86.6928, "name": "Chapel Hill"},
        "eagleville": {"lat": 35.7434, "lng": -86.6478, "name": "Eagleville"},
        "lascassas": {"lat": 35.9350, "lng": -86.2850, "name": "Lascassas"},
        "college grove": {"lat": 35.7695, "lng": -86.7339, "name": "College Grove"},
        "arrington": {"lat": 35.8650, "lng": -86.6850, "name": "Arrington"},
        "bon aqua": {"lat": 35.9200, "lng": -87.2700, "name": "Bon Aqua"},
        "santa fe": {"lat": 35.7200, "lng": -87.0500, "name": "Santa Fe"},
        "culleoka": {"lat": 35.4650, "lng": -87.0200, "name": "Culleoka"},
        "lynnville": {"lat": 35.3900, "lng": -87.0100, "name": "Lynnville"},
        "cornersville": {"lat": 35.3617, "lng": -86.8400, "name": "Cornersville"},
        "unionville": {"lat": 35.6100, "lng": -86.5900, "name": "Unionville"},
        "bell buckle": {"lat": 35.5887, "lng": -86.3584, "name": "Bell Buckle"},
        "wartrace": {"lat": 35.5256, "lng": -86.3389, "name": "Wartrace"},
        "manchester": {"lat": 35.4817, "lng": -86.0886, "name": "Manchester"},
        "tullahoma": {"lat": 35.3620, "lng": -86.2094, "name": "Tullahoma"},
        "winchester": {"lat": 35.1859, "lng": -86.1122, "name": "Winchester"},
        "fayetteville": {"lat": 35.1520, "lng": -86.5706, "name": "Fayetteville"},
        "hohenwald": {"lat": 35.5487, "lng": -87.5514, "name": "Hohenwald"},
        "linden": {"lat": 35.6173, "lng": -87.8392, "name": "Linden"},
        "waverly": {"lat": 36.0839, "lng": -87.7947, "name": "Waverly"},
        "white bluff": {"lat": 36.1073, "lng": -87.2200, "name": "White Bluff"},
        "kingston springs": {"lat": 36.0998, "lng": -87.1150, "name": "Kingston Springs"},
        "bellevue": {"lat": 36.0759, "lng": -86.9075, "name": "Bellevue"},
        "goodlettsville": {"lat": 36.3234, "lng": -86.7133, "name": "Goodlettsville"},
        "springfield": {"lat": 36.5092, "lng": -86.8850, "name": "Springfield"},
        "portland": {"lat": 36.5817, "lng": -86.5164, "name": "Portland"},
        "white house": {"lat": 36.4712, "lng": -86.6514, "name": "White House"},
        "greenbrier": {"lat": 36.4284, "lng": -86.8042, "name": "Greenbrier"},
        "ashland city": {"lat": 36.2748, "lng": -87.0642, "name": "Ashland City"},
        "charlotte": {"lat": 36.1773, "lng": -87.3397, "name": "Charlotte"},
        "antioch": {"lat": 36.0601, "lng": -86.6722, "name": "Antioch"},
        "hermitage": {"lat": 36.1740, "lng": -86.6120, "name": "Hermitage"},
        "mount juliet": {"lat": 36.2001, "lng": -86.5186, "name": "Mount Juliet"},
        "mt juliet": {"lat": 36.2001, "lng": -86.5186, "name": "Mount Juliet"},
        "donelson": {"lat": 36.1387, "lng": -86.6564, "name": "Donelson"},
        "madison": {"lat": 36.2570, "lng": -86.7075, "name": "Madison"},
        "old hickory": {"lat": 36.2376, "lng": -86.6480, "name": "Old Hickory"},
    },
    "san_marcos": {
        "san marcos": {"lat": 29.8833, "lng": -97.9414, "name": "San Marcos"},
        "kyle": {"lat": 29.9888, "lng": -97.8772, "name": "Kyle"},
        "buda": {"lat": 30.0852, "lng": -97.8411, "name": "Buda"},
        "wimberley": {"lat": 29.9977, "lng": -98.0986, "name": "Wimberley"},
        "dripping springs": {"lat": 30.1902, "lng": -98.0867, "name": "Dripping Springs"},
        "new braunfels": {"lat": 29.7030, "lng": -98.1245, "name": "New Braunfels"},
        "seguin": {"lat": 29.5688, "lng": -97.9647, "name": "Seguin"},
        "lockhart": {"lat": 29.8849, "lng": -97.6700, "name": "Lockhart"},
        "luling": {"lat": 29.6808, "lng": -97.6475, "name": "Luling"},
        "austin": {"lat": 30.2672, "lng": -97.7431, "name": "Austin"},
    },
}


def get_market_by_area_code(area_code: str) -> dict:
    """Look up market by phone area code. Returns default market for unknown codes."""
    slug = _AREA_CODE_MAP.get(area_code, DEFAULT_MARKET_SLUG)
    return MARKETS[slug]


def get_market_by_slug(slug: str) -> Optional[dict]:
    """Look up market by slug."""
    return MARKETS.get(slug)


def lookup_city(city_name: str, market_slug: str) -> Optional[dict]:
    """Look up a city in the market's city table. Returns {lat, lng, name} or None."""
    table = CITY_TABLES.get(market_slug, {})
    return table.get(city_name.lower().strip())


def point_in_polygon(lat: float, lng: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon test. Polygon is list of (lat, lng) tuples."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def get_zone(lat: float, lng: float, market_slug: str) -> str:
    """Determine which service zone a point falls in: 'core', 'extended', or 'outside'."""
    market = MARKETS.get(market_slug)
    if not market or not market.get("polygons"):
        return "outside"
    polygons = market["polygons"]
    if polygons.get("core") and point_in_polygon(lat, lng, polygons["core"]):
        return "core"
    if polygons.get("extended") and point_in_polygon(lat, lng, polygons["extended"]):
        return "extended"
    return "outside"
