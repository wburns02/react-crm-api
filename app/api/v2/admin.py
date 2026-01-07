"""
Admin Settings API - System configuration endpoints.

Provides settings management for system, notifications, integrations, and security.
Also provides user management endpoints.
"""
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from sqlalchemy import select, delete, func
from datetime import datetime, timedelta, date
from decimal import Decimal
import random
import logging

from app.api.deps import CurrentUser, DbSession, get_password_hash
from app.models.user import User
from app.models.customer import Customer

# Customer Success imports
from app.models.customer_success.health_score import HealthScore, HealthScoreEvent
from app.models.customer_success.segment import Segment, CustomerSegment
from app.models.customer_success.playbook import Playbook, PlaybookStep, PlaybookExecution
from app.models.customer_success.journey import Journey, JourneyStep, JourneyEnrollment, JourneyStepExecution
from app.models.customer_success.task import CSTask
from app.models.customer_success.touchpoint import Touchpoint
from app.data.playbooks_data import get_world_class_playbooks
from app.data.journeys_data import get_world_class_journeys

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ User Management ============

class UserResponse(BaseModel):
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "user"
    is_active: bool = True
    last_login: Optional[str] = None
    created_at: str


class CreateUserRequest(BaseModel):
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str = "user"
    password: str


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


def user_to_response(user: User) -> dict:
    """Convert User model to response dict."""
    role = "admin" if user.is_superuser else "user"
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "role": role,
        "is_active": user.is_active,
        "last_login": None,  # Not tracked yet
        "created_at": user.created_at.isoformat() if user.created_at else datetime.utcnow().isoformat(),
    }


