#!/usr/bin/env python3
"""
Seed Script for Customer Segments

Creates comprehensive demo segments for the Enterprise Customer Success Platform:
- System segments (smart/dynamic segments)
- User segments (sample saved segments)
- Populates segment memberships based on existing customer data

Run with: python scripts/seed_segments.py
"""

import asyncio
import random
from datetime import datetime, timedelta
from decimal import Decimal
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.customer import Customer
from app.models.customer_success.health_score import HealthScore
from app.models.customer_success.segment import Segment, CustomerSegment


# ============================================================
# SEGMENT DEFINITIONS
# ============================================================

# System segments - automatically evaluated based on rules
SYSTEM_SEGMENTS = [
    {
        "name": "High Value Accounts",
        "description": "Strategic customers with high contract value and engagement. Priority for QBRs and executive touchpoints.",
        "color": "#10B981",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "estimated_value", "operator": "gte", "value": 5000},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 100,
        "is_system": True,
        "tags": ["priority", "strategic", "high-touch"]
    },
    {
        "name": "At Risk - Low Engagement",
        "description": "Customers showing signs of disengagement with declining health scores. Requires immediate intervention.",
        "color": "#EF4444",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "health_score", "operator": "lt", "value": 50},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 95,
        "is_system": True,
        "tags": ["at-risk", "urgent", "churn-prevention"]
    },
    {
        "name": "Growth Candidates",
        "description": "Healthy accounts with expansion potential - good health scores with room to grow.",
        "color": "#3B82F6",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "health_score", "operator": "gte", "value": 70},
                {"field": "tank_count", "operator": "lt", "value": 3}
            ]
        },
        "priority": 80,
        "is_system": True,
        "tags": ["expansion", "upsell", "growth"]
    },
    {
        "name": "New Customers (< 90 days)",
        "description": "Recently onboarded customers in their first 90 days. Critical period for adoption and success.",
        "color": "#8B5CF6",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "days_since_signup", "operator": "lt", "value": 90},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 90,
        "is_system": True,
        "tags": ["onboarding", "new-customer", "adoption"]
    },
    {
        "name": "Champions",
        "description": "Highly engaged advocates with excellent health scores. Great candidates for referrals and case studies.",
        "color": "#F59E0B",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "health_score", "operator": "gte", "value": 85},
                {"field": "engagement_score", "operator": "gte", "value": 75}
            ]
        },
        "priority": 85,
        "is_system": True,
        "tags": ["champion", "advocate", "referral"]
    },
    {
        "name": "Commercial Accounts",
        "description": "Business and commercial customers with different service needs than residential.",
        "color": "#6366F1",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "customer_type", "operator": "eq", "value": "Commercial"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 70,
        "is_system": True,
        "tags": ["commercial", "b2b", "enterprise"]
    },
    {
        "name": "Aerobic System Owners",
        "description": "Customers with aerobic septic systems requiring specialized maintenance schedules.",
        "color": "#06B6D4",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "system_type", "operator": "eq", "value": "Aerobic"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 65,
        "is_system": True,
        "tags": ["aerobic", "equipment-specific", "maintenance"]
    },
    {
        "name": "Large Tank Owners (1500+ gal)",
        "description": "Customers with large capacity systems - typically multi-family or commercial properties.",
        "color": "#14B8A6",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "tank_size_gallons", "operator": "gte", "value": 1500},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 60,
        "is_system": True,
        "tags": ["large-system", "high-capacity"]
    },
]

