#!/usr/bin/env python3
"""
Seed Script for Enterprise Customer Success Platform

Creates test data for:
- Customers (100 max, removes existing beyond that)
- Health Scores
- Segments & Customer-Segment memberships
- Playbooks with steps
- Journeys with steps and enrollments
- Tasks
- Touchpoints

Run with: python scripts/seed_customer_success.py
"""

import asyncio
import random
from datetime import datetime, timedelta, date
from decimal import Decimal
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker, engine
from app.models.customer import Customer
from app.models.customer_success.health_score import HealthScore, HealthScoreEvent
from app.models.customer_success.segment import Segment, CustomerSegment
from app.models.customer_success.playbook import Playbook, PlaybookStep, PlaybookExecution
from app.models.customer_success.journey import Journey, JourneyStep, JourneyEnrollment, JourneyStepExecution
from app.models.customer_success.task import CSTask
from app.models.customer_success.touchpoint import Touchpoint


# Fake data generators
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Dorothy", "Kevin", "Carol", "Brian", "Amanda", "George", "Melissa"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell"
]

CITIES = [
    ("Houston", "TX", "77001"), ("Austin", "TX", "78701"), ("Dallas", "TX", "75201"),
    ("San Antonio", "TX", "78201"), ("Fort Worth", "TX", "76101"), ("El Paso", "TX", "79901"),
    ("Arlington", "TX", "76001"), ("Corpus Christi", "TX", "78401"), ("Plano", "TX", "75023"),
    ("Lubbock", "TX", "79401"), ("Irving", "TX", "75014"), ("Laredo", "TX", "78040"),
    ("Garland", "TX", "75040"), ("Frisco", "TX", "75034"), ("McKinney", "TX", "75069")
]

SUBDIVISIONS = [
    "Oak Meadows", "Riverside Estates", "Cedar Creek", "Pine Valley", "Willow Springs",
    "Maple Ridge", "Sunset Hills", "Lake View", "Country Club", "Greenwood",
    "Highland Park", "Meadow Brook", "Forest Glen", "Valley View", "Rolling Hills"
]

SYSTEM_TYPES = ["Conventional", "Aerobic", "Mound", "Chamber", "Drip Distribution"]
TANK_SIZES = [500, 750, 1000, 1250, 1500, 2000]

LEAD_SOURCES = ["Google", "Referral", "Facebook", "Website", "Yelp", "Direct Mail", "Phone Book"]
CUSTOMER_TYPES = ["Residential", "Commercial", "Multi-Family", "HOA"]


def random_phone():
    return f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}"


def random_email(first, last):
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"]
    return f"{first.lower()}.{last.lower()}@{random.choice(domains)}"


def random_address():
    return f"{random.randint(100, 9999)} {random.choice(['Oak', 'Elm', 'Main', 'Cedar', 'Pine', 'Maple'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr', 'Ln', 'Way'])}"


async def clear_customer_success_data(session: AsyncSession):
    """Clear all Customer Success related data."""
    print("Clearing existing Customer Success data...")

    # Delete in reverse order of dependencies
    await session.execute(delete(JourneyStepExecution))
    await session.execute(delete(JourneyEnrollment))
    await session.execute(delete(JourneyStep))
    await session.execute(delete(Journey))

    await session.execute(delete(CSTask))
    await session.execute(delete(PlaybookExecution))
    await session.execute(delete(PlaybookStep))
    await session.execute(delete(Playbook))

    await session.execute(delete(Touchpoint))
    await session.execute(delete(HealthScoreEvent))
    await session.execute(delete(HealthScore))

    await session.execute(delete(CustomerSegment))
    await session.execute(delete(Segment))

    await session.commit()
    print("Customer Success data cleared.")


