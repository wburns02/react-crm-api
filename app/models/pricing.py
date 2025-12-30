"""Pricing models for dynamic, zone-based pricing engine."""
from sqlalchemy import Column, String, DateTime, Text, Integer, Float, Boolean, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
import uuid

from app.database import Base


class ServiceCatalog(Base):
    """Catalog of services with base pricing."""

    __tablename__ = "service_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Service identification
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)  # pumping, repair, inspection, installation

    # Pricing
    base_price = Column(Float, nullable=False)
    cost = Column(Float, nullable=True)  # Internal cost
    min_price = Column(Float, nullable=True)  # Floor price
    max_price = Column(Float, nullable=True)  # Ceiling price

    # Unit of measure
    unit = Column(String(50), default="each")  # each, hour, gallon, foot
    default_quantity = Column(Float, default=1.0)

    # Time estimates
    estimated_duration_minutes = Column(Integer, nullable=True)
    setup_time_minutes = Column(Integer, nullable=True)

    # Requirements
    required_skills = Column(ARRAY(String), nullable=True)
    required_equipment = Column(ARRAY(String), nullable=True)

    # Tax
    is_taxable = Column(Boolean, default=True)
    tax_category = Column(String(50), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<ServiceCatalog {self.code} - {self.name}>"


class PricingZone(Base):
    """Geographic pricing zones with multipliers."""

    __tablename__ = "pricing_zones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Zone identification
    name = Column(String(100), nullable=False)
    code = Column(String(20), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Geographic coverage
    zip_codes = Column(ARRAY(String), nullable=True)  # List of ZIP codes
    counties = Column(ARRAY(String), nullable=True)
    cities = Column(ARRAY(String), nullable=True)
    state = Column(String(2), nullable=True)

    # Geographic center (for distance calculations)
    center_latitude = Column(Float, nullable=True)
    center_longitude = Column(Float, nullable=True)
    radius_miles = Column(Float, nullable=True)

    # Price adjustments
    price_multiplier = Column(Float, default=1.0)  # 1.0 = base, 1.2 = 20% more
    travel_fee = Column(Float, default=0.0)  # Flat travel fee
    mileage_rate = Column(Float, nullable=True)  # Per mile charge

    # Minimum charges
    minimum_service_charge = Column(Float, nullable=True)
    minimum_travel_charge = Column(Float, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # Higher priority zones match first

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PricingZone {self.code} - {self.name}>"


class PricingRule(Base):
    """Dynamic pricing rules for adjustments."""

    __tablename__ = "pricing_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Rule identification
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Rule type
    rule_type = Column(String(50), nullable=False)  # surge, discount, seasonal, customer_tier, volume

    # Conditions (JSON for flexibility)
    conditions = Column(JSON, nullable=True)
    # Examples:
    # {"day_of_week": ["saturday", "sunday"]}  - Weekend surcharge
    # {"hour_range": [18, 22]}  - After hours
    # {"month": [6, 7, 8]}  - Summer peak
    # {"customer_tier": "premium"}  - VIP discount
    # {"service_count": {"gte": 5}}  - Volume discount

    # Adjustment
    adjustment_type = Column(String(20), nullable=False)  # percent, fixed
    adjustment_value = Column(Float, nullable=False)  # -10 for 10% off, 25 for $25 or 25%

    # Scope
    applies_to_services = Column(ARRAY(String), nullable=True)  # Service codes, null = all
    applies_to_zones = Column(ARRAY(String), nullable=True)  # Zone codes, null = all

    # Stacking
    stackable = Column(Boolean, default=False)  # Can combine with other rules
    priority = Column(Integer, default=0)  # Higher priority applies first

    # Limits
    max_adjustment = Column(Float, nullable=True)  # Cap on adjustment
    min_final_price = Column(Float, nullable=True)  # Floor price after adjustment

    # Validity
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<PricingRule {self.code} - {self.rule_type}>"


class CustomerPricingTier(Base):
    """Customer pricing tiers for special rates."""

    __tablename__ = "customer_pricing_tiers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Tier definition
    name = Column(String(100), nullable=False)
    code = Column(String(20), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Default discount
    default_discount_percent = Column(Float, default=0.0)

    # Service-specific overrides (JSON)
    service_discounts = Column(JSON, nullable=True)
    # Example: {"PUMP-1000": 15, "REPAIR": 10}

    # Requirements to qualify
    min_annual_spend = Column(Float, nullable=True)
    min_service_count = Column(Integer, nullable=True)
    requires_contract = Column(Boolean, default=False)

    # Benefits
    priority_scheduling = Column(Boolean, default=False)
    waive_travel_fee = Column(Boolean, default=False)
    extended_payment_terms = Column(Integer, nullable=True)  # Days

    # Status
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<CustomerPricingTier {self.code}>"