# Demo user segments - examples of saved segments for specific campaigns
DEMO_USER_SEGMENTS = [
    {
        "name": "Aerobic System Owners - San Marcos",
        "description": "Geographic + equipment type segment: Aerobic system owners in San Marcos area for targeted maintenance campaign.",
        "color": "#059669",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "system_type", "operator": "eq", "value": "Aerobic"},
                {"field": "city", "operator": "eq", "value": "San Marcos"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 50,
        "is_system": False,
        "tags": ["geographic", "aerobic", "san-marcos", "campaign"]
    },
    {
        "name": "VIP At-Risk",
        "description": "High value customers showing concerning health signals. Priority intervention needed to prevent churn.",
        "color": "#DC2626",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "estimated_value", "operator": "gte", "value": 3000},
                {"field": "health_score", "operator": "lt", "value": 60},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 98,
        "is_system": False,
        "tags": ["vip", "at-risk", "high-priority", "urgent"]
    },
    {
        "name": "Summer Campaign 2024",
        "description": "Saved segment for Summer 2024 maintenance campaign - residential customers in high-usage areas.",
        "color": "#F97316",
        "segment_type": "static",
        "rules": None,
        "priority": 40,
        "is_system": False,
        "tags": ["campaign", "seasonal", "summer-2024", "marketing"]
    },
    {
        "name": "Contract Renewals Due",
        "description": "Service contracts expiring in the next 60 days - proactive renewal outreach needed.",
        "color": "#7C3AED",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "days_to_renewal", "operator": "lte", "value": 60},
                {"field": "days_to_renewal", "operator": "gte", "value": 0},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 88,
        "is_system": False,
        "tags": ["renewal", "contract", "retention", "proactive"]
    },
    {
        "name": "Recent Complainers",
        "description": "Customers with negative touchpoints or low satisfaction in the past 30 days. Service recovery candidates.",
        "color": "#E11D48",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "recent_negative_touchpoints", "operator": "gte", "value": 1},
                {"field": "days_since_last_negative", "operator": "lte", "value": 30},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 92,
        "is_system": False,
        "tags": ["service-recovery", "complaint", "urgent", "support"]
    },
    {
        "name": "Houston Metro Residential",
        "description": "Residential customers in the greater Houston metropolitan area.",
        "color": "#2563EB",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Houston"},
                {"field": "customer_type", "operator": "eq", "value": "Residential"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 55,
        "is_system": False,
        "tags": ["geographic", "houston", "residential"]
    },
    {
        "name": "Multi-Tank Properties",
        "description": "Properties with multiple septic tanks - often HOAs or commercial complexes requiring coordinated service.",
        "color": "#0891B2",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "number_of_tanks", "operator": "gte", "value": 2},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 62,
        "is_system": False,
        "tags": ["multi-tank", "complex", "coordinated-service"]
    },
    {
        "name": "Referral Sources",
        "description": "Customers who came through referrals - track for loyalty programs and thank-you campaigns.",
        "color": "#84CC16",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "lead_source", "operator": "eq", "value": "Referral"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 45,
        "is_system": False,
        "tags": ["referral", "loyalty", "word-of-mouth"]
    },
    {
        "name": "Digital Leads",
        "description": "Customers acquired through digital channels (Google, Facebook, Website) - track ROI and engagement.",
        "color": "#8B5CF6",
        "segment_type": "dynamic",
        "rules": {
            "logic": "or",
            "rules": [
                {"field": "lead_source", "operator": "eq", "value": "Google"},
                {"field": "lead_source", "operator": "eq", "value": "Facebook"},
                {"field": "lead_source", "operator": "eq", "value": "Website"}
            ]
        },
        "priority": 42,
        "is_system": False,
        "tags": ["digital", "marketing", "acquisition"]
    },
    {
        "name": "Subdivision: Oak Meadows",
        "description": "All customers in Oak Meadows subdivision - useful for neighborhood campaigns and coordinated service.",
        "color": "#22C55E",
        "segment_type": "dynamic",
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "subdivision", "operator": "eq", "value": "Oak Meadows"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "priority": 35,
        "is_system": False,
        "tags": ["subdivision", "neighborhood", "oak-meadows"]
    },
]


async def clear_segment_data(session: AsyncSession):
    """Clear all segment data for fresh seeding."""
    print("Clearing existing segment data...")

    # Delete in dependency order
    await session.execute(delete(CustomerSegment))
    await session.execute(delete(Segment))
    await session.commit()
    print("  Segment data cleared.")