async def manage_customers(session: AsyncSession, target_count: int = 100):
    """Ensure exactly target_count customers exist, removing Stephanie Burns specifically."""
    print(f"\nManaging customers (target: {target_count})...")

    # First, remove Stephanie Burns specifically
    stmt = select(Customer).where(
        func.lower(Customer.first_name) == 'stephanie',
        func.lower(Customer.last_name) == 'burns'
    )
    result = await session.execute(stmt)
    stephanie = result.scalars().all()
    for s in stephanie:
        print(f"  Removing Stephanie Burns (ID: {s.id})")
        await session.delete(s)

    await session.commit()

    # Count existing customers
    result = await session.execute(select(func.count(Customer.id)))
    current_count = result.scalar()
    print(f"  Current customer count: {current_count}")

    if current_count > target_count:
        # Delete excess customers (oldest first, but not the ones with work orders ideally)
        excess = current_count - target_count
        print(f"  Removing {excess} excess customers...")

        stmt = select(Customer.id).order_by(Customer.id.desc()).limit(excess)
        result = await session.execute(stmt)
        ids_to_delete = [row[0] for row in result.fetchall()]

        await session.execute(delete(Customer).where(Customer.id.in_(ids_to_delete)))
        await session.commit()

    elif current_count < target_count:
        # Create new customers
        needed = target_count - current_count
        print(f"  Creating {needed} new customers...")

        used_combos = set()
        # Get existing name combos
        result = await session.execute(select(Customer.first_name, Customer.last_name))
        for row in result.fetchall():
            used_combos.add((row[0], row[1]))

        new_customers = []
        attempts = 0
        while len(new_customers) < needed and attempts < 1000:
            attempts += 1
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)

            # Skip Stephanie Burns
            if first.lower() == 'stephanie' and last.lower() == 'burns':
                continue

            if (first, last) in used_combos:
                continue

            used_combos.add((first, last))
            city, state, postal = random.choice(CITIES)

            customer = Customer(
                first_name=first,
                last_name=last,
                email=random_email(first, last),
                phone=random_phone(),
                address_line1=random_address(),
                city=city,
                state=state,
                postal_code=postal,
                is_active=random.random() > 0.1,  # 90% active
                lead_source=random.choice(LEAD_SOURCES),
                customer_type=random.choice(CUSTOMER_TYPES),
                tank_size_gallons=random.choice(TANK_SIZES),
                number_of_tanks=random.randint(1, 3),
                system_type=random.choice(SYSTEM_TYPES),
                subdivision=random.choice(SUBDIVISIONS),
                created_at=datetime.now() - timedelta(days=random.randint(30, 730)),
                updated_at=datetime.now() - timedelta(days=random.randint(0, 30)),
                latitude=Decimal(str(round(random.uniform(29.5, 30.5), 6))),
                longitude=Decimal(str(round(random.uniform(-95.8, -95.0), 6)))
            )
            new_customers.append(customer)

        session.add_all(new_customers)
        await session.commit()

    # Return all customer IDs
    result = await session.execute(select(Customer.id))
    customer_ids = [row[0] for row in result.fetchall()]
    print(f"  Final customer count: {len(customer_ids)}")
    return customer_ids


async def create_segments(session: AsyncSession) -> list[int]:
    """Create Customer Success segments."""
    print("\nCreating segments...")

    segments_data = [
        {
            "name": "High Value Accounts",
            "description": "Customers with high contract value and strategic importance",
            "color": "#10B981",
            "segment_type": "dynamic",
            "rules": {"and": [{"field": "estimated_value", "op": "gte", "value": 5000}]},
            "priority": 10
        },
        {
            "name": "At Risk - Low Engagement",
            "description": "Customers showing signs of disengagement",
            "color": "#EF4444",
            "segment_type": "dynamic",
            "rules": {"and": [{"field": "health_score", "op": "lt", "value": 50}]},
            "priority": 5
        },
        {
            "name": "Growth Candidates",
            "description": "Healthy accounts with expansion potential",
            "color": "#3B82F6",
            "segment_type": "dynamic",
            "rules": {"and": [
                {"field": "health_score", "op": "gte", "value": 70},
                {"field": "tank_count", "op": "lt", "value": 3}
            ]},
            "priority": 15
        },
        {
            "name": "New Customers (< 90 days)",
            "description": "Recently onboarded customers requiring attention",
            "color": "#8B5CF6",
            "segment_type": "dynamic",
            "rules": {"and": [{"field": "days_since_signup", "op": "lt", "value": 90}]},
            "priority": 20
        },
        {
            "name": "Champions",
            "description": "Highly engaged advocates",
            "color": "#F59E0B",
            "segment_type": "dynamic",
            "rules": {"and": [
                {"field": "health_score", "op": "gte", "value": 85},
                {"field": "nps_score", "op": "gte", "value": 9}
            ]},
            "priority": 25
        },
        {
            "name": "Commercial Accounts",
            "description": "Business and commercial customers",
            "color": "#6366F1",
            "segment_type": "dynamic",
            "rules": {"and": [{"field": "customer_type", "op": "eq", "value": "Commercial"}]},
            "priority": 30
        }
    ]

    segment_ids = []
    for data in segments_data:
        segment = Segment(**data)
        session.add(segment)
        await session.flush()
        segment_ids.append(segment.id)
        print(f"  Created segment: {data['name']}")

    await session.commit()
    return segment_ids


