"""Shared types for the unified permit pipeline."""

from __future__ import annotations

from typing import TypedDict


class NormalizedPermit(TypedDict, total=False):
    """Canonical permit record — every adapter maps to this shape.

    Required fields: address, state_code, county_name, source_portal_code.
    All other fields are optional and filled by whichever source has them.
    """

    # ── Identity ──────────────────────────────────────────────────────
    address: str  # Normalized street address (uppercase, standardized)
    address_hash: str  # SHA256 of address|county|state (dedup key)
    state_code: str  # 2-letter state code
    county_name: str  # Normalized county name (no "County" suffix)
    permit_number: str | None

    # ── Location ──────────────────────────────────────────────────────
    city: str | None
    zip_code: str | None
    latitude: float | None
    longitude: float | None
    parcel_number: str | None

    # ── People ────────────────────────────────────────────────────────
    owner_name: str | None
    owner_phone: str | None
    owner_email: str | None
    applicant_name: str | None
    contractor_name: str | None

    # ── System Details ────────────────────────────────────────────────
    system_type: str | None  # Standardized name from KEYWORD_SYSTEM_TYPES
    daily_flow_gpd: int | None
    bedrooms: int | None
    tank_size_gallons: int | None

    # ── Dates ─────────────────────────────────────────────────────────
    permit_date: str | None  # YYYY-MM-DD
    expiration_date: str | None  # YYYY-MM-DD
    install_date: str | None  # YYYY-MM-DD

    # ── Metadata ──────────────────────────────────────────────────────
    source_portal_code: str  # e.g. "mgo_williamson_tx", "sss_travis_tx"
    scraped_at: str  # ISO datetime
    quality_score: int  # 0-100
    raw_data: dict  # Source-specific fields preserved here

    # ── Enrichment (added by pipeline) ────────────────────────────────
    parcel_owner_name: str | None
    parcel_geo_id: str | None
    parcel_mkt_value: str | None
    parcel_match_type: str | None  # "exact" | "variant"


# Source adapter names — used in CLI, checkpoints, and merge priority
SOURCE_MGO = "mgo"
SOURCE_SSS = "sss"
SOURCE_TNR = "tnr"
SOURCE_OCR = "ocr"
ALL_SOURCES = [SOURCE_MGO, SOURCE_SSS, SOURCE_TNR, SOURCE_OCR]

# Field merge priority: which source wins for each field
FIELD_PRIORITY: dict[str, list[str]] = {
    "system_type": [SOURCE_MGO, SOURCE_OCR, SOURCE_SSS, SOURCE_TNR],
    "daily_flow_gpd": [SOURCE_MGO, SOURCE_SSS],
    "bedrooms": [SOURCE_MGO, SOURCE_SSS, SOURCE_OCR],
    "permit_date": [SOURCE_TNR, SOURCE_MGO, SOURCE_SSS, SOURCE_OCR],
    "parcel_number": [SOURCE_SSS],
    "tank_size_gallons": [SOURCE_OCR],
    "owner_name": [SOURCE_OCR, SOURCE_MGO],  # Parcel enrichment overrides later
    "owner_phone": [SOURCE_OCR],  # Only OCR extracts phone from PDFs
    "owner_email": [SOURCE_OCR],  # Only OCR extracts email from PDFs
    "contractor_name": [SOURCE_OCR, SOURCE_MGO],
    "latitude": [SOURCE_MGO, SOURCE_SSS, SOURCE_TNR, SOURCE_OCR],
    "longitude": [SOURCE_MGO, SOURCE_SSS, SOURCE_TNR, SOURCE_OCR],
    "city": [SOURCE_MGO, SOURCE_SSS, SOURCE_TNR, SOURCE_OCR],
    "zip_code": [SOURCE_MGO, SOURCE_SSS, SOURCE_TNR, SOURCE_OCR],
}
