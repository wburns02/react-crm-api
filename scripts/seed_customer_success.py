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
    """Create world-class playbooks with 2025-2026 best practices."""
    print("\nCreating world-class playbooks (2025-2026 Best Practices)...")

    playbooks_data = [
        # ============================================================
        # PLAYBOOK 1: ENTERPRISE ONBOARDING (90-Day Time-to-Value)
        # ============================================================
        {
            "name": "Enterprise Customer Onboarding",
            "description": "90-day comprehensive onboarding program optimized for time-to-value. Incorporates 2025 best practices: digital-first approach, AI-powered insights, proactive touchpoints, and milestone-based success tracking.",
            "category": "onboarding",
            "trigger_type": "segment_entry",
            "trigger_segment_id": segment_ids[3],  # New Customers segment
            "priority": "high",
            "target_completion_days": 90,
            "estimated_hours": 12.0,
            "success_criteria": {"feature_adoption": 70, "health_score": 75, "first_value_achieved": True},
            "steps": [
                {
                    "name": "Pre-Kickoff Internal Prep",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Review sales handoff notes, research customer company, prepare kickoff deck, provision accounts",
                    "instructions": "1. Review CRM notes from sales\n2. Research company size, industry, recent news\n3. Identify key stakeholders and their goals\n4. Customize kickoff presentation\n5. Ensure all user accounts are provisioned",
                    "required_outcomes": ["handoff_reviewed", "stakeholders_identified", "accounts_provisioned"]
                },
                {
                    "name": "Welcome Email & Success Plan",
                    "step_type": "email",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Send personalized welcome email with success plan, meeting invite, and resource links",
                    "email_subject": "Welcome to ECBTX - Your Success Journey Begins",
                    "email_body_template": "Welcome {customer_name}! I'm {csm_name}, your dedicated Customer Success Manager. Let's schedule your kickoff call to align on your goals and set you up for success.",
                    "instructions": "Personalize with customer's specific goals from sales handoff. Include calendar link for kickoff scheduling."
                },
                {
                    "name": "Kickoff Call - Goal Alignment",
                    "step_type": "meeting",
                    "days_from_start": 3,
                    "due_days": 5,
                    "description": "60-minute strategic kickoff to establish goals, success criteria, and communication preferences",
                    "meeting_agenda_template": "1. Introductions (10 min)\n2. Customer Goals & Success Criteria (15 min)\n3. Solution Overview & How We Help (10 min)\n4. Onboarding Timeline & Milestones (10 min)\n5. Technical Requirements (10 min)\n6. Q&A & Next Steps (5 min)",
                    "talk_track": "What does success look like in 90 days? 6 months? What metrics will you use to measure our impact? What's the biggest pain point we need to solve first?",
                    "required_outcomes": ["goals_documented", "success_metrics_defined", "timeline_agreed"]
                },
                {
                    "name": "Technical Setup & Configuration",
                    "step_type": "internal_task",
                    "days_from_start": 5,
                    "due_days": 5,
                    "description": "Complete environment setup, data migration, integrations, and system configuration",
                    "instructions": "1. Configure customer environment\n2. Complete data import/migration\n3. Set up integrations with existing tools\n4. Configure user permissions and roles\n5. Verify all systems operational"
                },
                {
                    "name": "Admin Training Session",
                    "step_type": "training",
                    "days_from_start": 10,
                    "due_days": 3,
                    "description": "90-minute deep dive training for admin users on system configuration and management",
                    "meeting_agenda_template": "1. Admin Dashboard Overview (15 min)\n2. User Management (15 min)\n3. System Configuration (20 min)\n4. Reporting & Analytics (20 min)\n5. Best Practices & Tips (15 min)\n6. Q&A (5 min)"
                },
                {
                    "name": "End User Training",
                    "step_type": "training",
                    "days_from_start": 14,
                    "due_days": 5,
                    "description": "60-minute core training session for all users on daily workflows",
                    "instructions": "Focus on the 3-5 most critical features for their use case. Provide recorded session for future reference."
                },
                {
                    "name": "Week 2 Check-in Call",
                    "step_type": "call",
                    "days_from_start": 14,
                    "due_days": 3,
                    "description": "Quick pulse check on adoption progress, address questions, remove blockers",
                    "talk_track": "How is the team finding the platform? Any questions from training? What's working well? What challenges are you facing?"
                },
                {
                    "name": "First Value Milestone Review",
                    "step_type": "review",
                    "days_from_start": 21,
                    "due_days": 3,
                    "description": "Review first value achievement - has customer completed their first key workflow?",
                    "instructions": "Check if customer has: 1) Logged first service call 2) Generated first invoice 3) Completed first scheduled job. Document the 'aha moment'."
                },
                {
                    "name": "30-Day Success Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 28,
                    "due_days": 5,
                    "description": "Formal 30-day review of progress, adoption metrics, and goal tracking",
                    "meeting_agenda_template": "1. Progress Review vs Goals (15 min)\n2. Adoption Metrics Analysis (10 min)\n3. Feature Usage Deep Dive (10 min)\n4. Roadmap & Next 60 Days (10 min)\n5. Action Items & Commitments (5 min)",
                    "talk_track": "Let's review your progress toward the goals we set. Here's what the data shows about your team's adoption..."
                },
                {
                    "name": "Champion Enablement Session",
                    "step_type": "training",
                    "days_from_start": 35,
                    "due_days": 5,
                    "description": "Advanced training for power users/champions to drive internal adoption",
                    "instructions": "Identify 1-2 champions. Provide advanced features training, internal advocacy toolkit, and escalation path direct to CSM."
                },
                {
                    "name": "60-Day Health Check",
                    "step_type": "call",
                    "days_from_start": 60,
                    "due_days": 5,
                    "description": "Mid-point check-in focusing on adoption acceleration and expansion opportunities",
                    "talk_track": "We're 2/3 through onboarding. Let's assess where you are vs. goals and identify any gaps to address in the final 30 days."
                },
                {
                    "name": "90-Day Graduation Review",
                    "step_type": "meeting",
                    "days_from_start": 85,
                    "due_days": 7,
                    "description": "Formal onboarding completion meeting - transition to ongoing success relationship",
                    "meeting_agenda_template": "1. Goals Achievement Summary (15 min)\n2. ROI & Value Delivered (10 min)\n3. Ongoing Cadence & Support (10 min)\n4. Expansion Opportunities (10 min)\n5. NPS Survey & Testimonial Request (5 min)",
                    "required_outcomes": ["onboarding_complete", "health_score_green", "cadence_established"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 2: CRITICAL CHURN PREVENTION (14-Day Rapid Response)
        # ============================================================
        {
            "name": "Critical At-Risk Intervention",
            "description": "14-day rapid response playbook for customers showing churn signals. AI-triggered when health score drops below threshold. Focuses on immediate stabilization, root cause analysis, and recovery plan execution.",
            "category": "churn_risk",
            "trigger_type": "health_threshold",
            "trigger_health_threshold": 50,
            "trigger_health_direction": "below",
            "priority": "critical",
            "target_completion_days": 14,
            "estimated_hours": 8.0,
            "success_criteria": {"health_score_increase": 20, "engagement_restored": True, "risk_mitigated": True},
            "steps": [
                {
                    "name": "Immediate Risk Assessment",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Analyze all risk signals: usage decline, support tickets, payment issues, champion changes",
                    "instructions": "Pull 30/60/90 day usage data. Review support history. Check billing status. Identify what triggered the health drop. Document findings.",
                    "required_outcomes": ["risk_factors_identified", "root_cause_hypothesis"]
                },
                {
                    "name": "Urgent Customer Outreach",
                    "step_type": "call",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Same-day call to primary contact. Show concern, not alarm. Seek to understand.",
                    "talk_track": "I noticed some changes in your account and wanted to check in personally. How are things going? Is there anything concerning you that I should know about? What challenges are you facing right now?",
                    "instructions": "Be empathetic, not defensive. Listen more than talk. Don't make promises yet - gather information."
                },
                {
                    "name": "Internal Escalation Brief",
                    "step_type": "internal_task",
                    "days_from_start": 1,
                    "due_days": 1,
                    "description": "Create escalation brief for CS leadership. High-value accounts require VP notification.",
                    "instructions": "Document: Customer value, risk level, root cause, proposed recovery actions, resources needed. Submit to CS Manager for review."
                },
                {
                    "name": "Executive Sponsor Engagement",
                    "step_type": "email",
                    "days_from_start": 2,
                    "due_days": 1,
                    "description": "Reach out to executive sponsor or secondary contact if primary unresponsive",
                    "email_subject": "Partnership Review Request - {company_name}",
                    "email_body_template": "I'm reaching out to schedule a brief discussion about your team's experience with our platform. We value your partnership and want to ensure we're meeting your needs.",
                    "instructions": "For high-value accounts, have your VP co-sign or send directly. Multi-thread the account."
                },
                {
                    "name": "Recovery Plan Development",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 2,
                    "description": "Create detailed recovery plan with specific actions, owners, and success criteria",
                    "instructions": "Include: Root cause summary, specific recovery actions with owners and dates, customer commitments needed, success metrics, escalation triggers, check-in schedule."
                },
                {
                    "name": "Recovery Plan Presentation",
                    "step_type": "meeting",
                    "days_from_start": 5,
                    "due_days": 2,
                    "description": "Present recovery plan to customer. Get buy-in on mutual commitments.",
                    "meeting_agenda_template": "1. Acknowledge the Situation (5 min)\n2. Root Cause Discussion (10 min)\n3. Our Commitment & Recovery Plan (15 min)\n4. Your Commitments Needed (10 min)\n5. Success Metrics & Timeline (5 min)\n6. Next Steps (5 min)",
                    "talk_track": "We've identified what went wrong and here's our plan to fix it. We're committed to your success, but we need your partnership on a few things..."
                },
                {
                    "name": "Day 7 Progress Check",
                    "step_type": "call",
                    "days_from_start": 7,
                    "due_days": 1,
                    "description": "Weekly check-in on recovery progress. Address new blockers immediately.",
                    "talk_track": "Let's review our progress this week. What's improved? What's still challenging? How can I help accelerate the recovery?"
                },
                {
                    "name": "Support & Training Intervention",
                    "step_type": "training",
                    "days_from_start": 8,
                    "due_days": 3,
                    "description": "If adoption is the issue, provide intensive re-training or support intervention",
                    "instructions": "Schedule hands-on working session. Focus on their specific pain points. Leave them with clear next steps they can execute immediately."
                },
                {
                    "name": "Executive Business Review (if needed)",
                    "step_type": "meeting",
                    "days_from_start": 10,
                    "due_days": 3,
                    "description": "For high-value accounts, involve executive sponsors on both sides",
                    "instructions": "Only for strategic accounts or if recovery isn't progressing. Bring your CS Director or VP. Focus on partnership value and mutual investment."
                },
                {
                    "name": "Day 14 Recovery Assessment",
                    "step_type": "review",
                    "days_from_start": 14,
                    "due_days": 1,
                    "description": "Final assessment: Is customer stabilized? Health score improving? Engagement restored?",
                    "instructions": "Review all metrics. If recovery successful, transition to monitoring. If not, escalate for retention offer consideration or accept loss.",
                    "required_outcomes": ["recovery_assessed", "next_steps_determined", "health_score_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 3: STRATEGIC RENEWAL PROGRAM (90-Day)
        # ============================================================
        {
            "name": "Strategic Renewal Program",
            "description": "90-day renewal excellence program. Begins 90 days before contract end. Combines value realization, executive alignment, and expansion opportunity identification. 2025 best practice: Start renewal conversations from Day 1 of the relationship.",
            "category": "renewal",
            "trigger_type": "days_to_renewal",
            "trigger_days_to_renewal": 90,
            "priority": "high",
            "target_completion_days": 90,
            "estimated_hours": 10.0,
            "success_criteria": {"renewal_closed": True, "expansion_identified": True, "multi_year_consideration": True},
            "steps": [
                {
                    "name": "Renewal Readiness Assessment",
                    "step_type": "review",
                    "days_from_start": 0,
                    "due_days": 3,
                    "description": "Internal assessment of renewal likelihood, expansion potential, and risk factors",
                    "instructions": "Score 1-5 on: Health Score Trend, Goal Achievement, Usage/Adoption, Relationship Strength, Support Experience, NPS, Champion Stability, Competitive Threat. Total 32+ = High confidence, 24-31 = Attention needed, <24 = At risk."
                },
                {
                    "name": "Value Delivered Documentation",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 7,
                    "description": "Compile comprehensive value delivered summary with ROI metrics",
                    "instructions": "Document: Original goals vs achievement, quantified ROI, usage highlights, key wins with metrics, cost savings, efficiency gains. Prepare visual one-pager."
                },
                {
                    "name": "Expansion Opportunity Analysis",
                    "step_type": "internal_task",
                    "days_from_start": 7,
                    "due_days": 5,
                    "description": "Identify all expansion opportunities: additional services, more tanks, new locations, premium features",
                    "instructions": "Review usage patterns for capacity signals. Check for new department interest. Identify feature requests matching premium tier. Calculate potential expansion value."
                },
                {
                    "name": "Value Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 15,
                    "due_days": 5,
                    "description": "Present value delivered summary to customer. Confirm ROI and gather feedback.",
                    "meeting_agenda_template": "1. Relationship Check-in (5 min)\n2. Value Delivered Review (15 min)\n3. Goals Achievement Discussion (10 min)\n4. Future Goals & Needs (10 min)\n5. Next Steps (5 min)",
                    "talk_track": "Over the past year, here's the value we've delivered together... [ROI data]. Looking ahead, what are your goals for the next 12 months?"
                },
                {
                    "name": "Stakeholder Mapping & Multi-threading",
                    "step_type": "internal_task",
                    "days_from_start": 20,
                    "due_days": 5,
                    "description": "Identify all stakeholders involved in renewal decision. Ensure relationships at multiple levels.",
                    "instructions": "Map: Decision maker, Budget holder, Champion, Users, Detractors. Ensure you have relationships at 3+ levels. Schedule touchpoints with any gaps."
                },
                {
                    "name": "Executive Sponsor Touch-base",
                    "step_type": "call",
                    "days_from_start": 30,
                    "due_days": 5,
                    "description": "Connect with executive sponsor to ensure strategic alignment and surface any concerns",
                    "talk_track": "As we approach renewal, I wanted to check in at the strategic level. How does our partnership fit into your priorities for the coming year? Any concerns I should be aware of?"
                },
                {
                    "name": "Renewal Proposal Preparation",
                    "step_type": "documentation",
                    "days_from_start": 40,
                    "due_days": 5,
                    "description": "Prepare renewal proposal with options: same terms, multi-year, expansion",
                    "instructions": "Create 3 options: 1) Same terms renewal, 2) Multi-year with discount, 3) Expansion bundle. Include value summary, pricing, and ROI projections for each."
                },
                {
                    "name": "Renewal Discussion Meeting",
                    "step_type": "meeting",
                    "days_from_start": 50,
                    "due_days": 5,
                    "description": "Present renewal proposal, discuss options, handle objections",
                    "meeting_agenda_template": "1. Value Summary Recap (5 min)\n2. Future Vision Alignment (10 min)\n3. Renewal Options Presentation (15 min)\n4. Q&A and Objection Handling (15 min)\n5. Next Steps & Timeline (5 min)",
                    "talk_track": "Based on your goals and the value we've delivered, here are three options for moving forward..."
                },
                {
                    "name": "Negotiation & Objection Handling",
                    "step_type": "call",
                    "days_from_start": 60,
                    "due_days": 10,
                    "description": "Handle any negotiations, objections, or procurement requirements",
                    "instructions": "Common objections: Price too high (cite ROI), Need to evaluate options (offer comparison support), Not using enough (offer adoption sprint), Leadership approval needed (offer exec alignment call)."
                },
                {
                    "name": "Contract Finalization",
                    "step_type": "documentation",
                    "days_from_start": 75,
                    "due_days": 10,
                    "description": "Finalize contract, process signature, update billing",
                    "instructions": "Coordinate with legal/procurement. Ensure clean handoff to billing. Update CRM with new contract details."
                },
                {
                    "name": "Renewal Celebration & Next Year Kickoff",
                    "step_type": "email",
                    "days_from_start": 85,
                    "due_days": 5,
                    "description": "Thank you communication and kickoff of new contract term success plan",
                    "email_subject": "Thank You for Your Continued Partnership - Year 2 Success Plan",
                    "email_body_template": "Thank you for renewing! Here's what to expect in Year 2, including new features, your dedicated support resources, and our first check-in date...",
                    "required_outcomes": ["renewal_closed", "success_plan_created", "health_score_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 4: EXPANSION & UPSELL ACCELERATION
        # ============================================================
        {
            "name": "Expansion Opportunity Accelerator",
            "description": "Structured program for identified expansion opportunities. Combines value-based selling, multi-stakeholder engagement, and ROI documentation. Best practice: Only pursue when health score > 70 and initial goals achieved.",
            "category": "expansion",
            "trigger_type": "manual",
            "priority": "high",
            "target_completion_days": 45,
            "estimated_hours": 8.0,
            "success_criteria": {"opportunity_qualified": True, "proposal_presented": True, "decision_made": True},
            "steps": [
                {
                    "name": "Expansion Readiness Check",
                    "step_type": "review",
                    "days_from_start": 0,
                    "due_days": 2,
                    "description": "Verify customer is ready for expansion: Health score > 70, goals achieved, relationship strong",
                    "instructions": "Check: Health score (must be >70), Goal achievement (>80%), Champion relationship (strong), No open escalations. If any fail, pause playbook and address first."
                },
                {
                    "name": "Opportunity Qualification (BANT)",
                    "step_type": "internal_task",
                    "days_from_start": 2,
                    "due_days": 2,
                    "description": "Qualify the opportunity: Budget, Authority, Need, Timeline",
                    "instructions": "Document: Do they have budget? Who approves? What problem does expansion solve? When do they need it? Score opportunity 1-4 on each dimension."
                },
                {
                    "name": "Value-Based Discovery Call",
                    "step_type": "call",
                    "days_from_start": 5,
                    "due_days": 3,
                    "description": "Deep discovery on expanded needs, pain points, and business impact",
                    "talk_track": "You've been so successful with [current use]. Tell me about [expanded need]. What would it mean for your business if you could [desired outcome]? What's the cost of not solving this?",
                    "instructions": "Focus 80% on their needs, 20% on solution. Quantify the pain. Get them to articulate the value."
                },
                {
                    "name": "Internal Deal Review",
                    "step_type": "internal_task",
                    "days_from_start": 10,
                    "due_days": 2,
                    "description": "Review opportunity with sales/account team. Align on approach and pricing.",
                    "instructions": "Present: Customer situation, expansion opportunity, qualification score, proposed solution, pricing recommendation, timeline. Get alignment on deal strategy."
                },
                {
                    "name": "ROI Business Case Development",
                    "step_type": "documentation",
                    "days_from_start": 12,
                    "due_days": 5,
                    "description": "Build compelling ROI business case with customer-specific data",
                    "instructions": "Calculate: Investment amount, Expected benefits (quantified), ROI %, Payback period. Use customer's own data where possible. Include case studies from similar customers."
                },
                {
                    "name": "Champion Alignment",
                    "step_type": "call",
                    "days_from_start": 18,
                    "due_days": 3,
                    "description": "Preview proposal with champion. Get feedback and buy-in before formal presentation.",
                    "talk_track": "Before I present to the broader team, I wanted to get your input on our proposal. Does this address your needs? What concerns might others have?",
                    "instructions": "Champions can preview objections and help you tailor the presentation. Their buy-in is critical."
                },
                {
                    "name": "Expansion Proposal Presentation",
                    "step_type": "meeting",
                    "days_from_start": 25,
                    "due_days": 5,
                    "description": "Formal presentation of expansion proposal to decision makers",
                    "meeting_agenda_template": "1. Current Success Recap (5 min)\n2. Expanded Needs Discussion (10 min)\n3. Solution Recommendation (15 min)\n4. ROI & Business Case (10 min)\n5. Investment & Timeline (5 min)\n6. Q&A (10 min)",
                    "instructions": "Bring your champion as internal advocate. Focus on business outcomes, not features."
                },
                {
                    "name": "Objection Handling & Negotiation",
                    "step_type": "call",
                    "days_from_start": 32,
                    "due_days": 5,
                    "description": "Address any objections, negotiate terms if needed",
                    "instructions": "Common objections: Budget timing (offer quarterly payment), Need more proof (provide reference calls), Scope concerns (offer pilot). Never discount without getting something in return."
                },
                {
                    "name": "Close or Decision Meeting",
                    "step_type": "meeting",
                    "days_from_start": 40,
                    "due_days": 5,
                    "description": "Final meeting to close deal or get clear decision/timeline",
                    "talk_track": "We've addressed your questions and refined the proposal. Are you ready to move forward? If not now, what needs to happen to get to yes?",
                    "required_outcomes": ["deal_closed", "deal_deferred_with_timeline", "deal_lost_documented"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 5: EXECUTIVE BUSINESS REVIEW (EBR/QBR)
        # ============================================================
        {
            "name": "Executive Business Review",
            "description": "Quarterly strategic review program for key accounts. Combines value storytelling, roadmap alignment, and executive engagement. 2025 best practice: Focus 70% on customer's future, 30% on past performance.",
            "category": "qbr",
            "trigger_type": "scheduled",
            "priority": "medium",
            "target_completion_days": 21,
            "estimated_hours": 6.0,
            "success_criteria": {"meeting_held": True, "action_items_assigned": True, "next_ebr_scheduled": True},
            "steps": [
                {
                    "name": "EBR Data Gathering",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 3,
                    "description": "Collect all data needed for EBR: usage, health, support, ROI metrics",
                    "instructions": "Gather: Health score trend, usage metrics (30/60/90 day), support ticket summary, NPS/CSAT, ROI calculations, product usage by feature, goal achievement status."
                },
                {
                    "name": "Stakeholder Outreach & Scheduling",
                    "step_type": "email",
                    "days_from_start": 3,
                    "due_days": 3,
                    "description": "Reach out to stakeholders to confirm attendees and schedule EBR",
                    "email_subject": "Quarterly Business Review - {quarter} {year}",
                    "email_body_template": "It's time for our quarterly strategic review. I'd like to schedule 60 minutes to review your progress, share insights, and align on priorities for next quarter.",
                    "instructions": "Target attendees: Executive sponsor, Day-to-day champion, Key users. From our side: CSM + Manager for strategic accounts."
                },
                {
                    "name": "EBR Presentation Development",
                    "step_type": "documentation",
                    "days_from_start": 7,
                    "due_days": 5,
                    "description": "Build compelling EBR presentation with value storytelling and strategic recommendations",
                    "instructions": "Structure: 1) Value Delivered (30%), 2) Their Future Goals & Industry Trends (40%), 3) Recommendations & Roadmap (20%), 4) Action Items (10%). Make it visual, not text-heavy."
                },
                {
                    "name": "Internal Dry Run",
                    "step_type": "internal_task",
                    "days_from_start": 10,
                    "due_days": 2,
                    "description": "Practice presentation with manager. Refine story and anticipate questions.",
                    "instructions": "Practice the full presentation. Get feedback on flow, story, and data accuracy. Prepare for likely questions and objections."
                },
                {
                    "name": "Pre-Read Distribution",
                    "step_type": "email",
                    "days_from_start": 12,
                    "due_days": 1,
                    "description": "Send agenda and key data points to attendees before meeting",
                    "instructions": "Send 2-3 days before. Include: Agenda, 3-5 key metrics, discussion topics. Helps attendees prepare and shows professionalism."
                },
                {
                    "name": "Executive Business Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 14,
                    "due_days": 3,
                    "description": "60-minute strategic review meeting with executive stakeholders",
                    "meeting_agenda_template": "1. Welcome & Agenda (5 min)\n2. Value Delivered Summary (10 min)\n3. Customer Perspective - Their View (15 min)\n4. Strategic Alignment & Industry Trends (15 min)\n5. Roadmap & Innovation Preview (10 min)\n6. Action Items & Next Steps (5 min)",
                    "talk_track": "Let me share what we've accomplished together, then I'd love to hear your perspective on what's working and where we can improve...",
                    "instructions": "Speak 40% of the time, listen 60%. Focus on their strategic priorities, not just your platform. Be a strategic advisor, not a vendor."
                },
                {
                    "name": "EBR Follow-up & Action Items",
                    "step_type": "email",
                    "days_from_start": 15,
                    "due_days": 2,
                    "description": "Send meeting summary with action items and owners within 24 hours",
                    "email_subject": "EBR Summary & Action Items - {company_name}",
                    "instructions": "Include: Key discussion points, agreed action items with owners and due dates, next EBR date, any documents referenced."
                },
                {
                    "name": "Action Item Tracking Setup",
                    "step_type": "internal_task",
                    "days_from_start": 17,
                    "due_days": 2,
                    "description": "Document action items in CRM and set follow-up reminders",
                    "instructions": "Create tasks for all action items. Set reminders for follow-up. Schedule next EBR (typically 90 days out).",
                    "required_outcomes": ["action_items_documented", "next_ebr_scheduled", "crm_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 6: ESCALATION RESPONSE & RECOVERY
        # ============================================================
        {
            "name": "Escalation Response & Recovery",
            "description": "Rapid response playbook for customer escalations. Triggered by escalation events. Focus on immediate response, root cause resolution, and relationship recovery. SLA: Critical = 1hr response, High = 4hr, Medium = 24hr.",
            "category": "escalation",
            "trigger_type": "event",
            "trigger_event": "escalation_created",
            "priority": "critical",
            "target_completion_days": 7,
            "estimated_hours": 6.0,
            "success_criteria": {"escalation_resolved": True, "customer_satisfied": True, "prevention_documented": True},
            "steps": [
                {
                    "name": "Immediate Acknowledgment",
                    "step_type": "email",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Acknowledge escalation within SLA (Critical: 1hr, High: 4hr, Medium: 24hr)",
                    "email_subject": "[PRIORITY] Acknowledgment - {issue_summary}",
                    "email_body_template": "I want to confirm we've received your escalation and are treating this as our top priority. Here's what we know so far and what we're doing about it...",
                    "instructions": "Respond within SLA. Acknowledge the issue. Don't make excuses. Provide timeline for next update. Give direct contact info."
                },
                {
                    "name": "Severity Assessment & Triage",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Assess severity, identify affected scope, determine required resources",
                    "instructions": "Classify: P1 (Business stopped), P2 (Major impact), P3 (Moderate impact), P4 (Minor). Identify affected users/revenue. Determine cross-functional resources needed."
                },
                {
                    "name": "Internal Escalation & Resource Mobilization",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Escalate internally per severity. Mobilize required teams.",
                    "instructions": "P1: Immediate CS Director + Engineering Lead notification. P2: CS Manager within 4 hours. P3/P4: Standard process. Create war room for P1/P2."
                },
                {
                    "name": "Root Cause Investigation",
                    "step_type": "internal_task",
                    "days_from_start": 1,
                    "due_days": 2,
                    "description": "Deep investigation to identify root cause. Don't just fix symptoms.",
                    "instructions": "Apply 5 Whys methodology. Document investigation findings. Identify temporary workaround if full fix will take time. Coordinate with relevant teams."
                },
                {
                    "name": "Customer Update Call",
                    "step_type": "call",
                    "days_from_start": 1,
                    "due_days": 1,
                    "description": "Proactive call to customer with status update, even if not fully resolved",
                    "talk_track": "I wanted to update you directly on our progress. Here's what we've found, what we're doing, and when you can expect resolution...",
                    "instructions": "Call even if you don't have good news. Silence is worse than bad news. Customers appreciate transparency and proactive communication."
                },
                {
                    "name": "Resolution Implementation",
                    "step_type": "internal_task",
                    "days_from_start": 2,
                    "due_days": 3,
                    "description": "Implement fix and verify resolution. Test thoroughly before confirming.",
                    "instructions": "Implement fix. Test in staging if possible. Verify with customer that issue is resolved. Don't mark resolved until customer confirms."
                },
                {
                    "name": "Resolution Confirmation",
                    "step_type": "email",
                    "days_from_start": 5,
                    "due_days": 1,
                    "description": "Formal resolution communication with root cause and prevention measures",
                    "email_subject": "[RESOLVED] {issue_summary}",
                    "email_body_template": "I'm pleased to confirm that the issue has been resolved. Root cause: [explanation]. Resolution: [what was done]. Prevention: [what we've done to prevent recurrence].",
                    "instructions": "Be transparent about what happened. Don't hide or minimize. Explain prevention measures. Thank them for patience."
                },
                {
                    "name": "Post-Incident Review",
                    "step_type": "internal_task",
                    "days_from_start": 6,
                    "due_days": 2,
                    "description": "Internal post-mortem: What went well, what could improve, action items",
                    "instructions": "Document: Timeline, root cause, impact, what went well, what could improve, action items with owners. Share learnings with broader team."
                },
                {
                    "name": "Customer Relationship Recovery",
                    "step_type": "call",
                    "days_from_start": 7,
                    "due_days": 1,
                    "description": "Follow-up call to ensure satisfaction and repair relationship",
                    "talk_track": "Now that we've resolved the issue, I wanted to check in on how you're feeling about our partnership. What could we have done better? Is there anything else you need from us?",
                    "instructions": "For major incidents, consider: Executive apology call, service credits, additional support. Focus on rebuilding trust.",
                    "required_outcomes": ["customer_satisfied", "prevention_documented", "relationship_recovered"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 7: CHAMPION CHANGE MANAGEMENT
        # ============================================================
        {
            "name": "Champion Change Management",
            "description": "Playbook for managing transitions when your customer champion leaves or changes roles. Critical risk event - relationships with departing champions are a leading indicator of churn.",
            "category": "champion_change",
            "trigger_type": "event",
            "trigger_event": "champion_change_detected",
            "priority": "high",
            "target_completion_days": 30,
            "estimated_hours": 5.0,
            "success_criteria": {"new_champion_identified": True, "relationship_transferred": True, "account_stable": True},
            "steps": [
                {
                    "name": "Situation Assessment",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Assess the situation: Is champion leaving company, changing roles, or being replaced?",
                    "instructions": "Determine: Departure type (leaving company, promotion, lateral move). Identify interim contacts. Assess risk to account. Check health of relationships with other stakeholders."
                },
                {
                    "name": "Departing Champion Conversation",
                    "step_type": "call",
                    "days_from_start": 1,
                    "due_days": 2,
                    "description": "Call with departing champion to understand situation and get warm introductions",
                    "talk_track": "I heard about your transition - congratulations! Before you go, could you help me connect with your successor? Also, would you mind being a reference for us at your new company?",
                    "instructions": "Get: Successor name and intro, remaining influence period, reference for new company, feedback on our partnership."
                },
                {
                    "name": "New Champion Introduction",
                    "step_type": "meeting",
                    "days_from_start": 5,
                    "due_days": 5,
                    "description": "Initial meeting with new champion to establish relationship",
                    "meeting_agenda_template": "1. Introductions & Background (10 min)\n2. Current Partnership Overview (10 min)\n3. Their Priorities & Goals (15 min)\n4. How We Can Help (10 min)\n5. Support & Next Steps (5 min)",
                    "talk_track": "I'm excited to work with you. Let me share where we are and the value we've delivered, then I'd love to understand your priorities and how I can support your success."
                },
                {
                    "name": "Stakeholder Map Update",
                    "step_type": "internal_task",
                    "days_from_start": 7,
                    "due_days": 3,
                    "description": "Update stakeholder map, identify gaps, plan multi-threading strategy",
                    "instructions": "Update CRM with new contacts. Identify other relationships to strengthen. Plan outreach to ensure multiple relationships across the organization."
                },
                {
                    "name": "Value Reinforcement Session",
                    "step_type": "meeting",
                    "days_from_start": 14,
                    "due_days": 5,
                    "description": "Present value summary to new champion - re-sell the partnership",
                    "instructions": "New champions may not know the history. Present: Original goals, value delivered, ROI, roadmap. Make them a believer. This is essentially a mini-renewal."
                },
                {
                    "name": "Training & Enablement Offer",
                    "step_type": "email",
                    "days_from_start": 18,
                    "due_days": 3,
                    "description": "Offer new champion training and direct support to accelerate their success",
                    "email_body_template": "As you get up to speed, I wanted to offer a personalized training session on the platform. I can also share our champion toolkit with best practices from top-performing customers."
                },
                {
                    "name": "30-Day Stability Check",
                    "step_type": "call",
                    "days_from_start": 28,
                    "due_days": 3,
                    "description": "Check-in call to ensure smooth transition and address any concerns",
                    "talk_track": "It's been a month since your transition. How are you feeling about the platform? Any questions or concerns I can address? What would make our partnership even more successful?",
                    "required_outcomes": ["new_champion_enabled", "relationship_stable", "health_score_maintained"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 8: IMPLEMENTATION & GO-LIVE SUPPORT
        # ============================================================
        {
            "name": "Implementation Success Program",
            "description": "Technical implementation support playbook for complex deployments. Ensures successful go-live with minimal disruption. Best practice: Implementation is the foundation of all future success.",
            "category": "implementation",
            "trigger_type": "manual",
            "priority": "high",
            "target_completion_days": 45,
            "estimated_hours": 15.0,
            "success_criteria": {"go_live_successful": True, "data_migrated": True, "users_trained": True},
            "steps": [
                {
                    "name": "Implementation Kickoff",
                    "step_type": "meeting",
                    "days_from_start": 0,
                    "due_days": 3,
                    "description": "Technical kickoff meeting with all implementation stakeholders",
                    "meeting_agenda_template": "1. Team Introductions (10 min)\n2. Technical Requirements Review (15 min)\n3. Data Migration Scope (15 min)\n4. Integration Requirements (10 min)\n5. Timeline & Milestones (10 min)\n6. Risk Assessment (10 min)",
                    "instructions": "Bring technical lead. Ensure customer IT team is present. Document all requirements and dependencies."
                },
                {
                    "name": "Technical Requirements Documentation",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 5,
                    "description": "Document all technical requirements, integrations, and configuration needs",
                    "instructions": "Create comprehensive tech spec: System integrations, data fields, workflows, user roles, security requirements, compliance needs."
                },
                {
                    "name": "Data Migration Planning",
                    "step_type": "internal_task",
                    "days_from_start": 7,
                    "due_days": 5,
                    "description": "Plan data migration: mapping, cleansing, validation, and rollback procedures",
                    "instructions": "Create migration plan: Source systems, field mapping, data cleansing rules, validation criteria, rollback procedure, timeline."
                },
                {
                    "name": "Environment Configuration",
                    "step_type": "internal_task",
                    "days_from_start": 12,
                    "due_days": 7,
                    "description": "Configure customer environment per requirements",
                    "instructions": "Complete all configurations. Document all settings. Create admin guide. Test all functionality before handing off."
                },
                {
                    "name": "Integration Development & Testing",
                    "step_type": "internal_task",
                    "days_from_start": 14,
                    "due_days": 10,
                    "description": "Build and test all required integrations",
                    "instructions": "Build integrations per spec. Unit test each. Integration test full workflow. Document APIs and troubleshooting."
                },
                {
                    "name": "Data Migration Execution",
                    "step_type": "internal_task",
                    "days_from_start": 25,
                    "due_days": 5,
                    "description": "Execute data migration and validate results",
                    "instructions": "Run migration. Validate record counts. Spot check data quality. Get customer sign-off on migrated data."
                },
                {
                    "name": "User Acceptance Testing (UAT)",
                    "step_type": "meeting",
                    "days_from_start": 30,
                    "due_days": 5,
                    "description": "Customer UAT session to validate all functionality",
                    "instructions": "Provide test scripts. Support customer through testing. Document issues. Fix blockers before go-live. Get UAT sign-off."
                },
                {
                    "name": "Go-Live Preparation",
                    "step_type": "internal_task",
                    "days_from_start": 35,
                    "due_days": 3,
                    "description": "Final preparation for go-live: checklist, communication plan, support readiness",
                    "instructions": "Complete go-live checklist. Prepare communication to users. Brief support team. Confirm rollback plan. Get final go-live approval."
                },
                {
                    "name": "Go-Live Support",
                    "step_type": "meeting",
                    "days_from_start": 38,
                    "due_days": 3,
                    "description": "Hands-on support during go-live window",
                    "instructions": "Be available during go-live. Monitor for issues. Respond immediately to problems. Daily check-ins with customer during first week."
                },
                {
                    "name": "Post Go-Live Review",
                    "step_type": "meeting",
                    "days_from_start": 45,
                    "due_days": 3,
                    "description": "Formal implementation closure and handoff to ongoing success",
                    "meeting_agenda_template": "1. Go-Live Success Review (10 min)\n2. Remaining Items & Timeline (10 min)\n3. Training Completion Status (5 min)\n4. Transition to Ongoing Support (10 min)\n5. Implementation Feedback (5 min)",
                    "required_outcomes": ["implementation_complete", "customer_satisfied", "handoff_to_cs"]
                }
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