async def create_health_scores(session: AsyncSession, customer_ids: list[int]):
    """Create health scores for all customers."""
    print("\nCreating health scores...")

    health_scores = []
    for cid in customer_ids:
        # Generate varied but realistic scores
        base_score = random.gauss(65, 20)  # Mean 65, std dev 20
        base_score = max(10, min(100, int(base_score)))  # Clamp 10-100

        # Component scores with some correlation to base
        product_adoption = max(0, min(100, int(base_score + random.gauss(0, 15))))
        engagement = max(0, min(100, int(base_score + random.gauss(0, 15))))
        relationship = max(0, min(100, int(base_score + random.gauss(5, 10))))
        financial = max(0, min(100, int(base_score + random.gauss(0, 12))))
        support = max(0, min(100, int(base_score + random.gauss(-5, 18))))

        # Calculate weighted overall
        overall = int(
            product_adoption * 0.30 +
            engagement * 0.25 +
            relationship * 0.15 +
            financial * 0.20 +
            support * 0.10
        )

        # Determine status
        if overall >= 70:
            status = 'healthy'
        elif overall >= 40:
            status = 'at_risk'
        else:
            status = 'critical'

        # Churn probability inversely related to score
        churn_prob = max(0, min(1, (100 - overall) / 100 * 0.8 + random.uniform(-0.1, 0.1)))

        # Determine trend
        trend_roll = random.random()
        if trend_roll < 0.3:
            trend = 'improving'
            change_7d = random.randint(1, 10)
            change_30d = random.randint(3, 20)
        elif trend_roll < 0.6:
            trend = 'stable'
            change_7d = random.randint(-3, 3)
            change_30d = random.randint(-5, 5)
        else:
            trend = 'declining'
            change_7d = random.randint(-10, -1)
            change_30d = random.randint(-20, -3)

        hs = HealthScore(
            customer_id=cid,
            overall_score=overall,
            health_status=status,
            product_adoption_score=product_adoption,
            engagement_score=engagement,
            relationship_score=relationship,
            financial_score=financial,
            support_score=support,
            churn_probability=round(churn_prob, 3),
            expansion_probability=round(random.uniform(0, 0.5) if status == 'healthy' else random.uniform(0, 0.2), 3),
            days_since_last_login=random.randint(0, 90),
            days_to_renewal=random.randint(30, 365),
            active_users_count=random.randint(1, 10),
            licensed_users_count=random.randint(1, 15),
            feature_adoption_pct=round(random.uniform(0.2, 0.95), 2),
            score_trend=trend,
            score_change_7d=change_7d,
            score_change_30d=change_30d,
            has_open_escalation=random.random() < 0.1,
            champion_at_risk=random.random() < 0.05,
            payment_issues=random.random() < 0.08,
            calculated_at=datetime.now() - timedelta(hours=random.randint(0, 24))
        )
        health_scores.append(hs)

    session.add_all(health_scores)
    await session.commit()
    print(f"  Created {len(health_scores)} health scores")


async def assign_customers_to_segments(session: AsyncSession, customer_ids: list[int], segment_ids: list[int]):
    """Assign customers to segments based on simulated criteria."""
    print("\nAssigning customers to segments...")

    # Get health scores for decision making
    result = await session.execute(
        select(HealthScore.customer_id, HealthScore.overall_score, HealthScore.health_status)
    )
    health_data = {row[0]: (row[1], row[2]) for row in result.fetchall()}

    memberships = []
    segment_counts = {sid: 0 for sid in segment_ids}

    for cid in customer_ids:
        score, status = health_data.get(cid, (50, 'at_risk'))

        # Assign based on score/status
        assigned_segments = []

        # High Value (segment 0) - top 20%
        if score >= 75:
            assigned_segments.append(segment_ids[0])

        # At Risk (segment 1) - below 50
        if score < 50:
            assigned_segments.append(segment_ids[1])

        # Growth Candidates (segment 2) - 60-85 score
        if 60 <= score <= 85:
            if random.random() < 0.4:
                assigned_segments.append(segment_ids[2])

        # New Customers (segment 3) - random 15%
        if random.random() < 0.15:
            assigned_segments.append(segment_ids[3])

        # Champions (segment 4) - top 10%
        if score >= 85:
            assigned_segments.append(segment_ids[4])

        # Commercial (segment 5) - random 25%
        if random.random() < 0.25:
            assigned_segments.append(segment_ids[5])

        for sid in assigned_segments:
            membership = CustomerSegment(
                customer_id=cid,
                segment_id=sid,
                is_active=True,
                entry_reason="Initial segmentation",
                added_by="system:seed_script"
            )
            memberships.append(membership)
            segment_counts[sid] += 1

    session.add_all(memberships)

    # Update segment counts
    for sid, count in segment_counts.items():
        result = await session.execute(select(Segment).where(Segment.id == sid))
        segment = result.scalar_one()
        segment.customer_count = count

    await session.commit()
    print(f"  Created {len(memberships)} segment memberships")


