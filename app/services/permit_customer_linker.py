"""
Permit-Customer Linking Service.

Matches septic permits to CRM customers using:
1. Exact normalized address match
2. Phone number match
3. Fuzzy name + city match
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.septic_permit import SepticPermit

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of a permit-to-customer match attempt."""
    customer_id: str
    confidence: str  # "high", "medium", "low"
    match_method: str  # "address", "phone", "name_city"
    details: str


def normalize_address(address: str | None) -> str:
    """Normalize an address for comparison."""
    if not address:
        return ""
    addr = address.upper().strip()
    # Common abbreviations
    replacements = {
        " STREET": " ST",
        " AVENUE": " AVE",
        " BOULEVARD": " BLVD",
        " DRIVE": " DR",
        " LANE": " LN",
        " ROAD": " RD",
        " COURT": " CT",
        " CIRCLE": " CIR",
        " PLACE": " PL",
        " HIGHWAY": " HWY",
        " PARKWAY": " PKWY",
        " NORTH": " N",
        " SOUTH": " S",
        " EAST": " E",
        " WEST": " W",
        " NORTHEAST": " NE",
        " NORTHWEST": " NW",
        " SOUTHEAST": " SE",
        " SOUTHWEST": " SW",
        " APARTMENT": " APT",
        " SUITE": " STE",
        " UNIT": " #",
    }
    for full, abbr in replacements.items():
        addr = addr.replace(full, abbr)
    # Remove extra whitespace, punctuation
    addr = re.sub(r'[.,#]', '', addr)
    addr = re.sub(r'\s+', ' ', addr)
    return addr.strip()


def normalize_phone(phone: str | None) -> str:
    """Extract digits from phone number for comparison."""
    if not phone:
        return ""
    digits = re.sub(r'\D', '', phone)
    # Ensure 10-digit US format
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else ""


def name_similarity(name1: str, name2: str) -> float:
    """Simple Levenshtein-based similarity ratio (0-1)."""
    if not name1 or not name2:
        return 0.0
    n1 = name1.upper().strip()
    n2 = name2.upper().strip()
    if n1 == n2:
        return 1.0
    # Use sequence matcher for fuzzy comparison
    from difflib import SequenceMatcher
    return SequenceMatcher(None, n1, n2).ratio()


async def find_customer_for_permit(
    db: AsyncSession,
    permit: SepticPermit,
) -> Optional[MatchResult]:
    """
    Try to match a permit to a customer using multiple strategies.
    Returns MatchResult if found, None otherwise.
    """
    # Strategy 1: Exact address match
    if permit.address_normalized or permit.address:
        normalized = normalize_address(permit.address_normalized or permit.address)
        if normalized:
            result = await db.execute(
                select(Customer).where(
                    Customer.is_active == True,
                    func.upper(Customer.address_line1).isnot(None),
                )
            )
            customers = result.scalars().all()
            for cust in customers:
                cust_addr = normalize_address(cust.address_line1)
                if cust_addr and cust_addr == normalized:
                    return MatchResult(
                        customer_id=str(cust.id),
                        confidence="high",
                        match_method="address",
                        details=f"Exact address match: {normalized}",
                    )

    # Strategy 2: Phone match
    permit_phone = ""
    if permit.raw_data and isinstance(permit.raw_data, dict):
        permit_phone = normalize_phone(permit.raw_data.get("owner_phone"))
    if permit_phone:
        result = await db.execute(
            select(Customer).where(
                Customer.is_active == True,
                Customer.phone.isnot(None),
            )
        )
        customers = result.scalars().all()
        for cust in customers:
            cust_phone = normalize_phone(cust.phone)
            if cust_phone and cust_phone == permit_phone:
                return MatchResult(
                    customer_id=str(cust.id),
                    confidence="high",
                    match_method="phone",
                    details=f"Phone match: {permit_phone}",
                )

    # Strategy 3: Name + city fuzzy match
    if permit.owner_name and permit.city:
        permit_city = (permit.city or "").upper().strip()
        result = await db.execute(
            select(Customer).where(
                Customer.is_active == True,
                func.upper(Customer.city) == permit_city,
            )
        )
        customers = result.scalars().all()
        best_match = None
        best_score = 0.0

        for cust in customers:
            cust_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip()
            score = name_similarity(permit.owner_name, cust_name)
            if score > best_score:
                best_score = score
                best_match = cust

        if best_match and best_score >= 0.85:
            return MatchResult(
                customer_id=str(best_match.id),
                confidence="medium" if best_score < 0.95 else "high",
                match_method="name_city",
                details=f"Name similarity: {best_score:.0%} in {permit_city}",
            )

    return None


async def batch_link_permits(
    db: AsyncSession,
    limit: int = 1000,
    auto_link_only: bool = True,
) -> dict:
    """
    Run auto-linking on unlinked permits.

    Args:
        db: Database session
        limit: Max permits to process
        auto_link_only: If True, only link high-confidence matches

    Returns:
        Stats dict with linked/skipped/failed counts
    """
    stats = {
        "processed": 0,
        "linked_high": 0,
        "linked_medium": 0,
        "skipped": 0,
        "errors": 0,
    }

    # Get unlinked permits
    result = await db.execute(
        select(SepticPermit).where(
            SepticPermit.customer_id.is_(None),
            SepticPermit.is_active == True,
        ).limit(limit)
    )
    permits = result.scalars().all()

    for permit in permits:
        stats["processed"] += 1
        try:
            match = await find_customer_for_permit(db, permit)
            if match:
                if match.confidence == "high":
                    permit.customer_id = match.customer_id
                    stats["linked_high"] += 1
                    logger.info(f"Linked permit {permit.id} → customer {match.customer_id} ({match.match_method})")
                elif not auto_link_only and match.confidence == "medium":
                    permit.customer_id = match.customer_id
                    stats["linked_medium"] += 1
                    logger.info(f"Linked permit {permit.id} → customer {match.customer_id} (medium: {match.match_method})")
                else:
                    stats["skipped"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.error(f"Error linking permit {permit.id}: {e}")

    await db.commit()
    return stats
