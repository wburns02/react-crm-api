"""
Seed journey steps for existing journeys.
Run this script after connecting to the database.

Usage:
  python scripts/seed_journey_steps.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.customer_success import Journey, JourneyStep
from app.core.config import settings


# Journey step templates
ONBOARDING_STEPS = [
    {"name": "Welcome Email", "description": "Send personalized welcome email with next steps", "step_type": "email", "step_order": 1, "action_config": {"template": "welcome", "subject": "Welcome to Mac-Septic!"}},
    {"name": "Wait 24 Hours", "description": "Allow customer time to explore", "step_type": "wait", "step_order": 2, "wait_duration_hours": 24},
    {"name": "Account Setup Reminder", "description": "Remind customer to complete profile", "step_type": "email", "step_order": 3, "action_config": {"template": "setup_reminder"}},
    {"name": "CSM Introduction Call", "description": "Schedule introductory call with assigned CSM", "step_type": "task", "step_order": 4, "action_config": {"task_type": "call", "assignee_role": "csm"}},
    {"name": "Check Profile Complete", "description": "Verify customer has completed their profile", "step_type": "condition", "step_order": 5, "condition_rules": {"field": "profile_complete", "operator": "eq", "value": True}},
    {"name": "Schedule First Service", "description": "Help customer schedule their first service", "step_type": "task", "step_order": 6, "action_config": {"task_type": "meeting", "title": "Schedule First Service"}},
    {"name": "Wait for Service", "description": "Wait for first service to be completed", "step_type": "wait", "step_order": 7, "wait_duration_hours": 168},
    {"name": "Post-Service Follow-up", "description": "Send satisfaction survey after first service", "step_type": "email", "step_order": 8, "action_config": {"template": "post_service_survey"}},
    {"name": "NPS Survey", "description": "Request Net Promoter Score feedback", "step_type": "email", "step_order": 9, "action_config": {"template": "nps_survey"}},
    {"name": "Graduation Check", "description": "Verify customer is fully onboarded", "step_type": "health_check", "step_order": 10, "action_config": {"min_health_score": 70}},
]

RISK_MITIGATION_STEPS = [
    {"name": "Risk Alert", "description": "Notify CSM of at-risk customer", "step_type": "notification", "step_order": 1, "action_config": {"channel": "slack", "priority": "high"}},
    {"name": "Health Score Review", "description": "Analyze health score components", "step_type": "health_check", "step_order": 2, "action_config": {"review_type": "detailed"}},
    {"name": "Immediate Outreach", "description": "CSM calls customer within 24 hours", "step_type": "task", "step_order": 3, "action_config": {"task_type": "call", "priority": "critical", "due_hours": 24}},
    {"name": "Concern Documentation", "description": "Document customer concerns and issues", "step_type": "task", "step_order": 4, "action_config": {"task_type": "documentation"}},
    {"name": "Recovery Plan Creation", "description": "Create action plan to address issues", "step_type": "task", "step_order": 5, "action_config": {"task_type": "internal", "title": "Create Recovery Plan"}},
    {"name": "Executive Escalation Check", "description": "Determine if executive involvement needed", "step_type": "condition", "step_order": 6, "condition_rules": {"field": "health_score", "operator": "lt", "value": 30}},
    {"name": "Recovery Actions", "description": "Execute recovery plan actions", "step_type": "task", "step_order": 7, "action_config": {"task_type": "follow_up"}},
    {"name": "Wait 7 Days", "description": "Allow time for recovery actions to take effect", "step_type": "wait", "step_order": 8, "wait_duration_hours": 168},
    {"name": "Progress Check-in", "description": "Follow up call to assess progress", "step_type": "task", "step_order": 9, "action_config": {"task_type": "call", "title": "Recovery Progress Check"}},
    {"name": "Health Re-evaluation", "description": "Re-calculate health score after intervention", "step_type": "health_check", "step_order": 10, "action_config": {"target_score": 60}},
]

ADVOCACY_STEPS = [
    {"name": "Promoter Identification", "description": "Confirm customer is a promoter (NPS 9-10)", "step_type": "condition", "step_order": 1, "condition_rules": {"field": "nps_score", "operator": "gte", "value": 9}},
    {"name": "Thank You Email", "description": "Send personalized thank you for high NPS", "step_type": "email", "step_order": 2, "action_config": {"template": "promoter_thanks"}},
    {"name": "Case Study Invitation", "description": "Invite customer to participate in case study", "step_type": "email", "step_order": 3, "action_config": {"template": "case_study_invite"}},
    {"name": "Wait for Response", "description": "Allow time to consider case study", "step_type": "wait", "step_order": 4, "wait_duration_hours": 72},
    {"name": "Referral Program Introduction", "description": "Introduce referral rewards program", "step_type": "email", "step_order": 5, "action_config": {"template": "referral_program"}},
    {"name": "Review Request", "description": "Request online review", "step_type": "email", "step_order": 6, "action_config": {"template": "review_request"}},
    {"name": "Social Media Engagement", "description": "Invite to follow and engage on social", "step_type": "in_app_message", "step_order": 7, "action_config": {"message_type": "banner"}},
    {"name": "Advocacy Program Enrollment", "description": "Enroll in formal advocacy program", "step_type": "update_field", "step_order": 8, "action_config": {"field": "is_advocate", "value": True}},
]

DEFAULT_STEPS = [
    {"name": "Journey Start", "description": "Initial entry point for the journey", "step_type": "notification", "step_order": 1, "action_config": {"type": "internal"}},
    {"name": "Initial Outreach", "description": "First touchpoint with customer", "step_type": "email", "step_order": 2, "action_config": {"template": "generic_outreach"}},
    {"name": "Wait Period", "description": "Allow time for customer response", "step_type": "wait", "step_order": 3, "wait_duration_hours": 48},
    {"name": "Follow-up Task", "description": "CSM follow-up action", "step_type": "task", "step_order": 4, "action_config": {"task_type": "follow_up"}},
    {"name": "Status Check", "description": "Evaluate journey progress", "step_type": "condition", "step_order": 5, "condition_rules": {"field": "engaged", "operator": "eq", "value": True}},
    {"name": "Journey Complete", "description": "Mark journey as successfully completed", "step_type": "update_field", "step_order": 6, "action_config": {"field": "journey_status", "value": "completed"}},
]


def get_steps_for_journey(journey_name: str) -> list:
    """Determine which steps template to use based on journey name."""
    name_lower = journey_name.lower()

    if 'onboarding' in name_lower:
        return ONBOARDING_STEPS
    elif 'risk' in name_lower or 'mitigation' in name_lower:
        return RISK_MITIGATION_STEPS
    elif 'advocacy' in name_lower:
        return ADVOCACY_STEPS
    else:
        return DEFAULT_STEPS


async def seed_journey_steps():
    """Main function to seed journey steps."""
    # Create async engine
    database_url = settings.DATABASE_URL
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)

    engine = create_async_engine(database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get all journeys
        result = await session.execute(select(Journey))
        journeys = result.scalars().all()

        print(f"Found {len(journeys)} journeys")

        seeded_count = 0

        for journey in journeys:
            # Check if journey already has steps
            steps_result = await session.execute(
                select(func.count()).where(JourneyStep.journey_id == journey.id)
            )
            existing_steps = steps_result.scalar() or 0

            if existing_steps > 0:
                print(f"Journey '{journey.name}' already has {existing_steps} steps, skipping")
                continue

            # Get appropriate steps
            steps_to_add = get_steps_for_journey(journey.name)

            # Add steps
            for step_data in steps_to_add:
                step = JourneyStep(
                    journey_id=journey.id,
                    name=step_data["name"],
                    description=step_data.get("description"),
                    step_type=step_data["step_type"],
                    step_order=step_data["step_order"],
                    wait_duration_hours=step_data.get("wait_duration_hours"),
                    condition_rules=step_data.get("condition_rules"),
                    action_config=step_data.get("action_config"),
                    is_required=True,
                    is_active=True,
                )
                session.add(step)
                seeded_count += 1

            print(f"Added {len(steps_to_add)} steps to journey: {journey.name}")

        await session.commit()
        print(f"\nTotal: Seeded {seeded_count} steps across {len(journeys)} journeys")


if __name__ == "__main__":
    asyncio.run(seed_journey_steps())