async def create_playbooks(session: AsyncSession, segment_ids: list[int]) -> list[int]:
    """Create playbooks with steps."""
    print("\nCreating playbooks...")

    playbooks_data = [
        {
            "name": "New Customer Onboarding",
            "description": "30-day onboarding program for new customers",
            "category": "onboarding",
            "trigger_type": "segment_entry",
            "trigger_segment_id": segment_ids[3],  # New Customers segment
            "priority": "high",
            "target_completion_days": 30,
            "steps": [
                {"name": "Welcome Call", "step_type": "call", "days_from_start": 0, "due_days": 1},
                {"name": "Send Welcome Kit", "step_type": "email", "days_from_start": 1, "due_days": 2},
                {"name": "Schedule Training", "step_type": "meeting", "days_from_start": 3, "due_days": 5},
                {"name": "First Check-in Call", "step_type": "call", "days_from_start": 7, "due_days": 3},
                {"name": "Feature Adoption Review", "step_type": "review", "days_from_start": 14, "due_days": 3},
                {"name": "30-Day Success Review", "step_type": "meeting", "days_from_start": 28, "due_days": 5}
            ]
        },
        {
            "name": "At-Risk Intervention",
            "description": "Immediate intervention for at-risk accounts",
            "category": "churn_risk",
            "trigger_type": "health_threshold",
            "trigger_health_threshold": 50,
            "trigger_health_direction": "below",
            "priority": "critical",
            "target_completion_days": 14,
            "steps": [
                {"name": "Urgent Outreach Call", "step_type": "call", "days_from_start": 0, "due_days": 1},
                {"name": "Internal Risk Review", "step_type": "internal_task", "days_from_start": 0, "due_days": 1},
                {"name": "Executive Sponsor Email", "step_type": "email", "days_from_start": 1, "due_days": 1},
                {"name": "Recovery Plan Meeting", "step_type": "meeting", "days_from_start": 3, "due_days": 2},
                {"name": "Follow-up Check", "step_type": "call", "days_from_start": 7, "due_days": 2},
                {"name": "Health Score Re-evaluation", "step_type": "review", "days_from_start": 14, "due_days": 1}
            ]
        },
        {
            "name": "Quarterly Business Review",
            "description": "Standard QBR process for all accounts",
            "category": "qbr",
            "trigger_type": "scheduled",
            "priority": "medium",
            "target_completion_days": 21,
            "steps": [
                {"name": "QBR Prep & Data Gathering", "step_type": "internal_task", "days_from_start": 0, "due_days": 5},
                {"name": "Schedule QBR Meeting", "step_type": "meeting", "days_from_start": 5, "due_days": 3},
                {"name": "Prepare Presentation", "step_type": "documentation", "days_from_start": 7, "due_days": 5},
                {"name": "Conduct QBR", "step_type": "meeting", "days_from_start": 14, "due_days": 3},
                {"name": "Send Follow-up & Action Items", "step_type": "email", "days_from_start": 15, "due_days": 2},
                {"name": "Update Success Plan", "step_type": "documentation", "days_from_start": 18, "due_days": 3}
            ]
        },
        {
            "name": "Expansion Opportunity",
            "description": "Process for identified expansion opportunities",
            "category": "expansion",
            "trigger_type": "manual",
            "priority": "high",
            "target_completion_days": 45,
            "steps": [
                {"name": "Opportunity Assessment", "step_type": "review", "days_from_start": 0, "due_days": 2},
                {"name": "Internal Alignment Call", "step_type": "internal_task", "days_from_start": 2, "due_days": 2},
                {"name": "Customer Discovery Call", "step_type": "call", "days_from_start": 5, "due_days": 3},
                {"name": "Prepare Proposal", "step_type": "documentation", "days_from_start": 10, "due_days": 5},
                {"name": "Proposal Presentation", "step_type": "meeting", "days_from_start": 18, "due_days": 5},
                {"name": "Negotiation Follow-up", "step_type": "call", "days_from_start": 25, "due_days": 5},
                {"name": "Close or Defer Decision", "step_type": "review", "days_from_start": 35, "due_days": 10}
            ]
        },
        {
            "name": "Renewal Process",
            "description": "90-day renewal preparation and execution",
            "category": "renewal",
            "trigger_type": "days_to_renewal",
            "trigger_days_to_renewal": 90,
            "priority": "high",
            "target_completion_days": 90,
            "steps": [
                {"name": "Renewal Kickoff Internal", "step_type": "internal_task", "days_from_start": 0, "due_days": 3},
                {"name": "Account Health Review", "step_type": "review", "days_from_start": 3, "due_days": 5},
                {"name": "Renewal Discussion Call", "step_type": "call", "days_from_start": 10, "due_days": 5},
                {"name": "Send Renewal Proposal", "step_type": "email", "days_from_start": 20, "due_days": 5},
                {"name": "Negotiation Meeting", "step_type": "meeting", "days_from_start": 35, "due_days": 10},
                {"name": "Contract Finalization", "step_type": "documentation", "days_from_start": 50, "due_days": 15},
                {"name": "Renewal Celebration", "step_type": "email", "days_from_start": 75, "due_days": 15}
            ]
        }
    ]

    playbook_ids = []
    for pb_data in playbooks_data:
        steps_data = pb_data.pop("steps")
        playbook = Playbook(**pb_data)
        session.add(playbook)
        await session.flush()
        playbook_ids.append(playbook.id)

        for i, step_data in enumerate(steps_data, 1):
            step = PlaybookStep(
                playbook_id=playbook.id,
                step_order=i,
                **step_data
            )
            session.add(step)

        print(f"  Created playbook: {pb_data['name']} with {len(steps_data)} steps")

    await session.commit()
    return playbook_ids


