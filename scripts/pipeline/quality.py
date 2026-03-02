"""Unified quality scoring for permit records.

Consolidates 3 different scoring implementations into one consistent
0-100 scale that accounts for field completeness and source reliability.
"""

from __future__ import annotations

from typing import Any


def compute_quality_score(permit: dict[str, Any]) -> int:
    """Score a permit record 0-100 based on field completeness.

    Weights:
      address         20  (required, most important)
      permit_number   10
      city + zip      10  (5 each, or 5 for just one)
      system_type     8-15  (varies by extraction method)
      daily_flow_gpd  10
      bedrooms        10
      lat/lng         10
      owner_name       5
      permit_date      5
      parcel_number    5
    """
    score = 0
    raw = permit.get("raw_data") or {}

    # Address (20 pts) — most important for dedup
    if permit.get("address"):
        score += 20

    # Permit number (10 pts)
    if permit.get("permit_number"):
        score += 10

    # City + zip (10 pts total)
    has_city = bool(permit.get("city"))
    has_zip = bool(permit.get("zip_code"))
    if has_city and has_zip:
        score += 10
    elif has_city or has_zip:
        score += 5

    # System type (8-15 pts, depending on extraction confidence)
    if permit.get("system_type"):
        source = raw.get("system_type_source", "keyword")
        if source == "description":
            score += 15  # MGO description regex — highest confidence
        elif source == "work_type":
            score += 12  # MGO work_type mapping
        elif source == "ocr":
            score += 10  # OCR extraction
        else:
            score += 8  # Keyword fallback

    # Flow + bedrooms (10 each)
    if permit.get("daily_flow_gpd"):
        score += 10
    if permit.get("bedrooms"):
        score += 10

    # Coordinates (10 pts)
    if permit.get("latitude") and permit.get("longitude"):
        score += 10

    # Owner name (5 pts)
    if permit.get("owner_name"):
        score += 5

    # Permit date (5 pts)
    if permit.get("permit_date"):
        score += 5

    # Parcel number (5 pts)
    if permit.get("parcel_number"):
        score += 5

    # Bonus: tank size (OCR-only, 3 pts)
    if permit.get("tank_size_gallons"):
        score += 3

    # Bonus: subdivision info (3 pts)
    if raw.get("subdivision"):
        score += 3

    # Bonus: maintenance contract info (2 pts)
    if raw.get("maintenance_contract_required"):
        score += 2

    return min(score, 100)
