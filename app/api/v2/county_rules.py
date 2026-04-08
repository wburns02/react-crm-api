"""
County Rules API — county lookup and septic rules for Texas counties.
"""

import logging
from fastapi import APIRouter, Query
from sqlalchemy import select, update, func, or_

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.services.county_lookup import (
    lookup_county,
    get_county_rules,
    is_service_area_county,
    COUNTY_RULES,
    TX_ZIP_TO_COUNTY,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/lookup")
async def lookup_county_endpoint(
    postal_code: str = Query(..., description="ZIP code to look up"),
    state: str = Query("TX", description="State code"),
):
    """Look up county from a ZIP code."""
    county = lookup_county(postal_code, state)
    rules = get_county_rules(county) if county else None
    return {
        "county": county,
        "is_service_area": is_service_area_county(county),
        "rules": rules,
    }


@router.get("/rules")
async def list_county_rules():
    """Get all county rules for the MAC Septic service area."""
    return {
        "counties": {
            name: {
                **rules,
                "name": name,
            }
            for name, rules in COUNTY_RULES.items()
        }
    }


@router.get("/rules/{county_name}")
async def get_county_rules_endpoint(county_name: str):
    """Get rules for a specific county."""
    rules = get_county_rules(county_name)
    if not rules:
        return {"county": county_name, "is_service_area": False, "rules": None}
    return {"county": county_name, "is_service_area": True, "rules": rules}


@router.post("/backfill")
async def backfill_counties(
    db: DbSession,
    current_user: CurrentUser,
):
    """Backfill county for all Texas customers/prospects that have a ZIP code but no county."""
    result = await db.execute(
        select(Customer).where(
            Customer.postal_code.isnot(None),
            Customer.postal_code != "",
            or_(Customer.state == "TX", Customer.state == "tx", Customer.state == "Texas"),
            or_(Customer.county.is_(None), Customer.county == ""),
        )
    )
    customers = result.scalars().all()

    updated = 0
    for customer in customers:
        county = lookup_county(customer.postal_code, customer.state)
        if county:
            customer.county = county
            updated += 1

    await db.commit()
    logger.info(f"Backfilled county for {updated} customers")
    return {"backfilled": updated, "total_checked": len(customers)}