async def create_journeys(session: AsyncSession, segment_ids: list[int]) -> list[int]:
    """Create journeys with steps."""
    print("\nCreating journeys...")

    journeys_data = [
        {
            "name": "Onboarding Journey",
            "description": "Automated 60-day onboarding experience",
            "journey_type": "onboarding",
            "trigger_type": "segment_entry",
            "trigger_segment_id": segment_ids[3],
            "goal_metric": "feature_adoption",
            "goal_target": 70.0,
            "goal_timeframe_days": 60,
            "steps": [
                {"name": "Welcome Email", "step_type": "email", "step_order": 1, "wait_days": 0},
                {"name": "Wait 2 Days", "step_type": "wait", "step_order": 2, "wait_days": 2},
                {"name": "Feature Tour Prompt", "step_type": "in_app_message", "step_order": 3, "wait_days": 0},
                {"name": "Wait 5 Days", "step_type": "wait", "step_order": 4, "wait_days": 5},
                {"name": "Check Feature Usage", "step_type": "condition", "step_order": 5, "wait_days": 0},
                {"name": "Training Reminder", "step_type": "email", "step_order": 6, "wait_days": 0},
                {"name": "Wait 7 Days", "step_type": "wait", "step_order": 7, "wait_days": 7},
                {"name": "CSM Check-in Task", "step_type": "human_touchpoint", "step_order": 8, "wait_days": 0, "task_due_days": 3},
                {"name": "Wait 14 Days", "step_type": "wait", "step_order": 9, "wait_days": 14},
                {"name": "Success Milestone Email", "step_type": "email", "step_order": 10, "wait_days": 0}
            ]
        },
        {
            "name": "Risk Mitigation Journey",
            "description": "Automated touches for at-risk accounts",
            "journey_type": "risk_mitigation",
            "trigger_type": "segment_entry",
            "trigger_segment_id": segment_ids[1],
            "goal_metric": "health_score",
            "goal_target": 60.0,
            "goal_timeframe_days": 30,
            "steps": [
                {"name": "Risk Alert Email", "step_type": "email", "step_order": 1, "wait_days": 0},
                {"name": "Create Intervention Task", "step_type": "task", "step_order": 2, "wait_days": 0, "task_due_days": 1},
                {"name": "Wait 3 Days", "step_type": "wait", "step_order": 3, "wait_days": 3},
                {"name": "Check Health Score", "step_type": "health_check", "step_order": 4, "wait_days": 0},
                {"name": "Support Offer Email", "step_type": "email", "step_order": 5, "wait_days": 0},
                {"name": "Wait 7 Days", "step_type": "wait", "step_order": 6, "wait_days": 7},
                {"name": "Escalation Review Task", "step_type": "human_touchpoint", "step_order": 7, "wait_days": 0, "task_due_days": 2}
            ]
        },
        {
            "name": "Advocacy Development",
            "description": "Nurture champions into advocates",
            "journey_type": "advocacy",
            "trigger_type": "segment_entry",
            "trigger_segment_id": segment_ids[4],
            "goal_metric": "nps_score",
            "goal_target": 10.0,
            "goal_timeframe_days": 90,
            "steps": [
                {"name": "Thank You Email", "step_type": "email", "step_order": 1, "wait_days": 0},
                {"name": "Wait 7 Days", "step_type": "wait", "step_order": 2, "wait_days": 7},
                {"name": "Referral Program Invite", "step_type": "email", "step_order": 3, "wait_days": 0},
                {"name": "Wait 14 Days", "step_type": "wait", "step_order": 4, "wait_days": 14},
                {"name": "Case Study Request", "step_type": "email", "step_order": 5, "wait_days": 0},
                {"name": "CSM Personal Outreach", "step_type": "human_touchpoint", "step_order": 6, "wait_days": 0, "task_due_days": 5},
                {"name": "Wait 30 Days", "step_type": "wait", "step_order": 7, "wait_days": 30},
                {"name": "NPS Survey", "step_type": "email", "step_order": 8, "wait_days": 0}
            ]
        }
    ]

    journey_ids = []
    for j_data in journeys_data:
        steps_data = j_data.pop("steps")
        journey = Journey(**j_data)
        session.add(journey)
        await session.flush()
        journey_ids.append(journey.id)

        for step_data in steps_data:
            step = JourneyStep(
                journey_id=journey.id,
                **step_data
            )
            session.add(step)

        print(f"  Created journey: {j_data['name']} with {len(steps_data)} steps")

    await session.commit()
    return journey_ids