async def get_customer_data(session: AsyncSession) -> dict:
    """Get customer data for segment assignment."""
    print("\nLoading customer data...")

    # Get all active customers with their details
    result = await session.execute(
        select(Customer).where(Customer.is_active == True)
    )
    customers = result.scalars().all()

    # Get health scores
    health_result = await session.execute(
        select(HealthScore)
    )
    health_scores = {hs.customer_id: hs for hs in health_result.scalars().all()}

    customer_data = {}
    for c in customers:
        hs = health_scores.get(c.id)
        customer_data[c.id] = {
            "customer": c,
            "health_score": hs.overall_score if hs else 50,
            "health_status": hs.health_status if hs else "at_risk",
            "engagement_score": hs.engagement_score if hs else 50,
            "system_type": c.system_type,
            "city": c.city,
            "customer_type": c.customer_type,
            "estimated_value": float(c.estimated_value) if c.estimated_value else 0,
            "tank_size_gallons": c.tank_size_gallons or 1000,
            "number_of_tanks": c.number_of_tanks or 1,
            "lead_source": c.lead_source,
            "subdivision": c.subdivision,
            "created_at": c.created_at,
        }

    print(f"  Loaded {len(customer_data)} active customers")
    return customer_data


def evaluate_rule(customer_data: dict, rule: dict) -> bool:
    """Evaluate a single rule against customer data."""
    field = rule.get("field")
    operator = rule.get("operator")
    value = rule.get("value")

    # Get the field value from customer data
    if field == "health_score":
        field_value = customer_data.get("health_score", 0)
    elif field == "engagement_score":
        field_value = customer_data.get("engagement_score", 0)
    elif field == "is_active":
        field_value = True  # We only load active customers
    elif field == "estimated_value":
        field_value = customer_data.get("estimated_value", 0)
    elif field == "tank_count" or field == "number_of_tanks":
        field_value = customer_data.get("number_of_tanks", 1)
    elif field == "tank_size_gallons":
        field_value = customer_data.get("tank_size_gallons", 0)
    elif field == "system_type":
        field_value = customer_data.get("system_type", "")
    elif field == "city":
        field_value = customer_data.get("city", "")
    elif field == "customer_type":
        field_value = customer_data.get("customer_type", "")
    elif field == "lead_source":
        field_value = customer_data.get("lead_source", "")
    elif field == "subdivision":
        field_value = customer_data.get("subdivision", "")
    elif field == "days_since_signup":
        created_at = customer_data.get("created_at")
        if created_at:
            field_value = (datetime.now() - created_at).days
        else:
            field_value = 365  # Default to old customer
    elif field == "days_to_renewal":
        # Simulate renewal dates - random for demo
        field_value = random.randint(-30, 180)
    elif field == "recent_negative_touchpoints":
        # Simulate - random for demo
        field_value = random.randint(0, 3)
    elif field == "days_since_last_negative":
        # Simulate - random for demo
        field_value = random.randint(0, 90)
    else:
        return False

    # Evaluate the operator
    if operator == "eq":
        return field_value == value
    elif operator == "neq":
        return field_value != value
    elif operator == "gt":
        return field_value > value
    elif operator == "lt":
        return field_value < value
    elif operator == "gte":
        return field_value >= value
    elif operator == "lte":
        return field_value <= value
    elif operator == "contains":
        return value.lower() in str(field_value).lower() if field_value else False
    elif operator == "in":
        return field_value in value if isinstance(value, list) else False
    else:
        return False


def evaluate_rules(customer_data: dict, rules: dict) -> bool:
    """Evaluate a rule set against customer data."""
    if not rules:
        return False

    logic = rules.get("logic", "and")
    rule_list = rules.get("rules", [])

    if not rule_list:
        return False

    results = []
    for rule in rule_list:
        if "logic" in rule:
            # Nested rule set
            results.append(evaluate_rules(customer_data, rule))
        else:
            # Single rule
            results.append(evaluate_rule(customer_data, rule))

    if logic == "and":
        return all(results)
    elif logic == "or":
        return any(results)
    else:
        return False


async def create_segments(session: AsyncSession) -> list[Segment]:
    """Create all segments."""
    print("\nCreating segments...")

    all_segments = SYSTEM_SEGMENTS + DEMO_USER_SEGMENTS
    created_segments = []

    for seg_data in all_segments:
        is_system = seg_data.pop("is_system", False)
        tags = seg_data.pop("tags", [])

        segment = Segment(
            **seg_data,
            auto_refresh=True,
            refresh_interval_hours=1 if seg_data.get("priority", 0) >= 90 else 24,
            is_active=True,
        )
        session.add(segment)
        await session.flush()
        created_segments.append(segment)

        print(f"  Created segment: {segment.name} (type: {segment.segment_type}, priority: {segment.priority})")

    await session.commit()
    return created_segments