@router.get("/users")
async def list_users(
    db: DbSession,
    current_user: CurrentUser,
):
    """List all users."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return {"users": [user_to_response(u) for u in users]}


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new user."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=request.email,
        hashed_password=get_password_hash(request.password),
        first_name=request.first_name,
        last_name=request.last_name,
        is_active=True,
        is_superuser=(request.role == "admin"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"user": user_to_response(user)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a user."""
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields
    if request.email is not None:
        user.email = request.email
    if request.first_name is not None:
        user.first_name = request.first_name
    if request.last_name is not None:
        user.last_name = request.last_name
    if request.role is not None:
        user.is_superuser = (request.role == "admin")
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password is not None:
        user.hashed_password = get_password_hash(request.password)

    await db.commit()
    await db.refresh(user)

    return {"user": user_to_response(user)}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Deactivate a user (soft delete)."""
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_active = False
    await db.commit()

    return {"message": "User deactivated"}


class SystemSettings(BaseModel):
    company_name: str = "MAC Septic CRM"
    timezone: str = "America/Chicago"
    date_format: str = "MM/DD/YYYY"
    currency: str = "USD"
    language: str = "en"


class NotificationSettings(BaseModel):
    email_notifications: bool = True
    sms_notifications: bool = False
    push_notifications: bool = False
    daily_digest: bool = True
    work_order_alerts: bool = True
    payment_alerts: bool = True


class IntegrationSettings(BaseModel):
    samsara_enabled: bool = False
    ringcentral_enabled: bool = False
    quickbooks_enabled: bool = False
    stripe_enabled: bool = False


class SecuritySettings(BaseModel):
    two_factor_required: bool = False
    session_timeout_minutes: int = 30
    password_expiry_days: int = 90
    ip_whitelist_enabled: bool = False
    ip_whitelist: list[str] = []


@router.get("/settings/system")
async def get_system_settings(current_user: CurrentUser) -> SystemSettings:
    """Get system settings."""
    return SystemSettings()


@router.patch("/settings/system")
async def update_system_settings(
    settings: SystemSettings,
    current_user: CurrentUser,
) -> SystemSettings:
    """Update system settings."""
    # TODO: Persist settings to database
    return settings


@router.get("/settings/notifications")
async def get_notification_settings(current_user: CurrentUser) -> NotificationSettings:
    """Get notification settings."""
    return NotificationSettings()


@router.patch("/settings/notifications")
async def update_notification_settings(
    settings: NotificationSettings,
    current_user: CurrentUser,
) -> NotificationSettings:
    """Update notification settings."""
    return settings


@router.get("/settings/integrations")
async def get_integration_settings(current_user: CurrentUser) -> IntegrationSettings:
    """Get integration settings."""
    return IntegrationSettings()


@router.patch("/settings/integrations")
async def update_integration_settings(
    settings: IntegrationSettings,
    current_user: CurrentUser,
) -> IntegrationSettings:
    """Update integration settings."""
    return settings


@router.get("/settings/security")
async def get_security_settings(current_user: CurrentUser) -> SecuritySettings:
    """Get security settings."""
    return SecuritySettings()


@router.patch("/settings/security")
async def update_security_settings(
    settings: SecuritySettings,
    current_user: CurrentUser,
) -> SecuritySettings:
    """Update security settings."""
    return settings


# ============ Customer Success Seed Data ============

# Fake data for generating customers
FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Charles", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

CITIES = [
    ("Houston", "TX", "77001"), ("Austin", "TX", "78701"), ("Dallas", "TX", "75201"),
    ("San Antonio", "TX", "78201"), ("Fort Worth", "TX", "76101"),
]

SUBDIVISIONS = ["Oak Meadows", "Riverside Estates", "Cedar Creek", "Pine Valley", "Willow Springs"]
SYSTEM_TYPES = ["Conventional", "Aerobic", "Mound", "Chamber", "Drip Distribution"]
TANK_SIZES = [500, 750, 1000, 1250, 1500, 2000]
LEAD_SOURCES = ["Google", "Referral", "Facebook", "Website", "Yelp"]
CUSTOMER_TYPES = ["Residential", "Commercial", "Multi-Family", "HOA"]


class SeedResponse(BaseModel):
    success: bool
    message: str
    stats: dict


@router.post("/seed/customer-success", response_model=SeedResponse)
async def seed_customer_success_data(
    db: DbSession,
    current_user: CurrentUser,
    target_customers: int = 100,
):
    """
    Seed Customer Success test data.

    - Limits customers to target_customers (default 100)
    - Removes any customer named "Stephanie Burns"
    - Creates health scores, segments, playbooks, journeys, tasks, touchpoints
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can seed data"
        )

    stats = {}

    try:
        # 1. Clear existing CS data
        logger.info("Clearing existing Customer Success data...")
        await db.execute(delete(JourneyStepExecution))
        await db.execute(delete(JourneyEnrollment))
        await db.execute(delete(JourneyStep))
        await db.execute(delete(Journey))
        await db.execute(delete(CSTask))
        await db.execute(delete(PlaybookExecution))
        await db.execute(delete(PlaybookStep))
        await db.execute(delete(Playbook))
        await db.execute(delete(Touchpoint))
        await db.execute(delete(HealthScoreEvent))
        await db.execute(delete(HealthScore))
        await db.execute(delete(CustomerSegment))
        await db.execute(delete(Segment))
        await db.commit()

        # 2. Remove Stephanie Burns (or rename if has FK constraints)
        result = await db.execute(
            select(Customer).where(
                func.lower(Customer.first_name) == 'stephanie',
                func.lower(Customer.last_name) == 'burns'
            )
        )
        for s in result.scalars().all():
            # Rename instead of delete to avoid FK constraint issues
            logger.info(f"Renaming Stephanie Burns (ID: {s.id}) to 'Removed Customer'")
            s.first_name = "Removed"
            s.last_name = "Customer"
            s.email = f"removed.customer.{s.id}@example.com"
        await db.commit()

        # 3. Manage customer count (don't delete - may have FK constraints)
        result = await db.execute(select(func.count(Customer.id)))
        current_count = result.scalar()

        if current_count > target_customers:
            # Don't delete customers - they may have work orders, attachments, etc.
            # Just use the first N customers
            logger.info(f"Have {current_count} customers, using first {target_customers}")

        if current_count < target_customers:
            needed = target_customers - current_count
            used_combos = set()
            result = await db.execute(select(Customer.first_name, Customer.last_name))
            for row in result.fetchall():
                used_combos.add((row[0], row[1]))

            new_customers = []
            attempts = 0
            while len(new_customers) < needed and attempts < 1000:
                attempts += 1
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
                if first.lower() == 'stephanie' and last.lower() == 'burns':
                    continue
                if (first, last) in used_combos:
                    continue
                used_combos.add((first, last))
                city, state, postal = random.choice(CITIES)

                customer = Customer(
                    first_name=first,
                    last_name=last,
                    email=f"{first.lower()}.{last.lower()}@example.com",
                    phone=f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
                    address_line1=f"{random.randint(100, 9999)} Oak St",
                    city=city,
                    state=state,
                    postal_code=postal,
                    is_active=random.random() > 0.1,
                    lead_source=random.choice(LEAD_SOURCES),
                    customer_type=random.choice(CUSTOMER_TYPES),
                    tank_size_gallons=random.choice(TANK_SIZES),
                    number_of_tanks=random.randint(1, 3),
                    system_type=random.choice(SYSTEM_TYPES),
                    subdivision=random.choice(SUBDIVISIONS),
                    created_at=datetime.now() - timedelta(days=random.randint(30, 730)),
                    updated_at=datetime.now() - timedelta(days=random.randint(0, 30)),
                )
                new_customers.append(customer)

            db.add_all(new_customers)
            await db.commit()

        # Get customer IDs (limit to target)
        result = await db.execute(
            select(Customer.id).order_by(Customer.id).limit(target_customers)
        )
        customer_ids = [row[0] for row in result.fetchall()]
        stats["customers"] = len(customer_ids)

        # 4. Create segments
        segments_data = [
            {"name": "High Value Accounts", "description": "High contract value customers", "color": "#10B981", "segment_type": "dynamic", "priority": 10},
            {"name": "At Risk - Low Engagement", "description": "Customers showing disengagement", "color": "#EF4444", "segment_type": "dynamic", "priority": 5},
            {"name": "Growth Candidates", "description": "Healthy accounts with expansion potential", "color": "#3B82F6", "segment_type": "dynamic", "priority": 15},
            {"name": "New Customers (< 90 days)", "description": "Recently onboarded customers", "color": "#8B5CF6", "segment_type": "dynamic", "priority": 20},
            {"name": "Champions", "description": "Highly engaged advocates", "color": "#F59E0B", "segment_type": "dynamic", "priority": 25},
            {"name": "Commercial Accounts", "description": "Business customers", "color": "#6366F1", "segment_type": "dynamic", "priority": 30},
        ]

        segment_ids = []
        for data in segments_data:
            segment = Segment(**data)
            db.add(segment)
            await db.flush()
            segment_ids.append(segment.id)
        await db.commit()
        stats["segments"] = len(segment_ids)

        # 5. Create health scores
        health_scores = []
        for cid in customer_ids:
            base_score = max(10, min(100, int(random.gauss(65, 20))))
            product_adoption = max(0, min(100, int(base_score + random.gauss(0, 15))))
            engagement = max(0, min(100, int(base_score + random.gauss(0, 15))))
            relationship = max(0, min(100, int(base_score + random.gauss(5, 10))))
            financial = max(0, min(100, int(base_score + random.gauss(0, 12))))
            support = max(0, min(100, int(base_score + random.gauss(-5, 18))))

            overall = int(product_adoption * 0.30 + engagement * 0.25 + relationship * 0.15 + financial * 0.20 + support * 0.10)
            status_val = 'healthy' if overall >= 70 else ('at_risk' if overall >= 40 else 'critical')
            trend_roll = random.random()
            trend = 'improving' if trend_roll < 0.3 else ('stable' if trend_roll < 0.6 else 'declining')

            hs = HealthScore(
                customer_id=cid,
                overall_score=overall,
                health_status=status_val,
                product_adoption_score=product_adoption,
                engagement_score=engagement,
                relationship_score=relationship,
                financial_score=financial,
                support_score=support,
                churn_probability=round(max(0, min(1, (100 - overall) / 100 * 0.8)), 3),
                expansion_probability=round(random.uniform(0, 0.5) if status_val == 'healthy' else random.uniform(0, 0.2), 3),
                days_since_last_login=random.randint(0, 90),
                days_to_renewal=random.randint(30, 365),
                score_trend=trend,
                score_change_7d=random.randint(-10, 10),
                score_change_30d=random.randint(-20, 20),
            )
            health_scores.append(hs)

        db.add_all(health_scores)
        await db.commit()
        stats["health_scores"] = len(health_scores)

        # 6. Assign customers to segments
        result = await db.execute(select(HealthScore.customer_id, HealthScore.overall_score))
        health_data = {row[0]: row[1] for row in result.fetchall()}

        memberships = []
        segment_counts = {sid: 0 for sid in segment_ids}

        for cid in customer_ids:
            score = health_data.get(cid, 50)
            assigned = []

            if score >= 75:
                assigned.append(segment_ids[0])  # High Value
            if score < 50:
                assigned.append(segment_ids[1])  # At Risk
            if 60 <= score <= 85 and random.random() < 0.4:
                assigned.append(segment_ids[2])  # Growth
            if random.random() < 0.15:
                assigned.append(segment_ids[3])  # New
            if score >= 85:
                assigned.append(segment_ids[4])  # Champions
            if random.random() < 0.25:
                assigned.append(segment_ids[5])  # Commercial

            for sid in assigned:
                memberships.append(CustomerSegment(
                    customer_id=cid,
                    segment_id=sid,
                    is_active=True,
                    entry_reason="Initial segmentation",
                    added_by="system:seed"
                ))
                segment_counts[sid] += 1

        db.add_all(memberships)

        for sid, count in segment_counts.items():
            result = await db.execute(select(Segment).where(Segment.id == sid))
            segment = result.scalar_one()
            segment.customer_count = count

        await db.commit()
        stats["segment_memberships"] = len(memberships)

        # 7. Create world-class playbooks (2025-2026 Best Practices)
        playbooks_data = get_world_class_playbooks(segment_ids)

        playbook_ids = []
        for pb_data in playbooks_data:
            # Extract steps before creating playbook
            steps_data = pb_data.pop("steps", [])

            # Handle success_criteria - convert to JSON-compatible
            if "success_criteria" in pb_data and pb_data["success_criteria"]:
                pb_data["success_criteria"] = pb_data["success_criteria"]

            playbook = Playbook(**pb_data)
            db.add(playbook)
            await db.flush()
            playbook_ids.append(playbook.id)

            # Add steps with detailed content
            for i, step_data in enumerate(steps_data, 1):
                step_data["step_order"] = i
                step_data["playbook_id"] = playbook.id
                step = PlaybookStep(**step_data)
                db.add(step)

        await db.commit()
        stats["playbooks"] = len(playbook_ids)

        # 8. Create world-class journeys (2025-2026 Best Practices)
        journeys_data = get_world_class_journeys()

        journey_ids = []
        total_steps = 0
        for j_data in journeys_data:
            # Extract steps before creating journey
            steps_data = j_data.pop("steps", [])

            journey = Journey(**j_data)
            db.add(journey)
            await db.flush()
            journey_ids.append(journey.id)

            # Add steps with detailed content
            for i, step_data in enumerate(steps_data, 1):
                step_data["step_order"] = i
                step_data["journey_id"] = journey.id
                step = JourneyStep(**step_data)
                db.add(step)
                total_steps += 1

        await db.commit()
        stats["journeys"] = len(journey_ids)
        stats["journey_steps"] = total_steps

        # 9. Create tasks
        task_templates = [
            {"title": "Quarterly check-in call", "task_type": "call", "category": "relationship", "priority": "medium"},
            {"title": "Review usage metrics", "task_type": "review", "category": "adoption", "priority": "low"},
            {"title": "Send training resources", "task_type": "email", "category": "onboarding", "priority": "medium"},
            {"title": "Schedule QBR", "task_type": "meeting", "category": "relationship", "priority": "high"},
            {"title": "Follow up on support ticket", "task_type": "follow_up", "category": "support", "priority": "high"},
        ]

        tasks = []
        statuses = ['pending', 'in_progress', 'completed', 'blocked', 'snoozed']

        for cid in customer_ids:
            num_tasks = random.randint(1, 3)
            for template in random.sample(task_templates, min(num_tasks, len(task_templates))):
                task_status = random.choice(statuses)
                task = CSTask(
                    customer_id=cid,
                    title=template["title"],
                    task_type=template["task_type"],
                    category=template["category"],
                    priority=template["priority"],
                    status=task_status,
                    due_date=date.today() + timedelta(days=random.randint(-10, 30)),
                    source="seed_script",
                )
                if task_status == 'completed':
                    task.completed_at = datetime.now() - timedelta(days=random.randint(0, 5))
                    task.outcome = random.choice(['successful', 'rescheduled', 'no_response'])
                tasks.append(task)

        db.add_all(tasks)
        await db.commit()
        stats["tasks"] = len(tasks)

        # 10. Create touchpoints
        touchpoint_types = ['email_sent', 'email_opened', 'call_outbound', 'call_inbound', 'meeting_held', 'product_login']
        touchpoints = []

        for cid in customer_ids:
            for _ in range(random.randint(3, 8)):
                tp_type = random.choice(touchpoint_types)
                touchpoint = Touchpoint(
                    customer_id=cid,
                    touchpoint_type=tp_type,
                    channel=random.choice(['email', 'phone', 'in_app', 'video']),
                    direction='outbound' if 'sent' in tp_type or 'outbound' in tp_type else 'inbound',
                    sentiment_label=random.choice(['positive', 'neutral', 'negative']) if 'call' in tp_type or 'meeting' in tp_type else None,
                    occurred_at=datetime.now() - timedelta(days=random.randint(1, 180)),
                    source='seed_script',
                )
                touchpoints.append(touchpoint)

        db.add_all(touchpoints)
        await db.commit()
        stats["touchpoints"] = len(touchpoints)

        # 11. Create journey enrollments
        enrollments = []
        for journey_id in journey_ids:
            enrolled = random.sample(customer_ids, int(len(customer_ids) * 0.2))
            for cid in enrolled:
                enrollment = JourneyEnrollment(
                    journey_id=journey_id,
                    customer_id=cid,
                    status=random.choice(['active', 'completed']),
                    steps_completed=random.randint(1, 4),
                    enrolled_by='system:seed'
                )
                enrollments.append(enrollment)

        db.add_all(enrollments)
        await db.commit()
        stats["journey_enrollments"] = len(enrollments)

        # 12. Create playbook executions
        executions = []
        for playbook_id in playbook_ids:
            executed = random.sample(customer_ids, int(len(customer_ids) * 0.15))
            for cid in executed:
                execution = PlaybookExecution(
                    playbook_id=playbook_id,
                    customer_id=cid,
                    status=random.choice(['active', 'completed']),
                    steps_completed=random.randint(1, 4),
                    steps_total=4,
                    triggered_by='system:seed'
                )
                executions.append(execution)

        db.add_all(executions)
        await db.commit()
        stats["playbook_executions"] = len(executions)

        return SeedResponse(
            success=True,
            message="Customer Success test data seeded successfully",
            stats=stats
        )

    except Exception as e:
        logger.error(f"Error seeding data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error seeding data: {str(e)}"
        )


# Temporary endpoint to add journey status column
@router.post("/fix-journey-status")
async def fix_journey_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """Add status column to cs_journeys if it doesn't exist."""
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only admins can run migrations")

    try:
        from sqlalchemy import text

        # Check if column exists
        result = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'cs_journeys' AND column_name = 'status'
        """))
        exists = result.scalar_one_or_none()

        if exists:
            return {"success": True, "message": "Column already exists", "column_exists": True}

        # Create enum type if not exists
        await db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cs_journey_status_enum') THEN
                    CREATE TYPE cs_journey_status_enum AS ENUM ('draft', 'active', 'paused', 'archived');
                END IF;
            END
            $$;
        """))

        # Add the column
        await db.execute(text("""
            ALTER TABLE cs_journeys ADD COLUMN status cs_journey_status_enum DEFAULT 'draft';
        """))

        # Update existing rows
        await db.execute(text("""
            UPDATE cs_journeys SET status = 'draft' WHERE status IS NULL;
        """))

        await db.commit()

        return {"success": True, "message": "Status column added successfully", "column_exists": False}

    except Exception as e:
        logger.error(f"Error adding status column: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {str(e)}"
        )