async def create_tasks(session: AsyncSession, customer_ids: list[int]):
    """Create CS tasks for customers."""
    print("\nCreating tasks...")

    task_templates = [
        {"title": "Quarterly check-in call", "task_type": "call", "category": "relationship", "priority": "medium"},
        {"title": "Review usage metrics", "task_type": "review", "category": "adoption", "priority": "low"},
        {"title": "Send training resources", "task_type": "email", "category": "onboarding", "priority": "medium"},
        {"title": "Schedule QBR", "task_type": "meeting", "category": "relationship", "priority": "high"},
        {"title": "Follow up on support ticket", "task_type": "follow_up", "category": "support", "priority": "high"},
        {"title": "Renewal discussion", "task_type": "call", "category": "retention", "priority": "critical"},
        {"title": "Upsell opportunity review", "task_type": "review", "category": "expansion", "priority": "medium"},
        {"title": "Product feedback session", "task_type": "meeting", "category": "relationship", "priority": "medium"},
        {"title": "Invoice clarification", "task_type": "call", "category": "administrative", "priority": "low"},
        {"title": "Executive sponsor intro", "task_type": "meeting", "category": "relationship", "priority": "high"}
    ]

    tasks = []
    statuses = ['pending', 'in_progress', 'completed', 'blocked', 'snoozed']
    status_weights = [0.3, 0.2, 0.35, 0.05, 0.1]

    # Create 2-5 tasks per customer (randomly)
    for cid in customer_ids:
        num_tasks = random.randint(1, 4)
        selected_templates = random.sample(task_templates, min(num_tasks, len(task_templates)))

        for template in selected_templates:
            status = random.choices(statuses, weights=status_weights)[0]
            due_date = date.today() + timedelta(days=random.randint(-10, 30))

            task = CSTask(
                customer_id=cid,
                title=template["title"],
                description=f"Auto-generated task for customer {cid}",
                task_type=template["task_type"],
                category=template["category"],
                priority=template["priority"],
                status=status,
                due_date=due_date,
                source="seed_script",
                created_at=datetime.now() - timedelta(days=random.randint(1, 30))
            )

            if status == 'completed':
                task.completed_at = datetime.now() - timedelta(days=random.randint(0, 5))
                task.outcome = random.choice(['successful', 'rescheduled', 'no_response'])

            tasks.append(task)

    session.add_all(tasks)
    await session.commit()
    print(f"  Created {len(tasks)} tasks")