async def populate_segment_memberships(
    session: AsyncSession,
    segments: list[Segment],
    customer_data: dict
) -> int:
    """Populate segment memberships based on rules."""
    print("\nPopulating segment memberships...")

    total_memberships = 0
    segment_stats = {}

    for segment in segments:
        matching_customers = []

        if segment.segment_type == "dynamic" and segment.rules:
            # Evaluate rules for each customer
            for customer_id, data in customer_data.items():
                if evaluate_rules(data, segment.rules):
                    matching_customers.append(customer_id)

        elif segment.segment_type == "static":
            # For static segments, add random selection of customers (demo data)
            all_customer_ids = list(customer_data.keys())
            sample_size = min(len(all_customer_ids), random.randint(10, 30))
            matching_customers = random.sample(all_customer_ids, sample_size)

        # Create memberships
        for customer_id in matching_customers:
            membership = CustomerSegment(
                customer_id=customer_id,
                segment_id=segment.id,
                is_active=True,
                entry_reason=f"Matched segment rules: {segment.name}",
                added_by="system:seed_segments"
            )
            session.add(membership)
            total_memberships += 1

        # Update segment metrics
        segment.customer_count = len(matching_customers)

        # Calculate average health score for the segment
        if matching_customers:
            health_scores = [customer_data[cid]["health_score"] for cid in matching_customers]
            segment.avg_health_score = sum(health_scores) / len(health_scores)

            # Count at-risk customers
            segment.at_risk_count = sum(
                1 for cid in matching_customers
                if customer_data[cid].get("health_status") in ("at_risk", "critical")
            )

            # Calculate total ARR (estimated value)
            segment.total_arr = sum(
                Decimal(str(customer_data[cid].get("estimated_value", 0)))
                for cid in matching_customers
            )

        segment.last_refreshed_at = datetime.utcnow()
        segment_stats[segment.name] = len(matching_customers)

        print(f"  {segment.name}: {len(matching_customers)} customers")

    await session.commit()
    return total_memberships


async def print_summary(session: AsyncSession):
    """Print summary of seeded data."""
    print("\n" + "="*60)
    print("SEGMENT SEED SUMMARY")
    print("="*60)

    # Get segment counts
    result = await session.execute(select(func.count(Segment.id)))
    total_segments = result.scalar()

    result = await session.execute(
        select(func.count(Segment.id)).where(Segment.segment_type == "dynamic")
    )
    dynamic_count = result.scalar()

    result = await session.execute(
        select(func.count(Segment.id)).where(Segment.segment_type == "static")
    )
    static_count = result.scalar()

    result = await session.execute(select(func.count(CustomerSegment.id)))
    total_memberships = result.scalar()

    print(f"Total Segments: {total_segments}")
    print(f"  - Dynamic: {dynamic_count}")
    print(f"  - Static: {static_count}")
    print(f"Total Memberships: {total_memberships}")

    print("\nSegment Details:")
    result = await session.execute(
        select(Segment).order_by(Segment.priority.desc())
    )
    for segment in result.scalars().all():
        print(f"  {segment.name}")
        print(f"    Type: {segment.segment_type}, Priority: {segment.priority}")
        print(f"    Customers: {segment.customer_count}, Avg Health: {segment.avg_health_score:.1f if segment.avg_health_score else 0}")

    print("="*60)
    print("Segment seeding complete!")
    print("="*60)


async def main():
    """Main seed function."""
    print("="*60)
    print("Customer Segments - Seed Script")
    print("="*60)

    async with async_session_maker() as session:
        # Clear existing data
        await clear_segment_data(session)

        # Get customer data for evaluation
        customer_data = await get_customer_data(session)

        if not customer_data:
            print("\nNo customer data found! Run seed_customer_success.py first.")
            return

        # Create segments
        segments = await create_segments(session)

        # Populate memberships
        await populate_segment_memberships(session, segments, customer_data)

        # Print summary
        await print_summary(session)


if __name__ == "__main__":
    asyncio.run(main())
