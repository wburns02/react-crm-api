"""Pricing API - Dynamic zone-based pricing engine.

Features:
- Service catalog management
- Geographic pricing zones
- Dynamic pricing rules
- Price calculation with all adjustments
- Customer pricing tiers
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.pricing import ServiceCatalog, PricingZone, PricingRule, CustomerPricingTier

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models


class ServiceCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = None
    base_price: float = Field(..., ge=0)
    cost: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    unit: str = "each"
    default_quantity: float = 1.0
    estimated_duration_minutes: Optional[int] = None
    required_skills: Optional[List[str]] = None
    is_taxable: bool = True


class ZoneCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    zip_codes: Optional[List[str]] = None
    counties: Optional[List[str]] = None
    cities: Optional[List[str]] = None
    state: Optional[str] = None
    price_multiplier: float = 1.0
    travel_fee: float = 0.0
    mileage_rate: Optional[float] = None
    minimum_service_charge: Optional[float] = None


class RuleCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    rule_type: str  # surge, discount, seasonal, customer_tier, volume
    conditions: Optional[dict] = None
    adjustment_type: str  # percent, fixed
    adjustment_value: float
    applies_to_services: Optional[List[str]] = None
    applies_to_zones: Optional[List[str]] = None
    stackable: bool = False
    priority: int = 0
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class PriceCalculationRequest(BaseModel):
    service_code: str
    quantity: float = 1.0
    zip_code: Optional[str] = None
    customer_id: Optional[str] = None
    scheduled_date: Optional[datetime] = None


class PriceBreakdown(BaseModel):
    base_price: float
    quantity: float
    subtotal: float
    zone_adjustment: float
    zone_name: Optional[str] = None
    travel_fee: float
    rule_adjustments: List[dict]
    customer_discount: float
    customer_tier: Optional[str] = None
    total_before_tax: float
    tax_amount: float
    tax_rate: float
    total: float


# Helper functions


def service_to_response(svc: ServiceCatalog) -> dict:
    return {
        "id": str(svc.id),
        "code": svc.code,
        "name": svc.name,
        "description": svc.description,
        "category": svc.category,
        "base_price": svc.base_price,
        "cost": svc.cost,
        "min_price": svc.min_price,
        "max_price": svc.max_price,
        "unit": svc.unit,
        "default_quantity": svc.default_quantity,
        "estimated_duration_minutes": svc.estimated_duration_minutes,
        "required_skills": svc.required_skills,
        "is_taxable": svc.is_taxable,
        "is_active": svc.is_active,
        "created_at": svc.created_at.isoformat() if svc.created_at else None,
    }


def zone_to_response(zone: PricingZone) -> dict:
    return {
        "id": str(zone.id),
        "code": zone.code,
        "name": zone.name,
        "description": zone.description,
        "zip_codes": zone.zip_codes,
        "counties": zone.counties,
        "cities": zone.cities,
        "state": zone.state,
        "price_multiplier": zone.price_multiplier,
        "travel_fee": zone.travel_fee,
        "mileage_rate": zone.mileage_rate,
        "minimum_service_charge": zone.minimum_service_charge,
        "is_active": zone.is_active,
        "priority": zone.priority,
    }


def rule_to_response(rule: PricingRule) -> dict:
    return {
        "id": str(rule.id),
        "code": rule.code,
        "name": rule.name,
        "description": rule.description,
        "rule_type": rule.rule_type,
        "conditions": rule.conditions,
        "adjustment_type": rule.adjustment_type,
        "adjustment_value": rule.adjustment_value,
        "applies_to_services": rule.applies_to_services,
        "applies_to_zones": rule.applies_to_zones,
        "stackable": rule.stackable,
        "priority": rule.priority,
        "start_date": rule.start_date.isoformat() if rule.start_date else None,
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "is_active": rule.is_active,
    }


async def find_zone_for_zip(db: DbSession, zip_code: str) -> Optional[PricingZone]:
    """Find the pricing zone for a ZIP code."""
    result = await db.execute(
        select(PricingZone)
        .where(PricingZone.is_active == True)
        .where(PricingZone.zip_codes.contains([zip_code]))
        .order_by(PricingZone.priority.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def evaluate_rule_conditions(rule: PricingRule, context: dict) -> bool:
    """Check if a pricing rule's conditions are met."""
    if not rule.conditions:
        return True

    conditions = rule.conditions
    now = context.get("scheduled_date") or datetime.utcnow()

    # Day of week check
    if "day_of_week" in conditions:
        day_name = now.strftime("%A").lower()
        if day_name not in [d.lower() for d in conditions["day_of_week"]]:
            return False

    # Hour range check
    if "hour_range" in conditions:
        start_hour, end_hour = conditions["hour_range"]
        if not (start_hour <= now.hour <= end_hour):
            return False

    # Month check
    if "month" in conditions:
        if now.month not in conditions["month"]:
            return False

    # Customer tier check
    if "customer_tier" in conditions:
        if context.get("customer_tier") != conditions["customer_tier"]:
            return False

    return True