async def create_touchpoints(session: AsyncSession, customer_ids: list[int]):
    """Create touchpoint history for customers."""
    print("\nCreating touchpoints...")

    touchpoint_types = [
        'email_sent', 'email_opened', 'call_outbound', 'call_inbound',
        'meeting_held', 'support_ticket_opened', 'support_ticket_resolved',
        'product_login', 'feature_usage', 'nps_response'
    ]

    sentiments = ['positive', 'neutral', 'negative']
    sentiment_weights = [0.5, 0.35, 0.15]

    touchpoints = []

    for cid in customer_ids:
        # Create 3-10 touchpoints per customer
        num_touchpoints = random.randint(3, 10)

        for _ in range(num_touchpoints):
            tp_type = random.choice(touchpoint_types)
            occurred = datetime.now() - timedelta(days=random.randint(1, 180))

            touchpoint = Touchpoint(
                customer_id=cid,
                touchpoint_type=tp_type,
                channel=random.choice(['email', 'phone', 'in_app', 'meeting']),
                direction='outbound' if 'sent' in tp_type or 'outbound' in tp_type else 'inbound',
                sentiment=random.choices(sentiments, weights=sentiment_weights)[0] if 'call' in tp_type or 'meeting' in tp_type else None,
                occurred_at=occurred,
                source='seed_script',
                is_automated='email' in tp_type or 'product' in tp_type or 'feature' in tp_type
            )

            if 'meeting' in tp_type:
                touchpoint.duration_minutes = random.randint(15, 60)

            touchpoints.append(touchpoint)

    session.add_all(touchpoints)
    await session.commit()
    print(f"  Created {len(touchpoints)} touchpoints")


async def create_journey_enrollments(session: AsyncSession, customer_ids: list[int], journey_ids: list[int]):
    """Enroll some customers in journeys."""
    print("\nCreating journey enrollments...")

    enrollments = []

    # Enroll random 30% of customers in onboarding journey
    onboarding_customers = random.sample(customer_ids, int(len(customer_ids) * 0.3))
    for cid in onboarding_customers:
        enrollment = JourneyEnrollment(
            journey_id=journey_ids[0],  # Onboarding
            customer_id=cid,
            status=random.choice(['active', 'completed']),
            steps_completed=random.randint(1, 8),
            enrolled_by='system:segment_trigger'
        )
        enrollments.append(enrollment)

    # Enroll random 15% in risk mitigation
    risk_customers = random.sample(customer_ids, int(len(customer_ids) * 0.15))
    for cid in risk_customers:
        enrollment = JourneyEnrollment(
            journey_id=journey_ids[1],  # Risk Mitigation
            customer_id=cid,
            status=random.choice(['active', 'active', 'completed']),
            steps_completed=random.randint(1, 5),
            enrolled_by='system:health_trigger'
        )
        enrollments.append(enrollment)

    # Enroll random 10% in advocacy
    advocate_customers = random.sample(customer_ids, int(len(customer_ids) * 0.10))
    for cid in advocate_customers:
        enrollment = JourneyEnrollment(
            journey_id=journey_ids[2],  # Advocacy
            customer_id=cid,
            status='active',
            steps_completed=random.randint(1, 4),
            enrolled_by='system:segment_trigger'
        )
        enrollments.append(enrollment)

    session.add_all(enrollments)
    await session.commit()
    print(f"  Created {len(enrollments)} journey enrollments")


