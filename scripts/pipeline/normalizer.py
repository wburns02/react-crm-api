"""Address, system-type, and date normalization.

Consolidates the parsing logic that was duplicated across 8 ETL scripts.
Imports the canonical address normalization from app/utils/.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime

# Make the app package importable from scripts/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.utils.address_normalization import (  # noqa: E402
    compute_address_hash,
    normalize_address,
    normalize_county,
    normalize_owner_name,
    normalize_state,
)

# Re-export for convenience
__all__ = [
    "normalize_address",
    "normalize_county",
    "normalize_state",
    "normalize_owner_name",
    "compute_address_hash",
    "parse_date",
    "parse_datetime",
    "extract_system_type_keyword",
    "KEYWORD_SYSTEM_TYPES",
    "WORK_TYPE_MAP",
]

# ── Date Parsing ──────────────────────────────────────────────────────

# Superset of all date formats found across all ETL scripts
ALL_DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%B %d, %Y",
    "%b %d, %Y",
]


def parse_date(date_str: str | None) -> str | None:
    """Parse a date string to YYYY-MM-DD, trying all known formats."""
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    for fmt in ALL_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_datetime(dt_str: str | None) -> str | None:
    """Parse a datetime string to ISO format."""
    if not dt_str or not dt_str.strip():
        return None
    s = dt_str.strip()
    for fmt in ALL_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            continue
    return None


# ── System Type Keyword Matching ──────────────────────────────────────

# Unified keyword list (superset of all scripts)
KEYWORD_SYSTEM_TYPES: list[tuple[str, str]] = [
    ("aerobic", "Aerobic Treatment Unit"),
    ("conventional", "Conventional Septic"),
    ("mound", "Mound System"),
    ("drip", "Drip Irrigation"),
    ("spray", "Spray Distribution"),
    ("surface application", "Surface Application"),
    ("surface irrigation", "Surface Application"),
    ("low pressure", "Low Pressure Dosing"),
    ("lpd", "Low Pressure Dosing"),
    ("evapotranspiration", "Evapotranspiration"),
    ("leaching chamber", "Leaching Chambers"),
    ("cluster", "Cluster System"),
    ("cesspool", "Cesspool"),
    ("grease", "Grease Trap"),
    ("holding", "Holding Tank"),
    ("standard subsurface", "Standard Septic"),
    ("standard trench", "Standard Septic"),
    ("septic", "Standard Septic"),
]


def extract_system_type_keyword(text: str | None) -> str | None:
    """Match text against keyword list, return standardized type."""
    if not text:
        return None
    lower = text.lower()
    for keyword, system_type in KEYWORD_SYSTEM_TYPES:
        if keyword in lower:
            return system_type
    return None


# ── MGO Work-Type Mapping (30+ entries) ───────────────────────────────

WORK_TYPE_MAP: dict[str, str] = {
    "Aerobic": "Aerobic Treatment Unit",
    "Aerobic [SFR]": "Aerobic Treatment Unit",
    "Aerobic - Non SFR": "Aerobic Treatment Unit",
    "Aerobic Treatment Unit": "Aerobic Treatment Unit",
    "Conventional": "Conventional Septic",
    "Conventional [SFR]": "Conventional Septic",
    "Conventional - Non SFR": "Conventional Septic",
    "Standard Subsurface": "Standard Septic",
    "Standard Subsurface [SFR]": "Standard Septic",
    "Standard": "Standard Septic",
    "Mound": "Mound System",
    "Mound [SFR]": "Mound System",
    "Mound System": "Mound System",
    "Drip": "Drip Irrigation",
    "Drip [SFR]": "Drip Irrigation",
    "Drip Irrigation": "Drip Irrigation",
    "Low Pressure Dosing": "Low Pressure Dosing",
    "Low Pressure Dosing [SFR]": "Low Pressure Dosing",
    "Low Pressure Pipe [SFR]": "Low Pressure Dosing",
    "LPD": "Low Pressure Dosing",
    "Spray": "Spray Distribution",
    "Spray [SFR]": "Spray Distribution",
    "Spray Distribution": "Spray Distribution",
    "Surface Application": "Surface Application",
    "Surface Application [SFR]": "Surface Application",
    "Surface Irrigation": "Surface Application",
    "Evapotranspiration": "Evapotranspiration",
    "Evapotranspiration [SFR]": "Evapotranspiration",
    "ET [SFR]": "Evapotranspiration",
    "Leaching Chambers": "Leaching Chambers",
    "Cluster": "Cluster System",
    "Cluster [SFR]": "Cluster System",
    "Holding Tank": "Holding Tank",
    "Grease Trap": "Grease Trap",
    "Cesspool": "Cesspool",
}

# Work types that are NOT system types (skip these)
SKIP_WORK_TYPES = {
    "Subdivision",
    "Routine Maintenance",
    "Maintenance",
    "Inspection",
    "Plan Review",
    "Amendment",
    "Renewal",
    "Permit Closure",
    "Extension",
    "Variance",
    "Transfer",
    "Complaint",
    "Abandonment",
    "Exemption",
}


def map_work_type(work_type: str | None) -> str | None:
    """Map MGO work_type field to standard system type."""
    if not work_type:
        return None
    wt = work_type.strip()
    if wt in SKIP_WORK_TYPES:
        return None
    if wt in WORK_TYPE_MAP:
        return WORK_TYPE_MAP[wt]
    # Try keyword fallback
    return extract_system_type_keyword(wt)


# ── MGO Description Regex ─────────────────────────────────────────────

RE_SYSTEM_TYPE = re.compile(
    r"This\s+(.+?)\s+(?:OSSF\s+)?is\s+designed\s+to\s+treat",
    re.IGNORECASE,
)
RE_GPD = re.compile(r"(\d{2,5})\s+gallons\s+per\s+day", re.IGNORECASE)
RE_BEDROOMS = re.compile(r"(\d{1,2})-bedroom", re.IGNORECASE)
RE_SQFT = re.compile(r"([\d,]+)\s*sq\.?\s*ft", re.IGNORECASE)
RE_MAINTENANCE = re.compile(
    r"maintenance\s+(?:and\s+monitoring\s+)?contract\s+is\s+required",
    re.IGNORECASE,
)
RE_CHLORINE = re.compile(
    r"chlorine\s+disinfection\s+is\s+required", re.IGNORECASE
)
RE_RENEWAL = re.compile(
    r"permit\s+must\s+be\s+renewed\s+every\s+(\w+)\s+years?",
    re.IGNORECASE,
)

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}

# Compound system type normalization
_COMPOUND_PARTS = {
    "aerobic": "Aerobic Treatment Unit",
    "drip": "Drip Irrigation",
    "spray": "Spray Distribution",
    "surface": "Surface Application",
    "mound": "Mound System",
    "conventional": "Conventional Septic",
    "low pressure": "Low Pressure Dosing",
    "lpd": "Low Pressure Dosing",
}


def _normalize_description_system_type(raw: str) -> str | None:
    """Clean and normalize a system type extracted from description regex."""
    if not raw:
        return None
    cleaned = re.sub(r"<[^>]+>", "", raw).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    lower = cleaned.lower()

    # Check for compound types: "Aerobic + Drip"
    parts_found = []
    for key, name in _COMPOUND_PARTS.items():
        if key in lower and name not in parts_found:
            parts_found.append(name)

    if len(parts_found) == 2:
        return f"{parts_found[0]} with {parts_found[1]}"
    if len(parts_found) == 1:
        return parts_found[0]

    # Try keyword match
    result = extract_system_type_keyword(cleaned)
    if result:
        return result

    # Return cleaned title-case if nothing matched
    return cleaned.title() if len(cleaned) > 2 else None


def parse_mgo_description(description: str | None) -> dict:
    """Extract structured fields from MGO description template text.

    Returns dict with: system_type, system_type_source, daily_flow_gpd,
    bedrooms, sqft, maintenance_contract_required, chlorine_required,
    renewal_years.
    """
    result: dict = {}
    if not description:
        return result

    # Strip HTML
    text = re.sub(r"<[^>]+>", "", description)

    # System type from "This <type> is designed to treat..."
    m = RE_SYSTEM_TYPE.search(text)
    if m:
        st = _normalize_description_system_type(m.group(1))
        if st:
            result["system_type"] = st
            result["system_type_source"] = "description"

    # GPD
    m = RE_GPD.search(text)
    if m:
        gpd = int(m.group(1))
        if 50 <= gpd <= 50000:
            result["daily_flow_gpd"] = gpd

    # Bedrooms
    m = RE_BEDROOMS.search(text)
    if m:
        beds = int(m.group(1))
        if 1 <= beds <= 20:
            result["bedrooms"] = beds

    # Square footage
    m = RE_SQFT.search(text)
    if m:
        sqft = int(m.group(1).replace(",", ""))
        if 200 <= sqft <= 100000:
            result["sqft"] = sqft

    # Maintenance contract
    if RE_MAINTENANCE.search(text):
        result["maintenance_contract_required"] = True

    # Chlorine
    if RE_CHLORINE.search(text):
        result["chlorine_required"] = True

    # Renewal period
    m = RE_RENEWAL.search(text)
    if m:
        val = WORD_TO_NUM.get(m.group(1).lower())
        if val:
            result["renewal_years"] = val

    return result


def parse_ossf_details(ossf_json: str | None) -> dict:
    """Parse OSSF details JSON string from MGO records."""
    import json

    if not ossf_json:
        return {}
    try:
        data = json.loads(ossf_json)
    except (json.JSONDecodeError, TypeError):
        return {}

    result = {}
    for key in (
        "designation_type",
        "specific_use",
        "designer_name",
        "designer_license",
        "installer_name",
        "installer_license",
        "maintenance_contract_required",
    ):
        val = data.get(key)
        if val:
            result[key] = val
    return result


# ── OCR-specific parsers ──────────────────────────────────────────────

RE_TANK_SIZE = re.compile(r"(\d{3,5})\s*(?:gal(?:lon)?s?)?", re.IGNORECASE)


def parse_tank_size(raw: str | None) -> int | None:
    """Extract tank size in gallons from OCR text."""
    if not raw:
        return None
    m = RE_TANK_SIZE.search(raw)
    if m:
        val = int(m.group(1))
        if 100 <= val <= 50000:
            return val
    return None


# ── Septic record filter (for SSS) ───────────────────────────────────

SEPTIC_KEYWORDS = {
    "septic", "ossf", "aerobic", "drainfield", "leach field",
    "disposal", "wastewater", "sewage", "effluent", "grease trap",
    "holding tank", "cesspool",
}


def is_septic_record(description: str | None, specific_use: str | None) -> bool:
    """Check if SSS record is septic-related based on keywords."""
    text = f"{description or ''} {specific_use or ''}".lower()
    return any(kw in text for kw in SEPTIC_KEYWORDS)


# ── Trade filter (for T430/MGO) ──────────────────────────────────────

SEPTIC_TRADES = {
    "septic", "ossf", "on-site sewage", "onsite sewage",
    "wastewater", "sewer", "plumbing", "mechanical",
    "environmental", "health", "sanitation",
}


def is_septic_trade(trade: str | None) -> bool:
    """Check if MGO/T430 trade field indicates septic work."""
    if not trade:
        return False
    return trade.lower().strip() in SEPTIC_TRADES