# Service Catalog Endpoints


@router.get("/services")
async def list_services(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    """List services in the catalog."""
    query = select(ServiceCatalog)

    if category:
        query = query.where(ServiceCatalog.category == category)
    if is_active is not None:
        query = query.where(ServiceCatalog.is_active == is_active)
    if search:
        query = query.where((ServiceCatalog.name.ilike(f"%{search}%")) | (ServiceCatalog.code.ilike(f"%{search}%")))

    query = query.order_by(ServiceCatalog.category, ServiceCatalog.name)
    result = await db.execute(query)
    services = result.scalars().all()

    return {"items": [service_to_response(s) for s in services]}


@router.post("/services")
async def create_service(
    request: ServiceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new service in the catalog."""
    # Check for duplicate code
    existing = await db.execute(select(ServiceCatalog).where(ServiceCatalog.code == request.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service code '{request.code}' already exists",
        )

    service = ServiceCatalog(**request.model_dump())
    db.add(service)
    await db.commit()
    await db.refresh(service)

    return service_to_response(service)


@router.get("/services/{service_id}")
async def get_service(
    service_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a service by ID."""
    result = await db.execute(select(ServiceCatalog).where(ServiceCatalog.id == service_id))
    service = result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service not found",
        )

    return service_to_response(service)


# Pricing Zone Endpoints


@router.get("/zones")
async def list_zones(
    db: DbSession,
    current_user: CurrentUser,
    is_active: Optional[bool] = None,
):
    """List pricing zones."""
    query = select(PricingZone)

    if is_active is not None:
        query = query.where(PricingZone.is_active == is_active)

    query = query.order_by(PricingZone.priority.desc(), PricingZone.name)
    result = await db.execute(query)
    zones = result.scalars().all()

    return {"items": [zone_to_response(z) for z in zones]}


@router.post("/zones")
async def create_zone(
    request: ZoneCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new pricing zone."""
    existing = await db.execute(select(PricingZone).where(PricingZone.code == request.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Zone code '{request.code}' already exists",
        )

    zone = PricingZone(**request.model_dump())
    db.add(zone)
    await db.commit()
    await db.refresh(zone)

    return zone_to_response(zone)


@router.get("/zones/lookup")
async def lookup_zone(
    zip_code: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Look up pricing zone for a ZIP code."""
    zone = await find_zone_for_zip(db, zip_code)

    if not zone:
        return {"zone": None, "message": "No zone found for this ZIP code"}

    return {"zone": zone_to_response(zone)}


# Pricing Rule Endpoints


@router.get("/rules")
async def list_rules(
    db: DbSession,
    current_user: CurrentUser,
    rule_type: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List pricing rules."""
    query = select(PricingRule)

    if rule_type:
        query = query.where(PricingRule.rule_type == rule_type)
    if is_active is not None:
        query = query.where(PricingRule.is_active == is_active)

    query = query.order_by(PricingRule.priority.desc(), PricingRule.name)
    result = await db.execute(query)
    rules = result.scalars().all()

    return {"items": [rule_to_response(r) for r in rules]}


@router.post("/rules")
async def create_rule(
    request: RuleCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new pricing rule."""
    existing = await db.execute(select(PricingRule).where(PricingRule.code == request.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rule code '{request.code}' already exists",
        )

    rule = PricingRule(**request.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    return rule_to_response(rule)


# Price Calculation


@router.post("/calculate")
async def calculate_price(
    request: PriceCalculationRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Calculate price with all adjustments applied."""
    # Get service
    svc_result = await db.execute(select(ServiceCatalog).where(ServiceCatalog.code == request.service_code))
    service = svc_result.scalar_one_or_none()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service '{request.service_code}' not found",
        )

    # Start with base price
    base_price = service.base_price
    quantity = request.quantity or service.default_quantity
    subtotal = base_price * quantity

    # Zone adjustment
    zone_adjustment = 0.0
    travel_fee = 0.0
    zone_name = None

    if request.zip_code:
        zone = await find_zone_for_zip(db, request.zip_code)
        if zone:
            zone_name = zone.name
            zone_adjustment = subtotal * (zone.price_multiplier - 1)
            travel_fee = zone.travel_fee or 0.0

    # Apply pricing rules
    rules_result = await db.execute(
        select(PricingRule).where(PricingRule.is_active == True).order_by(PricingRule.priority.desc())
    )
    rules = rules_result.scalars().all()

    rule_adjustments = []
    context = {
        "scheduled_date": request.scheduled_date,
        "customer_tier": None,  # TODO: Look up customer tier
    }

    running_total = subtotal + zone_adjustment

    for rule in rules:
        # Check if rule applies to this service
        if rule.applies_to_services and request.service_code not in rule.applies_to_services:
            continue

        # Check conditions
        if not evaluate_rule_conditions(rule, context):
            continue

        # Calculate adjustment
        if rule.adjustment_type == "percent":
            adjustment = running_total * (rule.adjustment_value / 100)
        else:
            adjustment = rule.adjustment_value

        # Apply limits
        if rule.max_adjustment and abs(adjustment) > rule.max_adjustment:
            adjustment = rule.max_adjustment if adjustment > 0 else -rule.max_adjustment

        rule_adjustments.append(
            {
                "rule_code": rule.code,
                "rule_name": rule.name,
                "adjustment_type": rule.adjustment_type,
                "adjustment_value": rule.adjustment_value,
                "calculated_adjustment": adjustment,
            }
        )

        if rule.stackable:
            running_total += adjustment
        else:
            running_total += adjustment
            break  # Non-stackable rule stops further processing

    # Customer tier discount
    customer_discount = 0.0
    customer_tier = None

    # TODO: Look up customer pricing tier and apply discount

    # Calculate totals
    total_before_tax = running_total + travel_fee - customer_discount

    # Apply min/max price limits
    if service.min_price and total_before_tax < service.min_price:
        total_before_tax = service.min_price
    if service.max_price and total_before_tax > service.max_price:
        total_before_tax = service.max_price

    # Tax
    tax_rate = 0.0825  # Default 8.25% - TODO: Make configurable
    tax_amount = total_before_tax * tax_rate if service.is_taxable else 0.0

    total = total_before_tax + tax_amount

    return {
        "service_code": request.service_code,
        "service_name": service.name,
        "breakdown": {
            "base_price": base_price,
            "quantity": quantity,
            "subtotal": subtotal,
            "zone_adjustment": zone_adjustment,
            "zone_name": zone_name,
            "travel_fee": travel_fee,
            "rule_adjustments": rule_adjustments,
            "customer_discount": customer_discount,
            "customer_tier": customer_tier,
            "total_before_tax": round(total_before_tax, 2),
            "tax_rate": tax_rate,
            "tax_amount": round(tax_amount, 2),
            "total": round(total, 2),
        },
    }


@router.get("/categories")
async def get_service_categories(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get list of unique service categories."""
    result = await db.execute(select(ServiceCatalog.category).where(ServiceCatalog.category.isnot(None)).distinct())
    categories = [row[0] for row in result.fetchall() if row[0]]

    return {"categories": sorted(categories)}
