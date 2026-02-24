"""
Admin Settings API - System configuration endpoints.

Provides settings management for system, notifications, integrations, and security.
Also provides user management endpoints.
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Depends, Request
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from sqlalchemy import select, delete, func
from datetime import datetime, timedelta, date
from decimal import Decimal
import random
import logging

from app.api.deps import CurrentUser, DbSession, get_password_hash
from app.models.user import User
from app.models.technician import Technician
from app.models.system_settings import SystemSettingStore
from app.security.rbac import require_admin, require_superuser
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


# ============ Test Email ============


@router.post("/test-email")
async def test_email(
    request: Request,
    current_user: CurrentUser,
):
    """Send a simple test email to verify Brevo is working."""
    body = await request.json()
    to = body.get("to")
    if not to:
        raise HTTPException(status_code=400, detail="'to' is required")

    from app.services.email_service import EmailService
    svc = EmailService()
    logger.info(f"[TEST-EMAIL] is_configured={svc.is_configured}, api_key={'SET' if svc.api_key else 'MISSING'}, from={svc.from_address}")

    if not svc.is_configured:
        return {"success": False, "error": "Email not configured", "status": svc.get_status()}

    # Simple test with a tiny PDF attachment to prove attachments work
    import base64
    # Minimal valid PDF (just says "Test PDF")
    test_pdf_content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 44>>\nstream\nBT /F1 16 Tf 72 700 Td (Test PDF) Tj ET\nendstream\nendobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\nxref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000266 00000 n \n0000000360 00000 n \ntrailer<</Size 6/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    pdf_b64 = base64.b64encode(test_pdf_content).decode("ascii")

    result = await svc.send_email(
        to=to,
        subject="MAC Septic CRM - Test Email with PDF",
        body="This is a test email from MAC Septic CRM. If you can see the attached PDF, email with attachments is working correctly!",
        html_body="<div style='font-family:Arial;padding:20px'><h2>MAC Septic CRM</h2><p>This is a test email. If you can see the attached PDF, email with attachments is working correctly!</p></div>",
        attachments=[{
            "content": pdf_b64,
            "name": "test-attachment.pdf",
        }],
    )
    logger.info(f"[TEST-EMAIL] Result: {result}")
    return result


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
    _: None = Depends(require_admin),
):
    """List all users. Requires admin access."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    # Batch-resolve technician roles via email match
    non_admin_emails = [u.email for u in users if not u.is_superuser]
    tech_emails: set[str] = set()
    if non_admin_emails:
        tech_result = await db.execute(
            select(Technician.email).where(Technician.email.in_(non_admin_emails))
        )
        tech_emails = {row[0] for row in tech_result.all() if row[0]}

    def resolve_user(u: User) -> dict:
        resp = user_to_response(u)
        if not u.is_superuser and u.email in tech_emails:
            resp["role"] = "technician"
        return resp

    return {"users": [resolve_user(u) for u in users]}


@router.post("/users")
async def create_user(
    request: CreateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
):
    """Create a new user. Requires admin access."""
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

    # Auto-create Technician record when role is "technician"
    # This is required for /auth/me to resolve the technician role via email match
    if request.role == "technician":
        import uuid
        existing_tech = await db.execute(
            select(Technician).where(Technician.email == request.email)
        )
        if not existing_tech.scalar_one_or_none():
            technician = Technician(
                id=uuid.uuid4(),
                first_name=request.first_name,
                last_name=request.last_name,
                email=request.email,
                is_active=True,
            )
            db.add(technician)
            await db.commit()

    return {"user": user_to_response(user)}


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
):
    """Update a user. Requires admin access."""
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
        user.is_superuser = request.role == "admin"
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.password is not None:
        user.hashed_password = get_password_hash(request.password)

    await db.commit()
    await db.refresh(user)

    # Auto-create Technician record when role changed to "technician"
    if request.role == "technician":
        import uuid
        existing_tech = await db.execute(
            select(Technician).where(Technician.email == user.email)
        )
        if not existing_tech.scalar_one_or_none():
            technician = Technician(
                id=uuid.uuid4(),
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                is_active=True,
            )
            db.add(technician)
            await db.commit()

    return {"user": user_to_response(user)}


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
):
    """Deactivate a user (soft delete). Requires admin access."""
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


class PricingBenchmarks(BaseModel):
    """Competitor pricing benchmarks from market research (Competitor Pricing.docx)."""
    conventional_1000gal_pump: float = 500.00
    aerobic_atu_pump: float = 575.00  # midpoint of $550-$600
    aerobic_atu_pump_low: float = 550.00
    aerobic_atu_pump_high: float = 600.00
    per_gallon_overage: float = 0.30  # per gallon over 1500 gal
    overage_threshold_gallons: int = 1500
    dig_access_fee_hourly: float = 175.00
    cc_surcharge_pct: float = 3.5
    notes: str = "Source: Competitor Pricing.docx (OneDrive). Updated 2026-02."


async def _get_settings(db, category: str, model_class):
    """Load settings from DB, falling back to defaults."""
    try:
        result = await db.execute(
            select(SystemSettingStore).where(SystemSettingStore.category == category)
        )
        row = result.scalar_one_or_none()
        if row and row.settings_data:
            return model_class(**row.settings_data)
    except Exception:
        await db.rollback()
    return model_class()


async def _save_settings(db, category: str, settings, user_id: int):
    """Save settings to DB (upsert)."""
    try:
        result = await db.execute(
            select(SystemSettingStore).where(SystemSettingStore.category == category)
        )
        row = result.scalar_one_or_none()
        settings_dict = settings.model_dump()
        if row:
            row.settings_data = settings_dict
            row.updated_by = user_id
        else:
            row = SystemSettingStore(
                category=category,
                settings_data=settings_dict,
                updated_by=user_id,
            )
            db.add(row)
        await db.commit()
    except Exception:
        await db.rollback()
    return settings