async def create_playbook_executions(session: AsyncSession, customer_ids: list[int], playbook_ids: list[int]):
    """Create playbook executions for some customers."""
    print("\nCreating playbook executions...")

    executions = []

    # Execute onboarding playbook for 25% of customers
    onboarding_customers = random.sample(customer_ids, int(len(customer_ids) * 0.25))
    for cid in onboarding_customers:
        execution = PlaybookExecution(
            playbook_id=playbook_ids[0],  # Onboarding
            customer_id=cid,
            status=random.choice(['active', 'completed', 'completed']),
            steps_completed=random.randint(1, 6),
            steps_total=6,
            triggered_by='system:segment_entry'
        )
        executions.append(execution)

    # Execute at-risk playbook for 15% of customers
    risk_customers = random.sample(customer_ids, int(len(customer_ids) * 0.15))
    for cid in risk_customers:
        execution = PlaybookExecution(
            playbook_id=playbook_ids[1],  # At-Risk
            customer_id=cid,
            status=random.choice(['active', 'active', 'completed']),
            steps_completed=random.randint(1, 4),
            steps_total=6,
            triggered_by='system:health_threshold'
        )
        executions.append(execution)

    # QBR for 20% of customers
    qbr_customers = random.sample(customer_ids, int(len(customer_ids) * 0.20))
    for cid in qbr_customers:
        execution = PlaybookExecution(
            playbook_id=playbook_ids[2],  # QBR
            customer_id=cid,
            status=random.choice(['active', 'completed']),
            steps_completed=random.randint(1, 6),
            steps_total=6,
            triggered_by='user:scheduled'
        )
        executions.append(execution)

    session.add_all(executions)
    await session.commit()
    print(f"  Created {len(executions)} playbook executions")


async def print_summary(session: AsyncSession):
    """Print summary of created data."""
    print("\n" + "="*50)
    print("SEED DATA SUMMARY")
    print("="*50)

    # Customers
    result = await session.execute(select(func.count(Customer.id)))
    print(f"Customers: {result.scalar()}")

    # Health Scores
    result = await session.execute(select(func.count(HealthScore.id)))
    print(f"Health Scores: {result.scalar()}")

    # Health score distribution
    result = await session.execute(
        select(HealthScore.health_status, func.count(HealthScore.id))
        .group_by(HealthScore.health_status)
    )
    print("  Health Status Distribution:")
    for status, count in result.fetchall():
        print(f"    - {status}: {count}")

    # Segments
    result = await session.execute(select(func.count(Segment.id)))
    print(f"Segments: {result.scalar()}")

    # Customer Segments
    result = await session.execute(select(func.count(CustomerSegment.id)))
    print(f"Customer-Segment Memberships: {result.scalar()}")

    # Playbooks
    result = await session.execute(select(func.count(Playbook.id)))
    print(f"Playbooks: {result.scalar()}")

    # Playbook Steps
    result = await session.execute(select(func.count(PlaybookStep.id)))
    print(f"Playbook Steps: {result.scalar()}")

    # Playbook Executions
    result = await session.execute(select(func.count(PlaybookExecution.id)))
    print(f"Playbook Executions: {result.scalar()}")

    # Journeys
    result = await session.execute(select(func.count(Journey.id)))
    print(f"Journeys: {result.scalar()}")

    # Journey Steps
    result = await session.execute(select(func.count(JourneyStep.id)))
    print(f"Journey Steps: {result.scalar()}")

    # Journey Enrollments
    result = await session.execute(select(func.count(JourneyEnrollment.id)))
    print(f"Journey Enrollments: {result.scalar()}")

    # Tasks
    result = await session.execute(select(func.count(CSTask.id)))
    print(f"CS Tasks: {result.scalar()}")

    # Touchpoints
    result = await session.execute(select(func.count(Touchpoint.id)))
    print(f"Touchpoints: {result.scalar()}")

    print("="*50)
    print("Seed data creation complete!")
    print("="*50)


async def main():
    """Main seed function."""
    print("="*50)
    print("Customer Success Platform - Seed Script")
    print("="*50)

    async with async_session_maker() as session:
        # Clear existing CS data
        await clear_customer_success_data(session)

        # Manage customers (100 max, remove Stephanie Burns)
        customer_ids = await manage_customers(session, target_count=100)

        # Create segments
        segment_ids = await create_segments(session)

        # Create health scores for all customers
        await create_health_scores(session, customer_ids)

        # Assign customers to segments
        await assign_customers_to_segments(session, customer_ids, segment_ids)

        # Create playbooks with steps
        playbook_ids = await create_playbooks(session, segment_ids)

        # Create journeys with steps
        journey_ids = await create_journeys(session, segment_ids)

        # Create tasks
        await create_tasks(session, customer_ids)

        # Create touchpoints
        await create_touchpoints(session, customer_ids)

        # Create journey enrollments
        await create_journey_enrollments(session, customer_ids, journey_ids)

        # Create playbook executions
        await create_playbook_executions(session, customer_ids, playbook_ids)

        # Print summary
        await print_summary(session)


if __name__ == "__main__":
    asyncio.run(main())