@router.get("/settings/system")
async def get_system_settings(
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> SystemSettings:
    """Get system settings. Requires admin access."""
    return await _get_settings(db, "system", SystemSettings)


@router.patch("/settings/system")
async def update_system_settings(
    settings: SystemSettings,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> SystemSettings:
    """Update system settings. Requires admin access."""
    return await _save_settings(db, "system", settings, current_user.id)


@router.get("/settings/notifications")
async def get_notification_settings(
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> NotificationSettings:
    """Get notification settings. Requires admin access."""
    return await _get_settings(db, "notifications", NotificationSettings)


@router.patch("/settings/notifications")
async def update_notification_settings(
    settings: NotificationSettings,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> NotificationSettings:
    """Update notification settings. Requires admin access."""
    return await _save_settings(db, "notifications", settings, current_user.id)


@router.get("/settings/integrations")
async def get_integration_settings(
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> IntegrationSettings:
    """Get integration settings. Requires admin access."""
    return await _get_settings(db, "integrations", IntegrationSettings)


@router.patch("/settings/integrations")
async def update_integration_settings(
    settings: IntegrationSettings,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> IntegrationSettings:
    """Update integration settings. Requires admin access."""
    return await _save_settings(db, "integrations", settings, current_user.id)


@router.get("/settings/security")
async def get_security_settings(
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> SecuritySettings:
    """Get security settings. Requires admin access."""
    return await _get_settings(db, "security", SecuritySettings)


@router.patch("/settings/security")
async def update_security_settings(
    settings: SecuritySettings,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> SecuritySettings:
    """Update security settings. Requires admin access."""
    return await _save_settings(db, "security", settings, current_user.id)


@router.get("/settings/pricing-benchmarks")
async def get_pricing_benchmarks(
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> PricingBenchmarks:
    """Get competitor pricing benchmarks. Requires admin access."""
    return await _get_settings(db, "pricing_benchmarks", PricingBenchmarks)


@router.patch("/settings/pricing-benchmarks")
async def update_pricing_benchmarks(
    settings: PricingBenchmarks,
    db: DbSession,
    current_user: CurrentUser,
    _: None = Depends(require_admin),
) -> PricingBenchmarks:
    """Update competitor pricing benchmarks. Requires admin access."""
    return await _save_settings(db, "pricing_benchmarks", settings, current_user.id)


# ============ Customer Success Seed Data ============

# Fake data for generating customers
FIRST_NAMES = [
    "James",
    "Mary",
    "Robert",
    "Patricia",
    "John",
    "Jennifer",
    "Michael",
    "Linda",
    "David",
    "Elizabeth",
    "William",
    "Barbara",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Christopher",
    "Karen",
    "Charles",
    "Lisa",
    "Daniel",
    "Nancy",
    "Matthew",
    "Betty",
    "Anthony",
    "Margaret",
    "Mark",
    "Sandra",
    "Donald",
    "Ashley",
    "Steven",
    "Kimberly",
    "Paul",
    "Emily",
    "Andrew",
    "Donna",
    "Joshua",
    "Michelle",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Ramirez",
    "Lewis",
    "Robinson",
    "Walker",
]

CITIES = [
    ("Houston", "TX", "77001"),
    ("Austin", "TX", "78701"),
    ("Dallas", "TX", "75201"),
    ("San Antonio", "TX", "78201"),
    ("Fort Worth", "TX", "76101"),
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can seed data")

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
                func.lower(Customer.first_name) == "stephanie", func.lower(Customer.last_name) == "burns"
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
                if first.lower() == "stephanie" and last.lower() == "burns":
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
        result = await db.execute(select(Customer.id).order_by(Customer.id).limit(target_customers))
        customer_ids = [row[0] for row in result.fetchall()]
        stats["customers"] = len(customer_ids)

        # 4. Create segments
        segments_data = [
            {
                "name": "High Value Accounts",
                "description": "High contract value customers",
                "color": "#10B981",
                "segment_type": "dynamic",
                "priority": 10,
            },
            {
                "name": "At Risk - Low Engagement",
                "description": "Customers showing disengagement",
                "color": "#EF4444",
                "segment_type": "dynamic",
                "priority": 5,
            },
            {
                "name": "Growth Candidates",
                "description": "Healthy accounts with expansion potential",
                "color": "#3B82F6",
                "segment_type": "dynamic",
                "priority": 15,
            },
            {
                "name": "New Customers (< 90 days)",
                "description": "Recently onboarded customers",
                "color": "#8B5CF6",
                "segment_type": "dynamic",
                "priority": 20,
            },
            {
                "name": "Champions",
                "description": "Highly engaged advocates",
                "color": "#F59E0B",
                "segment_type": "dynamic",
                "priority": 25,
            },
            {
                "name": "Commercial Accounts",
                "description": "Business customers",
                "color": "#6366F1",
                "segment_type": "dynamic",
                "priority": 30,
            },
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

            overall = int(
                product_adoption * 0.30 + engagement * 0.25 + relationship * 0.15 + financial * 0.20 + support * 0.10
            )
            status_val = "healthy" if overall >= 70 else ("at_risk" if overall >= 40 else "critical")
            trend_roll = random.random()
            trend = "improving" if trend_roll < 0.3 else ("stable" if trend_roll < 0.6 else "declining")

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
                expansion_probability=round(
                    random.uniform(0, 0.5) if status_val == "healthy" else random.uniform(0, 0.2), 3
                ),
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
                memberships.append(
                    CustomerSegment(
                        customer_id=cid,
                        segment_id=sid,
                        is_active=True,
                        entry_reason="Initial segmentation",
                        added_by="system:seed",
                    )
                )
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
            {
                "title": "Follow up on support ticket",
                "task_type": "follow_up",
                "category": "support",
                "priority": "high",
            },
        ]

        tasks = []
        statuses = ["pending", "in_progress", "completed", "blocked", "snoozed"]

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
                if task_status == "completed":
                    task.completed_at = datetime.now() - timedelta(days=random.randint(0, 5))
                    task.outcome = random.choice(["successful", "rescheduled", "no_response"])
                tasks.append(task)

        db.add_all(tasks)
        await db.commit()
        stats["tasks"] = len(tasks)

        # 10. Create touchpoints
        touchpoint_types = [
            "email_sent",
            "email_opened",
            "call_outbound",
            "call_inbound",
            "meeting_held",
            "product_login",
        ]
        touchpoints = []

        for cid in customer_ids:
            for _ in range(random.randint(3, 8)):
                tp_type = random.choice(touchpoint_types)
                touchpoint = Touchpoint(
                    customer_id=cid,
                    touchpoint_type=tp_type,
                    channel=random.choice(["email", "phone", "in_app", "video"]),
                    direction="outbound" if "sent" in tp_type or "outbound" in tp_type else "inbound",
                    sentiment_label=random.choice(["positive", "neutral", "negative"])
                    if "call" in tp_type or "meeting" in tp_type
                    else None,
                    occurred_at=datetime.now() - timedelta(days=random.randint(1, 180)),
                    source="seed_script",
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
                    status=random.choice(["active", "completed"]),
                    steps_completed=random.randint(1, 4),
                    enrolled_by="system:seed",
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
                    status=random.choice(["active", "completed"]),
                    steps_completed=random.randint(1, 4),
                    steps_total=4,
                    triggered_by="system:seed",
                )
                executions.append(execution)

        db.add_all(executions)
        await db.commit()
        stats["playbook_executions"] = len(executions)

        return SeedResponse(success=True, message="Customer Success test data seeded successfully", stats=stats)

    except Exception as e:
        logger.error(f"Error seeding data: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error seeding data: {str(e)}")


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
        result = await db.execute(
            text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'cs_journeys' AND column_name = 'status'
        """)
        )
        exists = result.scalar_one_or_none()

        if exists:
            return {"success": True, "message": "Column already exists", "column_exists": True}

        # Create enum type if not exists
        await db.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'cs_journey_status_enum') THEN
                    CREATE TYPE cs_journey_status_enum AS ENUM ('draft', 'active', 'paused', 'archived');
                END IF;
            END
            $$;
        """)
        )

        # Add the column
        await db.execute(
            text("""
            ALTER TABLE cs_journeys ADD COLUMN status cs_journey_status_enum DEFAULT 'draft';
        """)
        )

        # Update existing rows
        await db.execute(
            text("""
            UPDATE cs_journeys SET status = 'draft' WHERE status IS NULL;
        """)
        )

        await db.commit()

        return {"success": True, "message": "Status column added successfully", "column_exists": False}

    except Exception as e:
        logger.error(f"Error adding status column: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}")


# =============================================================================
# SEED DATA - Central Texas Demo Data
# =============================================================================

# Technicians data
SEED_TECHNICIANS = [
    {
        "first_name": "Marcus",
        "last_name": "Rodriguez",
        "email": "marcus.rodriguez@ecbtx.com",
        "phone": "(512) 555-0101",
        "employee_id": "TECH-001",
        "skills": ["pumping", "repairs", "inspections", "camera"],
        "assigned_vehicle": "Truck-101",
        "vehicle_capacity_gallons": 3500,
        "hourly_rate": 32.00,
        "home_city": "Round Rock",
    },
    {
        "first_name": "Jake",
        "last_name": "Thompson",
        "email": "jake.thompson@ecbtx.com",
        "phone": "(512) 555-0102",
        "employee_id": "TECH-002",
        "skills": ["pumping", "maintenance", "emergency"],
        "assigned_vehicle": "Truck-102",
        "vehicle_capacity_gallons": 3000,
        "hourly_rate": 28.50,
        "home_city": "Georgetown",
    },
    {
        "first_name": "Sarah",
        "last_name": "Chen",
        "email": "sarah.chen@ecbtx.com",
        "phone": "(512) 555-0103",
        "employee_id": "TECH-003",
        "skills": ["inspections", "camera", "installations"],
        "assigned_vehicle": "Truck-103",
        "vehicle_capacity_gallons": 2500,
        "hourly_rate": 30.00,
        "home_city": "Cedar Park",
    },
    {
        "first_name": "David",
        "last_name": "Martinez",
        "email": "david.martinez@ecbtx.com",
        "phone": "(512) 555-0104",
        "employee_id": "TECH-004",
        "skills": ["pumping", "grease_trap", "repairs"],
        "assigned_vehicle": "Truck-104",
        "vehicle_capacity_gallons": 4000,
        "hourly_rate": 29.00,
        "home_city": "Austin",
    },
    {
        "first_name": "Chris",
        "last_name": "Williams",
        "email": "chris.williams@ecbtx.com",
        "phone": "(512) 555-0105",
        "employee_id": "TECH-005",
        "skills": ["pumping", "repairs", "inspections", "camera", "installations", "emergency"],
        "assigned_vehicle": "Truck-105",
        "vehicle_capacity_gallons": 3500,
        "hourly_rate": 35.00,
        "home_city": "Pflugerville",
    },
]

# Customers from real Central Texas permit data
SEED_CUSTOMERS = [
    {
        "first_name": "John",
        "last_name": "Cooke",
        "email": "john.cooke@example.com",
        "phone": "(512) 555-1001",
        "address_line1": "294 Call Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Brad",
        "last_name": "Hoff",
        "email": "brad.hoff@example.com",
        "phone": "(512) 555-1002",
        "address_line1": "495 July Johnson Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Aerobic",
    },
    {
        "first_name": "Robert",
        "last_name": "Bitterli",
        "email": "robert.bitterli@example.com",
        "phone": "(512) 555-1003",
        "address_line1": "1911 Lohman Ford Rd",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "customer_type": "commercial",
        "tank_size_gallons": 2000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Thomas",
        "last_name": "Vetter",
        "email": "thomas.vetter@example.com",
        "phone": "(512) 555-1004",
        "address_line1": "12961 Trail Driver",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Keith",
        "last_name": "Hansen",
        "email": "keith.hansen@example.com",
        "phone": "(512) 555-1005",
        "address_line1": "855 Gato Del Sol Ave",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "ATU",
    },
    {
        "first_name": "William",
        "last_name": "Curtis",
        "email": "william.curtis@example.com",
        "phone": "(830) 555-1006",
        "address_line1": "3106 Golf Course Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 2000,
        "system_type": "Mound",
    },
    {
        "first_name": "Darrell",
        "last_name": "Minton",
        "email": "darrell.minton@example.com",
        "phone": "(512) 555-1007",
        "address_line1": "428 Big Brown Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1250,
        "system_type": "Conventional",
    },
    {
        "first_name": "Bobby",
        "last_name": "Dean",
        "email": "bobby.dean@example.com",
        "phone": "(512) 555-1008",
        "address_line1": "623 July Johnson Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1250,
        "system_type": "Chamber",
    },
    {
        "first_name": "Tommy",
        "last_name": "Mathis",
        "email": "tommy.mathis@lonestarbrewing.com",
        "phone": "(512) 555-1009",
        "address_line1": "2110 County Road 118",
        "city": "Burnet",
        "state": "TX",
        "postal_code": "78611",
        "customer_type": "commercial",
        "tank_size_gallons": 2500,
        "system_type": "Grease Trap",
    },
    {
        "first_name": "Alfred",
        "last_name": "Stone",
        "email": "alfred.stone@example.com",
        "phone": "(512) 555-1010",
        "address_line1": "11104 Trails End Rd",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "John",
        "last_name": "Miller",
        "email": "john.miller@example.com",
        "phone": "(830) 555-1011",
        "address_line1": "2905 Blue Lake Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Conventional",
    },
    {
        "first_name": "Charles",
        "last_name": "Castro",
        "email": "charles.castro@example.com",
        "phone": "(830) 555-1012",
        "address_line1": "406 Lakeview Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Aerobic",
    },
    {
        "first_name": "Eugene",
        "last_name": "Zimmermann",
        "email": "eugene.zimmermann@example.com",
        "phone": "(325) 555-1013",
        "address_line1": "4016 River Oaks Dr",
        "city": "Kingsland",
        "state": "TX",
        "postal_code": "78639",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Conventional",
    },
    {
        "first_name": "Robert",
        "last_name": "Anderson",
        "email": "robert.anderson@example.com",
        "phone": "(512) 555-1014",
        "address_line1": "129 Lakeway Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78734",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Steven",
        "last_name": "Wellman",
        "email": "steven.wellman@example.com",
        "phone": "(512) 555-1015",
        "address_line1": "1305 Cat Hollow Club Dr",
        "city": "Spicewood",
        "state": "TX",
        "postal_code": "78669",
        "customer_type": "residential",
        "tank_size_gallons": 2000,
        "system_type": "ATU",
    },
]

# Prospects from real Central Texas permit data
SEED_PROSPECTS = [
    {
        "first_name": "Dennis",
        "last_name": "Glover",
        "email": "dennis.glover@example.com",
        "phone": "(512) 555-2001",
        "address_line1": "21802 Mockingbird St",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "qualified",
        "estimated_value": 4500.00,
        "lead_source": "Google",
        "lead_notes": "ATU repair needed - compressor failing",
    },
    {
        "first_name": "Teresa",
        "last_name": "Wildi",
        "email": "teresa.wildi@example.com",
        "phone": "(512) 555-2002",
        "address_line1": "18222 Center St",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "new_lead",
        "estimated_value": 350.00,
        "lead_source": "Referral",
        "lead_notes": "Due for routine pump out",
    },
    {
        "first_name": "Michael",
        "last_name": "Kaspar",
        "email": "michael.kaspar@example.com",
        "phone": "(512) 555-2003",
        "address_line1": "21909 Surrey Ln",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "quoted",
        "estimated_value": 8200.00,
        "lead_source": "Website",
        "lead_notes": "New septic system installation",
    },
    {
        "first_name": "Jester King",
        "last_name": "Holdings LLC",
        "email": "info@jesterkingbrewery.com",
        "phone": "(512) 555-2004",
        "address_line1": "13187 Fitzhugh Rd",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78736",
        "prospect_stage": "negotiation",
        "estimated_value": 12000.00,
        "lead_source": "Cold Call",
        "lead_notes": "Commercial brewery - multiple grease traps",
        "customer_type": "commercial",
    },
    {
        "first_name": "Harriet",
        "last_name": "Brandon",
        "email": "harriet.brandon@example.com",
        "phone": "(830) 555-2005",
        "address_line1": "613 Highland Dr",
        "city": "Marble Falls",
        "state": "TX",
        "postal_code": "78654",
        "prospect_stage": "contacted",
        "estimated_value": 450.00,
        "lead_source": "Facebook",
        "lead_notes": "Inspection request before home sale",
    },
    {
        "first_name": "Jack",
        "last_name": "O'Leary",
        "email": "jack.oleary@example.com",
        "phone": "(512) 555-2006",
        "address_line1": "8621 Grandview Dr",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "qualified",
        "estimated_value": 2800.00,
        "lead_source": "Google",
        "lead_notes": "ATU maintenance contract inquiry",
    },
    {
        "first_name": "James",
        "last_name": "Collins",
        "email": "james.collins@example.com",
        "phone": "(512) 555-2007",
        "address_line1": "716 Cutlass",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "quoted",
        "estimated_value": 6500.00,
        "lead_source": "Referral",
        "lead_notes": "Quarterly service contract for lakefront property",
    },
    {
        "first_name": "Kimberly",
        "last_name": "McDonald",
        "email": "kimberly.mcdonald@example.com",
        "phone": "(512) 555-2008",
        "address_line1": "128 Firebird St",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "new_lead",
        "estimated_value": 375.00,
        "lead_source": "Yelp",
        "lead_notes": "Residential pump out request",
    },
    {
        "first_name": "Daniel",
        "last_name": "Yannitell",
        "email": "daniel.yannitell@example.com",
        "phone": "(512) 555-2009",
        "address_line1": "4001 Outpost Trce",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "negotiation",
        "estimated_value": 24000.00,
        "lead_source": "Website",
        "lead_notes": "Multi-unit property - annual contract negotiation",
        "customer_type": "commercial",
    },
    {
        "first_name": "Patrick",
        "last_name": "Wendland",
        "email": "patrick.wendland@example.com",
        "phone": "(512) 555-2010",
        "address_line1": "915 Porpoise St",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "contacted",
        "estimated_value": 1200.00,
        "lead_source": "Door-to-door",
        "lead_notes": "Inspection + pump out combo requested",
    },
]


@router.post("/seed/central-texas")
async def seed_central_texas_data(
    db: DbSession,
    current_user: CurrentUser,
):
    """Seed Central Texas demo data (technicians, customers, prospects)."""
    import uuid
    from sqlalchemy import text

    results = {
        "technicians": {"created": 0, "skipped": 0},
        "customers": {"created": 0, "skipped": 0},
        "prospects": {"created": 0, "skipped": 0},
    }

    try:
        # Seed Technicians
        for tech in SEED_TECHNICIANS:
            result = await db.execute(
                text("SELECT id FROM technicians WHERE employee_id = :emp_id"), {"emp_id": tech["employee_id"]}
            )
            if result.fetchone():
                results["technicians"]["skipped"] += 1
                continue

            tech_id = str(uuid.uuid4())
            await db.execute(
                text("""
                    INSERT INTO technicians (
                        id, first_name, last_name, email, phone, employee_id,
                        skills, assigned_vehicle, vehicle_capacity_gallons,
                        hourly_rate, home_city, home_state, is_active, created_at
                    ) VALUES (
                        :id, :first_name, :last_name, :email, :phone, :employee_id,
                        :skills, :assigned_vehicle, :vehicle_capacity_gallons,
                        :hourly_rate, :home_city, 'TX', true, NOW()
                    )
                """),
                {**tech, "id": tech_id, "skills": tech["skills"]},
            )
            results["technicians"]["created"] += 1

        # Seed Customers
        for cust in SEED_CUSTOMERS:
            result = await db.execute(text("SELECT id FROM customers WHERE email = :email"), {"email": cust["email"]})
            if result.fetchone():
                results["customers"]["skipped"] += 1
                continue

            await db.execute(
                text("""
                    INSERT INTO customers (
                        first_name, last_name, email, phone,
                        address_line1, city, state, postal_code,
                        customer_type, tank_size_gallons, system_type,
                        is_active, created_at
                    ) VALUES (
                        :first_name, :last_name, :email, :phone,
                        :address_line1, :city, :state, :postal_code,
                        :customer_type, :tank_size_gallons, :system_type,
                        true, NOW()
                    )
                """),
                cust,
            )
            results["customers"]["created"] += 1

        # Seed Prospects
        for prospect in SEED_PROSPECTS:
            result = await db.execute(
                text("SELECT id FROM customers WHERE email = :email"), {"email": prospect["email"]}
            )
            if result.fetchone():
                results["prospects"]["skipped"] += 1
                continue

            await db.execute(
                text("""
                    INSERT INTO customers (
                        first_name, last_name, email, phone,
                        address_line1, city, state, postal_code,
                        prospect_stage, estimated_value, lead_source, lead_notes,
                        customer_type, is_active, created_at
                    ) VALUES (
                        :first_name, :last_name, :email, :phone,
                        :address_line1, :city, :state, :postal_code,
                        :prospect_stage, :estimated_value, :lead_source, :lead_notes,
                        :customer_type, true, NOW()
                    )
                """),
                {**prospect, "customer_type": prospect.get("customer_type", "residential")},
            )
            results["prospects"]["created"] += 1

        await db.commit()

        return {"success": True, "message": "Central Texas data seeded successfully", "results": results}

    except Exception as e:
        logger.error(f"Error seeding Central Texas data: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}")


# ============ Database Migration Endpoints ============


@router.get("/migrations/status")
async def get_migration_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get current alembic migration status."""
    from sqlalchemy import text

    try:
        result = await db.execute(text("SELECT version_num FROM alembic_version"))
        row = result.fetchone()
        current_version = row[0] if row else None

        # List expected migrations
        expected_migrations = [
            "000_create_base_tables",
            "001_add_technicians_and_invoices",
            "002_add_payments_quotes_sms_consent",
            "003_add_activities",
            "004_add_tickets_equipment_inventory",
            "005_add_all_phase_tables",
            "006_fix_call_logs_schema",
            "007_add_call_dispositions",
            "008_add_compliance_tables",
            "009_add_contracts_tables",
            "010_add_job_costs_table",
            "011_add_oauth_tables",
            "012_add_customer_success_platform",
            "013_fix_journey_schema",
            "014_seed_journey_steps",
            "015_make_test_user_admin",
            "016_add_role_views_tables",
            "017_add_journey_status_column",
            "018_cs_platform_tables",
            "019_fix_dropped_columns",
            "020_survey_enhancements",
            "021_add_smart_segments",
            "022_add_call_intelligence_columns",
            "023_add_septic_permit_tables",
        ]

        return {
            "current_version": current_version,
            "expected_latest": expected_migrations[-1] if expected_migrations else None,
            "needs_upgrade": current_version != expected_migrations[-1] if current_version else True,
            "expected_migrations": expected_migrations,
        }
    except Exception as e:
        logger.error(f"Error checking migration status: {e}")
        return {"current_version": None, "error": str(e)}


@router.post("/migrations/run")
async def run_migrations(
    current_user: CurrentUser,
):
    """Run pending alembic migrations. This is a blocking operation."""
    import subprocess
    import os

    try:
        # Get the project root directory (where alembic.ini is)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        # Run alembic upgrade head
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        success = result.returncode == 0

        return {"success": success, "stdout": result.stdout, "stderr": result.stderr, "return_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Migration timed out after 120 seconds"}
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        return {"success": False, "error": str(e)}


@router.post("/migrations/create-work-order-enums")
async def create_work_order_enums(
    db: DbSession,
    current_user: CurrentUser,
):
    """Create work order ENUM types if they don't exist."""
    from sqlalchemy import text

    results = {}

    try:
        # Create work_order_status_enum
        await db.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'work_order_status_enum') THEN
                    CREATE TYPE work_order_status_enum AS ENUM (
                        'draft', 'scheduled', 'confirmed', 'enroute', 'on_site',
                        'in_progress', 'completed', 'canceled', 'requires_followup'
                    );
                END IF;
            END
            $$;
        """)
        )
        results["work_order_status_enum"] = "created or exists"

        # Create work_order_job_type_enum
        await db.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'work_order_job_type_enum') THEN
                    CREATE TYPE work_order_job_type_enum AS ENUM (
                        'pumping', 'inspection', 'repair', 'installation',
                        'emergency', 'maintenance', 'grease_trap', 'camera_inspection'
                    );
                END IF;
            END
            $$;
        """)
        )
        results["work_order_job_type_enum"] = "created or exists"

        # Create work_order_priority_enum
        await db.execute(
            text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'work_order_priority_enum') THEN
                    CREATE TYPE work_order_priority_enum AS ENUM (
                        'low', 'normal', 'high', 'urgent', 'emergency'
                    );
                END IF;
            END
            $$;
        """)
        )
        results["work_order_priority_enum"] = "created or exists"

        await db.commit()

        return {"success": True, "results": results}

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating ENUM types: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}")


@router.post("/migrations/create-missing-tables")
async def create_missing_tables(
    db: DbSession,
    current_user: CurrentUser,
):
    """Create missing role_views and user_role_sessions tables manually."""
    from sqlalchemy import text

    results = {
        "role_views": {"created": False, "error": None},
        "user_role_sessions": {"created": False, "error": None},
        "seed_roles": {"success": False, "error": None},
    }

    try:
        # Check if role_views exists
        check = await db.execute(
            text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'role_views'
            )
        """)
        )
        role_views_exists = check.scalar()

        if not role_views_exists:
            # Create role_views table
            await db.execute(
                text("""
                CREATE TABLE role_views (
                    id SERIAL PRIMARY KEY,
                    role_key VARCHAR(50) NOT NULL UNIQUE,
                    display_name VARCHAR(100) NOT NULL,
                    description VARCHAR(500),
                    icon VARCHAR(10),
                    color VARCHAR(20),
                    visible_modules JSONB DEFAULT '[]'::jsonb,
                    default_route VARCHAR(100) DEFAULT '/',
                    dashboard_widgets JSONB DEFAULT '[]'::jsonb,
                    quick_actions JSONB DEFAULT '[]'::jsonb,
                    features JSONB DEFAULT '{}'::jsonb,
                    is_active BOOLEAN DEFAULT true,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                )
            """)
            )
            await db.execute(text("CREATE INDEX ix_role_views_role_key ON role_views (role_key)"))
            results["role_views"]["created"] = True
            logger.info("Created role_views table")
        else:
            results["role_views"]["error"] = "Table already exists"

        # Check if user_role_sessions exists
        check = await db.execute(
            text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_role_sessions'
            )
        """)
        )
        sessions_exists = check.scalar()

        if not sessions_exists:
            # Create user_role_sessions table
            await db.execute(
                text("""
                CREATE TABLE user_role_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES api_users(id) ON DELETE CASCADE,
                    current_role_key VARCHAR(50) NOT NULL REFERENCES role_views(role_key) ON DELETE CASCADE,
                    switched_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            )
            await db.execute(text("CREATE INDEX ix_user_role_sessions_user_id ON user_role_sessions (user_id)"))
            results["user_role_sessions"]["created"] = True
            logger.info("Created user_role_sessions table")
        else:
            results["user_role_sessions"]["error"] = "Table already exists"

        # Seed default roles if role_views was just created or is empty
        if results["role_views"]["created"]:
            await db.execute(
                text("""
                INSERT INTO role_views (role_key, display_name, description, icon, color, sort_order, visible_modules, default_route, dashboard_widgets, quick_actions, features, is_active)
                VALUES
                ('admin', 'Administrator', 'Full system access with all features and settings', '👑', 'purple', 1, '["*"]', '/', '["revenue_chart", "work_orders_summary", "customer_health", "team_performance"]', '["create_work_order", "add_customer", "view_reports", "manage_users"]', '{"can_manage_users": true, "can_view_reports": true, "can_manage_settings": true}', true),
                ('executive', 'Executive', 'High-level KPIs, financial metrics, and business intelligence', '📊', 'blue', 2, '["dashboard", "reports", "analytics", "customer-success"]', '/', '["revenue_kpi", "customer_growth", "profitability", "forecasts"]', '["view_reports", "export_data", "schedule_review"]', '{"can_view_reports": true, "can_export_data": true}', true),
                ('manager', 'Operations Manager', 'Day-to-day operations, team management, and scheduling oversight', '📋', 'green', 3, '["dashboard", "schedule", "work-orders", "technicians", "customers", "reports"]', '/schedule', '["today_schedule", "team_availability", "pending_work_orders", "customer_issues"]', '["create_work_order", "assign_technician", "view_schedule", "contact_customer"]', '{"can_assign_work": true, "can_view_reports": true, "can_manage_schedule": true}', true),
                ('technician', 'Field Technician', 'Mobile-optimized view for field work and service completion', '🔧', 'orange', 4, '["my-schedule", "work-orders", "customers", "equipment"]', '/my-schedule', '["my_jobs_today", "next_appointment", "route_map", "time_tracker"]', '["start_job", "complete_job", "add_notes", "call_customer"]', '{"can_update_work_orders": true, "can_capture_photos": true, "can_collect_signatures": true}', true),
                ('phone_agent', 'Phone Agent', 'Customer service focus with quick access to customer info and scheduling', '📞', 'cyan', 5, '["customers", "work-orders", "schedule", "communications"]', '/customers', '["incoming_calls", "customer_search", "recent_interactions", "quick_schedule"]', '["search_customer", "create_work_order", "schedule_appointment", "send_sms"]', '{"can_create_work_orders": true, "can_schedule": true, "can_communicate": true}', true),
                ('dispatcher', 'Dispatcher', 'Schedule management, route optimization, and real-time tracking', '🗺️', 'indigo', 6, '["schedule", "schedule-map", "work-orders", "technicians", "fleet"]', '/schedule-map', '["live_map", "unassigned_jobs", "technician_status", "route_efficiency"]', '["assign_job", "optimize_routes", "contact_technician", "reschedule"]', '{"can_assign_work": true, "can_manage_schedule": true, "can_track_fleet": true}', true),
                ('billing', 'Billing Specialist', 'Invoicing, payments, and financial operations', '💰', 'emerald', 7, '["invoices", "payments", "customers", "reports"]', '/invoices', '["outstanding_invoices", "payments_today", "aging_report", "collection_queue"]', '["create_invoice", "record_payment", "send_reminder", "generate_statement"]', '{"can_manage_invoices": true, "can_process_payments": true, "can_view_financial_reports": true}', true)
                ON CONFLICT (role_key) DO NOTHING
            """)
            )
            results["seed_roles"]["success"] = True
            logger.info("Seeded default roles")

        await db.commit()

        return {"success": True, "results": results}

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating tables: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error: {str(e)}")


@router.post("/fix-pay-rate-schema")
async def fix_pay_rate_schema(
    db: DbSession,
    current_user: CurrentUser,
):
    """Fix missing columns in technician_pay_rates table.

    This endpoint adds the pay_type and salary_amount columns if they don't exist.
    """
    from sqlalchemy import text

    results = {
        "pay_type_column": {"existed": False, "added": False},
        "salary_amount_column": {"existed": False, "added": False},
        "hourly_rate_nullable": {"was_nullable": False, "made_nullable": False},
    }

    try:
        # Check and add pay_type column
        result = await db.execute(
            text(
                """SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'technician_pay_rates' AND column_name = 'pay_type'
            )"""
            )
        )
        pay_type_exists = result.scalar()
        results["pay_type_column"]["existed"] = pay_type_exists

        if not pay_type_exists:
            await db.execute(
                text("ALTER TABLE technician_pay_rates ADD COLUMN pay_type VARCHAR(20) DEFAULT 'hourly' NOT NULL")
            )
            results["pay_type_column"]["added"] = True
            logger.info("Added pay_type column")

        # Check and add salary_amount column
        result = await db.execute(
            text(
                """SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'technician_pay_rates' AND column_name = 'salary_amount'
            )"""
            )
        )
        salary_exists = result.scalar()
        results["salary_amount_column"]["existed"] = salary_exists

        if not salary_exists:
            await db.execute(text("ALTER TABLE technician_pay_rates ADD COLUMN salary_amount FLOAT"))
            results["salary_amount_column"]["added"] = True
            logger.info("Added salary_amount column")

        # Check and make hourly_rate nullable
        result = await db.execute(
            text(
                """SELECT is_nullable FROM information_schema.columns
               WHERE table_name = 'technician_pay_rates' AND column_name = 'hourly_rate'"""
            )
        )
        row = result.fetchone()
        if row:
            results["hourly_rate_nullable"]["was_nullable"] = row[0] == "YES"
            if row[0] == "NO":
                await db.execute(text("ALTER TABLE technician_pay_rates ALTER COLUMN hourly_rate DROP NOT NULL"))
                results["hourly_rate_nullable"]["made_nullable"] = True
                logger.info("Made hourly_rate nullable")

        await db.commit()
        return {"success": True, "results": results}

    except Exception as e:
        await db.rollback()
        logger.error(f"Error fixing pay rate schema: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {type(e).__name__}: {str(e)}")


@router.post("/data/normalize-names")
async def normalize_names(
    db: DbSession,
    current_user: CurrentUser,
):
    """Normalize name casing and phone formatting across all records.

    Title-cases first_name, last_name, city. Formats US phone numbers as (XXX) XXX-XXXX.
    """
    import re
    from sqlalchemy import text

    require_admin(current_user)

    results = {"customers_updated": 0, "work_orders_updated": 0, "technicians_updated": 0}

    try:
        # Normalize customer names/cities
        cust_result = await db.execute(text("SELECT id, first_name, last_name, city, phone FROM customers"))
        customers = cust_result.fetchall()
        for c in customers:
            updates = {}
            if c[1] and c[1] != c[1].strip().title():
                updates["first_name"] = c[1].strip().title()
            if c[2] and c[2] != c[2].strip().title():
                updates["last_name"] = c[2].strip().title()
            if c[3] and c[3] != c[3].strip().title():
                updates["city"] = c[3].strip().title()
            if c[4]:
                digits = re.sub(r"\\D", "", c[4])
                if len(digits) == 11 and digits[0] == "1":
                    digits = digits[1:]
                if len(digits) == 10:
                    formatted = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
                    if formatted != c[4]:
                        updates["phone"] = formatted
            if updates:
                ALLOWED_CUSTOMER_COLS = {"first_name", "last_name", "city", "phone"}
                safe_keys = [k for k in updates if k in ALLOWED_CUSTOMER_COLS]
                set_clause = ", ".join(f"{k} = :{k}" for k in safe_keys)
                updates["cid"] = str(c[0])
                await db.execute(text(f"UPDATE customers SET {set_clause} WHERE id = :cid"), updates)
                results["customers_updated"] += 1

        # Normalize work order assigned_technician and service_city
        wo_result = await db.execute(text("SELECT id, assigned_technician, service_city FROM work_orders"))
        work_orders = wo_result.fetchall()
        for wo in work_orders:
            updates = {}
            if wo[1] and wo[1] != wo[1].strip().title():
                updates["assigned_technician"] = wo[1].strip().title()
            if wo[2] and wo[2] != wo[2].strip().title():
                updates["service_city"] = wo[2].strip().title()
            if updates:
                ALLOWED_WO_COLS = {"assigned_technician", "service_city"}
                safe_keys = [k for k in updates if k in ALLOWED_WO_COLS]
                set_clause = ", ".join(f"{k} = :{k}" for k in safe_keys)
                updates["wid"] = str(wo[0])
                await db.execute(text(f"UPDATE work_orders SET {set_clause} WHERE id = :wid"), updates)
                results["work_orders_updated"] += 1

        # Normalize technician names
        tech_result = await db.execute(text("SELECT id, first_name, last_name FROM technicians"))
        techs = tech_result.fetchall()
        for t in techs:
            updates = {}
            if t[1] and t[1] != t[1].strip().title():
                updates["first_name"] = t[1].strip().title()
            if t[2] and t[2] != t[2].strip().title():
                updates["last_name"] = t[2].strip().title()
            if updates:
                ALLOWED_TECH_COLS = {"first_name", "last_name"}
                safe_keys = [k for k in updates if k in ALLOWED_TECH_COLS]
                set_clause = ", ".join(f"{k} = :{k}" for k in safe_keys)
                updates["tid"] = str(t[0])
                await db.execute(text(f"UPDATE technicians SET {set_clause} WHERE id = :tid"), updates)
                results["technicians_updated"] += 1

        await db.commit()
        return {"success": True, "results": results}

    except Exception as e:
        await db.rollback()
        logger.error(f"Error normalizing data: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {type(e).__name__}: {str(e)}")


@router.post("/data/fix-call-logs-schema")
async def fix_call_logs_schema(
    db: DbSession,
    current_user: CurrentUser,
):
    """Drop FK constraint on call_logs.rc_account_id and make it nullable for imports."""
    from sqlalchemy import text

    require_admin(current_user)

    results = {}
    try:
        await db.execute(text(
            "ALTER TABLE call_logs DROP CONSTRAINT IF EXISTS call_logs_rc_account_id_fkey"
        ))
        results["fk_dropped"] = True
        await db.execute(text(
            "ALTER TABLE call_logs ALTER COLUMN rc_account_id DROP NOT NULL"
        ))
        results["rc_account_id_nullable"] = True
        await db.commit()
        return {"success": True, "results": results}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/add-archive-column")
async def add_archive_column(
    db: DbSession,
    current_user: CurrentUser,
):
    """Add is_archived column to customers table if it doesn't exist."""
    from sqlalchemy import text

    require_admin(current_user)

    try:
        # Check if column exists
        result = await db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'customers' AND column_name = 'is_archived'"
        ))
        exists = result.fetchone()
        if exists:
            return {"success": True, "message": "Column already exists"}

        await db.execute(text(
            "ALTER TABLE customers ADD COLUMN is_archived BOOLEAN DEFAULT FALSE"
        ))
        await db.execute(text(
            "CREATE INDEX ix_customers_is_archived ON customers (is_archived)"
        ))
        await db.commit()
        return {"success": True, "message": "Column added"}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/archive-legacy-imports")
async def archive_legacy_imports(
    db: DbSession,
    current_user: CurrentUser,
):
    """Archive all customers imported from OneDrive (lead_source='import' or 'research')
    that have prospect_stage='new_lead' and were bulk-imported."""
    from sqlalchemy import text

    require_admin(current_user)

    try:
        # Archive customers where lead_source indicates import
        result = await db.execute(text("""
            UPDATE customers
            SET is_archived = TRUE
            WHERE is_archived IS NOT TRUE
              AND (lead_source IN ('import', 'research', 'unknown'))
              AND prospect_stage = 'new_lead'
              AND (tags IS NULL OR tags NOT LIKE '%do_not_archive%')
        """))
        archived_count = result.rowcount

        await db.commit()
        return {
            "success": True,
            "archived_count": archived_count,
            "message": f"Archived {archived_count} legacy import records"
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/data/unarchive-customers")
async def unarchive_customers(
    db: DbSession,
    current_user: CurrentUser,
    customer_ids: list[str] = None,
    unarchive_all: bool = False,
):
    """Unarchive specific customers or all archived customers."""
    from sqlalchemy import text

    require_admin(current_user)

    try:
        if unarchive_all:
            result = await db.execute(text("UPDATE customers SET is_archived = FALSE WHERE is_archived = TRUE"))
            count = result.rowcount
        elif customer_ids:
            result = await db.execute(
                text("UPDATE customers SET is_archived = FALSE WHERE id = ANY(:ids)"),
                {"ids": customer_ids},
            )
            count = result.rowcount
        else:
            return {"success": False, "message": "Provide customer_ids or unarchive_all=true"}

        await db.commit()
        return {"success": True, "unarchived_count": count}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
