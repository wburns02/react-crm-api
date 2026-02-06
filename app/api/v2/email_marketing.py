"""
Email Marketing API - Full implementation with real DB-backed endpoints.

Provides email marketing status, subscription, profiles, templates, segments,
campaigns, AI features, analytics, and onboarding.
"""

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, func as sa_func, text, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import json
import logging
import asyncio

from app.api.deps import CurrentUser, DbSession
from app.models.marketing import MarketingCampaign, EmailTemplate, AISuggestion
from app.models.message import Message
from app.models.customer import Customer
from app.models.system_settings import SystemSettingStore
from app.services.email_service import EmailService
from app.services.ai_gateway import AIGateway

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Pydantic Request/Response Models
# ============================================================================


class SubscriptionResponse(BaseModel):
    tier: str = "manual"
    monthly_price: Optional[float] = None
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    is_active: bool = True


class BusinessProfileResponse(BaseModel):
    business_name: Optional[str] = None
    tagline: Optional[str] = None
    years_in_business: Optional[int] = None
    service_areas: Optional[List[str]] = None
    brand_voice: Optional[str] = None
    onboarding_completed: Optional[bool] = False
    ai_autonomy_level: Optional[str] = None
    monthly_email_budget: Optional[int] = None
    customer_email_limit: Optional[int] = None


class AnalyticsTotals(BaseModel):
    total_sent: int = 0
    total_delivered: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0


class StatusResponse(BaseModel):
    success: bool = True
    subscription: SubscriptionResponse = SubscriptionResponse()
    profile: BusinessProfileResponse = BusinessProfileResponse()
    analytics: AnalyticsTotals = AnalyticsTotals()
    tiers: dict = {
        "none": {"name": "No Email Marketing", "price": 0, "features": []},
        "manual": {"name": "Manual Marketing", "price": 49, "features": ["templates", "segments", "campaigns", "analytics"]},
        "ai_suggested": {"name": "AI-Suggested Marketing", "price": 99, "features": ["templates", "segments", "campaigns", "analytics", "ai_suggestions", "ai_content"]},
        "autonomous": {"name": "Fully Autonomous Marketing", "price": 199, "features": ["templates", "segments", "campaigns", "analytics", "ai_suggestions", "ai_content", "auto_send", "auto_optimize"]},
    }


class SubscriptionUpdateRequest(BaseModel):
    tier: str = "manual"


class ProfileUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    tagline: Optional[str] = None
    years_in_business: Optional[int] = None
    service_areas: Optional[List[str]] = None
    brand_voice: Optional[str] = None
    onboarding_completed: Optional[bool] = None
    ai_autonomy_level: Optional[str] = None
    monthly_email_budget: Optional[int] = None
    customer_email_limit: Optional[int] = None


class TemplateCreateRequest(BaseModel):
    name: str
    category: Optional[str] = None
    subject_template: str
    body_html: str
    body_text: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subject_template: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None


class TemplatePreviewRequest(BaseModel):
    customer_name: Optional[str] = "John Smith"
    first_name: Optional[str] = "John"
    company_name: Optional[str] = "MAC Septic"
    phone: Optional[str] = "(555) 123-4567"


class CampaignCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[str] = None
    segment: Optional[str] = None
    scheduled_at: Optional[str] = None


class AIContentRequest(BaseModel):
    campaign_type: str
    segment: Optional[str] = None
    context: Optional[dict] = None


class AIOptimizeSubjectRequest(BaseModel):
    subject: str
    segment: Optional[str] = None


class OnboardingAnswersRequest(BaseModel):
    answers: Optional[dict] = None


class MarketingPlanRequest(BaseModel):
    answers: Optional[dict] = None


# ============================================================================
# Helper: Load/Save SystemSettings
# ============================================================================


async def _get_setting(db: AsyncSession, category: str) -> dict:
    """Load a settings category from system_settings."""
    result = await db.execute(
        select(SystemSettingStore).where(SystemSettingStore.category == category)
    )
    row = result.scalar_one_or_none()
    return row.settings_data if row else {}


async def _save_setting(db: AsyncSession, category: str, data: dict):
    """Upsert a settings category in system_settings."""
    result = await db.execute(
        select(SystemSettingStore).where(SystemSettingStore.category == category)
    )
    row = result.scalar_one_or_none()
    if row:
        row.settings_data = data
    else:
        row = SystemSettingStore(category=category, settings_data=data)
        db.add(row)
    await db.commit()


# ============================================================================
# Helper: Segment queries
# ============================================================================


async def _get_segment_query(db: AsyncSession, segment_id: str):
    """Build segment filter for customers table. Returns a list of conditions."""
    now = datetime.utcnow()

    if segment_id == "all":
        # All customers with email
        return [Customer.email.isnot(None), Customer.email != ""]
    elif segment_id == "active":
        # Had a completed work order in last 12 months
        twelve_months_ago = now - timedelta(days=365)
        sub = text("""
            EXISTS (
                SELECT 1 FROM work_orders wo
                WHERE wo.customer_id = customers.id
                AND wo.status = 'completed'
                AND wo.completed_date >= :cutoff
            )
        """).bindparams(cutoff=twelve_months_ago)
        return [Customer.email.isnot(None), Customer.email != "", sub]
    elif segment_id == "inactive":
        # No work order in 12+ months
        twelve_months_ago = now - timedelta(days=365)
        sub = text("""
            NOT EXISTS (
                SELECT 1 FROM work_orders wo
                WHERE wo.customer_id = customers.id
                AND wo.status = 'completed'
                AND wo.completed_date >= :cutoff
            )
        """).bindparams(cutoff=twelve_months_ago)
        return [Customer.email.isnot(None), Customer.email != "", sub]
    elif segment_id == "new":
        # Created in last 6 months
        six_months_ago = now - timedelta(days=180)
        return [Customer.email.isnot(None), Customer.email != "",
                Customer.created_at >= six_months_ago]
    elif segment_id == "service_due":
        # Last service 10-14 months ago
        ten_months_ago = now - timedelta(days=300)
        fourteen_months_ago = now - timedelta(days=420)
        sub = text("""
            EXISTS (
                SELECT 1 FROM work_orders wo
                WHERE wo.customer_id = customers.id
                AND wo.status = 'completed'
                AND wo.completed_date BETWEEN :start AND :end
            )
            AND NOT EXISTS (
                SELECT 1 FROM work_orders wo2
                WHERE wo2.customer_id = customers.id
                AND wo2.status = 'completed'
                AND wo2.completed_date > :end
            )
        """).bindparams(start=fourteen_months_ago, end=ten_months_ago)
        return [Customer.email.isnot(None), Customer.email != "", sub]
    elif segment_id == "vip":
        # 3+ completed work orders
        sub = text("""
            (SELECT COUNT(*) FROM work_orders wo
             WHERE wo.customer_id = customers.id
             AND wo.status = 'completed') >= 3
        """)
        return [Customer.email.isnot(None), Customer.email != "", sub]
    else:
        return [Customer.email.isnot(None), Customer.email != ""]


async def _get_segment_count(db: AsyncSession, segment_id: str) -> int:
    """Get count of customers in a segment."""
    conditions = await _get_segment_query(db, segment_id)
    q = select(sa_func.count(Customer.id)).where(*conditions)
    result = await db.execute(q)
    return result.scalar() or 0


# ============================================================================
# Helper: Format campaign for frontend
# ============================================================================


def _format_campaign(c: MarketingCampaign) -> dict:
    """Format a MarketingCampaign row to match frontend campaignSchema."""
    return {
        "id": str(c.id),
        "name": c.name,
        "description": c.description,
        "template_id": str(c.template_id) if c.template_id else None,
        "segment": c.segment,
        "status": c.status or "draft",
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "sent_at": c.sent_at.isoformat() if c.sent_at else None,
        "stats": {
            "total_sent": c.total_sent or 0,
            "delivered": c.total_delivered or 0,
            "opened": c.total_opened or 0,
            "clicked": c.total_clicked or 0,
            "bounced": c.total_bounced or 0,
            "unsubscribed": c.total_unsubscribed or 0,
        },
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _format_template(t: EmailTemplate) -> dict:
    """Format an EmailTemplate row to match frontend emailTemplateSchema."""
    variables = None
    if t.variables:
        if isinstance(t.variables, list):
            # Convert ["customer_name", ...] to [{name: "customer_name"}, ...]
            variables = [{"name": v} if isinstance(v, str) else v for v in t.variables]
        elif isinstance(t.variables, dict):
            variables = [{"name": k, "description": v} for k, v in t.variables.items()]

    return {
        "id": str(t.id),
        "name": t.name,
        "category": t.category,
        "subject_template": t.subject,
        "body_html": t.body_html,
        "body_text": t.body_text,
        "variables": variables,
        "is_system": getattr(t, "is_system", False) or False,
        "is_active": t.is_active if t.is_active is not None else True,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _format_suggestion(s: AISuggestion) -> dict:
    """Format an AISuggestion row to match frontend aiSuggestionSchema."""
    return {
        "id": str(s.id),
        "suggestion_type": s.suggestion_type,
        "title": s.title,
        "description": s.description,
        "target_segment": s.target_segment,
        "estimated_recipients": s.estimated_recipients,
        "estimated_revenue": s.estimated_revenue,
        "priority_score": s.priority_score,
        "ai_rationale": s.ai_rationale,
        "suggested_subject": s.suggested_subject,
        "suggested_body": s.suggested_body,
        "suggested_send_date": s.suggested_send_date.isoformat() if s.suggested_send_date else None,
        "status": s.status or "pending",
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


# ============================================================================
# DB Migration Endpoint
# ============================================================================


@router.post("/fix-tables")
async def fix_email_marketing_tables(db: DbSession, current_user: CurrentUser) -> dict:
    """Add missing columns and create missing tables for email marketing."""
    from app.database import async_session_maker

    results = []

    migrations = [
        # Create marketing_campaigns table if missing
        """CREATE TABLE IF NOT EXISTS marketing_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            description TEXT,
            campaign_type VARCHAR(50) NOT NULL DEFAULT 'manual',
            template_id UUID,
            segment VARCHAR(50),
            target_segment JSONB,
            estimated_audience INTEGER,
            start_date TIMESTAMP WITH TIME ZONE,
            end_date TIMESTAMP WITH TIME ZONE,
            scheduled_at TIMESTAMP WITH TIME ZONE,
            sent_at TIMESTAMP WITH TIME ZONE,
            status VARCHAR(20) DEFAULT 'draft',
            total_sent INTEGER DEFAULT 0,
            total_opened INTEGER DEFAULT 0,
            total_clicked INTEGER DEFAULT 0,
            total_converted INTEGER DEFAULT 0,
            total_delivered INTEGER DEFAULT 0,
            total_bounced INTEGER DEFAULT 0,
            total_unsubscribed INTEGER DEFAULT 0,
            created_by VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE
        )""",
        # Add columns if table already existed without them
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS template_id UUID",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS segment VARCHAR(50)",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS total_delivered INTEGER DEFAULT 0",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS total_bounced INTEGER DEFAULT 0",
        "ALTER TABLE marketing_campaigns ADD COLUMN IF NOT EXISTS total_unsubscribed INTEGER DEFAULT 0",
        # Message campaign_id
        "ALTER TABLE messages ADD COLUMN IF NOT EXISTS campaign_id UUID",
        "CREATE INDEX IF NOT EXISTS ix_messages_campaign_id ON messages (campaign_id)",
        # Create ai_suggestions table
        """CREATE TABLE IF NOT EXISTS ai_suggestions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            suggestion_type VARCHAR(50) NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            target_segment VARCHAR(50),
            estimated_recipients INTEGER,
            estimated_revenue FLOAT,
            priority_score FLOAT,
            ai_rationale TEXT,
            suggested_subject VARCHAR(500),
            suggested_body TEXT,
            suggested_send_date TIMESTAMP WITH TIME ZONE,
            status VARCHAR(20) DEFAULT 'pending',
            campaign_id UUID,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )""",
    ]

    # Execute each migration in its own transaction to avoid cascading failures
    for sql_stmt in migrations:
        async with async_session_maker() as session:
            try:
                await session.execute(text(sql_stmt))
                await session.commit()
                results.append({"sql": sql_stmt[:60], "status": "ok"})
            except Exception as e:
                await session.rollback()
                err = str(e).split("\n")[0][:120]
                results.append({"sql": sql_stmt[:60], "status": "error", "error": err})

    return {"success": True, "migrations": results}


# ============================================================================
# Status & Subscription Endpoints
# ============================================================================


@router.get("/status")
async def get_email_marketing_status(db: DbSession, current_user: CurrentUser) -> dict:
    """Get email marketing integration status with real data."""
    # Load subscription
    sub_data = await _get_setting(db, "email_marketing_subscription")
    subscription = SubscriptionResponse(
        tier=sub_data.get("tier", "manual"),
        monthly_price=sub_data.get("monthly_price"),
        started_at=sub_data.get("started_at"),
        expires_at=sub_data.get("expires_at"),
        is_active=sub_data.get("is_active", True),
    )

    # Load profile
    prof_data = await _get_setting(db, "email_marketing_profile")
    profile = BusinessProfileResponse(**prof_data) if prof_data else BusinessProfileResponse()

    # Compute real analytics totals
    result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_sent), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_delivered), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_opened), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_clicked), 0),
        )
    )
    row = result.one()
    total_sent = row[0]
    total_delivered = row[1]
    total_opened = row[2]
    total_clicked = row[3]

    analytics = AnalyticsTotals(
        total_sent=total_sent,
        total_delivered=total_delivered,
        total_opened=total_opened,
        total_clicked=total_clicked,
        open_rate=round(total_opened / total_sent * 100, 1) if total_sent > 0 else 0,
        click_rate=round(total_clicked / total_sent * 100, 1) if total_sent > 0 else 0,
    )

    return StatusResponse(
        subscription=subscription,
        profile=profile,
        analytics=analytics,
    ).model_dump()


@router.get("/subscription")
async def get_subscription(db: DbSession, current_user: CurrentUser) -> dict:
    """Get subscription details."""
    sub_data = await _get_setting(db, "email_marketing_subscription")
    subscription = SubscriptionResponse(
        tier=sub_data.get("tier", "manual"),
        monthly_price=sub_data.get("monthly_price"),
        started_at=sub_data.get("started_at"),
        expires_at=sub_data.get("expires_at"),
        is_active=sub_data.get("is_active", True),
    )
    return {"success": True, "subscription": subscription.model_dump()}


@router.post("/subscription")
async def update_subscription(
    body: SubscriptionUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update subscription tier."""
    valid_tiers = ["none", "manual", "ai_suggested", "autonomous"]
    if body.tier not in valid_tiers:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {valid_tiers}")

    prices = {"none": 0, "manual": 49, "ai_suggested": 99, "autonomous": 199}
    data = {
        "tier": body.tier,
        "monthly_price": prices.get(body.tier, 0),
        "started_at": datetime.utcnow().isoformat(),
        "is_active": body.tier != "none",
    }
    await _save_setting(db, "email_marketing_subscription", data)
    return {"success": True, "subscription": data}


# ============================================================================
# Profile Endpoints
# ============================================================================


@router.get("/profile")
async def get_profile(db: DbSession, current_user: CurrentUser) -> dict:
    """Get business profile."""
    prof_data = await _get_setting(db, "email_marketing_profile")
    profile = BusinessProfileResponse(**prof_data) if prof_data else BusinessProfileResponse()
    return {"success": True, "profile": profile.model_dump()}


@router.put("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update business profile."""
    existing = await _get_setting(db, "email_marketing_profile")
    update_data = body.model_dump(exclude_none=True)
    existing.update(update_data)
    await _save_setting(db, "email_marketing_profile", existing)
    return {"success": True, "profile": existing}


# ============================================================================
# Template Endpoints (bridge to email_templates table)
# ============================================================================


@router.get("/templates")
async def get_templates(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
    include_system: bool = False,
) -> List[dict]:
    """Get email templates from email_templates table."""
    q = select(EmailTemplate).where(EmailTemplate.is_active == True)
    if category:
        q = q.where(EmailTemplate.category == category)
    q = q.order_by(EmailTemplate.created_at.desc())

    result = await db.execute(q)
    templates = result.scalars().all()
    return [_format_template(t) for t in templates]


@router.get("/templates/{template_id}")
async def get_template(template_id: str, db: DbSession, current_user: CurrentUser) -> dict:
    """Get a specific template."""
    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == tid))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True, "template": _format_template(t)}


@router.post("/templates")
async def create_template(
    body: TemplateCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Create email template."""
    t = EmailTemplate(
        id=uuid.uuid4(),
        name=body.name,
        subject=body.subject_template,
        body_html=body.body_html,
        body_text=body.body_text,
        category=body.category,
        is_active=True,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return {"success": True, "template": _format_template(t)}


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Update email template."""
    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == tid))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    if body.name is not None:
        t.name = body.name
    if body.subject_template is not None:
        t.subject = body.subject_template
    if body.body_html is not None:
        t.body_html = body.body_html
    if body.body_text is not None:
        t.body_text = body.body_text
    if body.category is not None:
        t.category = body.category

    await db.commit()
    await db.refresh(t)
    return {"success": True, "template": _format_template(t)}


@router.post("/templates/{template_id}/preview")
async def preview_template(
    template_id: str,
    body: TemplatePreviewRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Preview email template with sample data."""
    try:
        tid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid template ID")

    result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == tid))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    context = body.model_dump()
    rendered_subject = t.render_subject(context)
    rendered_html = t.render_body_html(context)

    return {
        "success": True,
        "preview": f"<h2>{rendered_subject}</h2>{rendered_html}",
    }


# ============================================================================
# Segment Endpoints (real customer queries)
# ============================================================================


SEGMENT_DEFINITIONS = [
    {"id": "all", "name": "All Customers", "description": "All customers with email addresses"},
    {"id": "active", "name": "Active Customers", "description": "Completed work order in last 12 months"},
    {"id": "inactive", "name": "Inactive Customers", "description": "No work order in 12+ months"},
    {"id": "new", "name": "New Customers", "description": "Created in last 6 months"},
    {"id": "service_due", "name": "Service Due", "description": "Last service 10-14 months ago"},
    {"id": "vip", "name": "VIP Customers", "description": "3+ completed work orders"},
]


@router.get("/segments")
async def get_segments(db: DbSession, current_user: CurrentUser) -> List[dict]:
    """Get customer segments with real counts."""
    segments = []
    for seg_def in SEGMENT_DEFINITIONS:
        count = await _get_segment_count(db, seg_def["id"])
        segments.append({
            "id": seg_def["id"],
            "name": seg_def["name"],
            "description": seg_def.get("description", ""),
            "count": count,
            "criteria": None,
        })
    return segments


@router.get("/segments/{segment}/customers")
async def get_segment_customers(
    segment: str,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 100,
) -> dict:
    """Get customers in a segment."""
    conditions = await _get_segment_query(db, segment)
    q = select(Customer).where(*conditions).limit(limit)
    result = await db.execute(q)
    customers = result.scalars().all()

    customer_list = [
        {
            "id": str(c.id),
            "name": f"{c.first_name or ''} {c.last_name or ''}".strip() or "Unknown",
            "email": c.email,
            "phone": c.phone,
        }
        for c in customers
    ]

    total = await _get_segment_count(db, segment)
    return {"success": True, "customers": customer_list, "total": total}


# ============================================================================
# Campaign Endpoints
# ============================================================================


@router.get("/campaigns")
async def get_campaigns(
    db: DbSession,
    current_user: CurrentUser,
    status: Optional[str] = None,
) -> List[dict]:
    """Get email campaigns."""
    q = select(MarketingCampaign).order_by(MarketingCampaign.created_at.desc())
    if status:
        q = q.where(MarketingCampaign.status == status)
    result = await db.execute(q)
    campaigns = result.scalars().all()
    return [_format_campaign(c) for c in campaigns]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, db: DbSession, current_user: CurrentUser) -> dict:
    """Get a specific campaign."""
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    result = await db.execute(select(MarketingCampaign).where(MarketingCampaign.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"success": True, "campaign": _format_campaign(c)}


@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Create email campaign."""
    estimated = 0
    if body.segment:
        estimated = await _get_segment_count(db, body.segment)

    c = MarketingCampaign(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        campaign_type="manual",
        template_id=uuid.UUID(body.template_id) if body.template_id else None,
        segment=body.segment,
        estimated_audience=estimated,
        status="draft",
        scheduled_at=datetime.fromisoformat(body.scheduled_at) if body.scheduled_at else None,
        created_by=str(current_user.id),
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"success": True, "campaign": _format_campaign(c)}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    campaign_id: str,
    db: DbSession,
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> dict:
    """Send email campaign via Brevo. Uses background tasks for async delivery."""
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    result = await db.execute(select(MarketingCampaign).where(MarketingCampaign.id == cid))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "scheduled"):
        raise HTTPException(status_code=400, detail=f"Campaign cannot be sent (status: {campaign.status})")

    # Load template if set
    template = None
    if campaign.template_id:
        t_result = await db.execute(select(EmailTemplate).where(EmailTemplate.id == campaign.template_id))
        template = t_result.scalar_one_or_none()

    if not template:
        raise HTTPException(status_code=400, detail="Campaign has no template assigned")

    # Get segment customers
    segment_id = campaign.segment or "all"
    conditions = await _get_segment_query(db, segment_id)
    q = select(Customer).where(*conditions)
    cust_result = await db.execute(q)
    customers = cust_result.scalars().all()

    if not customers:
        raise HTTPException(status_code=400, detail="No customers in segment have email addresses")

    # Set status to sending
    campaign.status = "sending"
    await db.commit()

    # Launch background task
    background_tasks.add_task(
        _send_campaign_emails,
        campaign_id=str(campaign.id),
        template_id=str(template.id),
        template_subject=template.subject,
        template_html=template.body_html,
        template_text=template.body_text,
        customers=[{"id": str(c.id), "email": c.email, "first_name": c.first_name, "last_name": c.last_name} for c in customers],
    )

    return {
        "success": True,
        "status": "sending",
        "recipients": len(customers),
        "message": f"Sending to {len(customers)} recipients...",
    }


async def _send_campaign_emails(
    campaign_id: str,
    template_id: str,
    template_subject: str,
    template_html: str,
    template_text: Optional[str],
    customers: List[dict],
):
    """Background task to send campaign emails via Brevo."""
    from app.database import async_session_maker

    email_service = EmailService()
    sent = 0
    failed = 0

    async with async_session_maker() as db:
        for cust in customers:
            context = {
                "customer_name": f"{cust.get('first_name', '')} {cust.get('last_name', '')}".strip() or "Customer",
                "first_name": cust.get("first_name", "Customer"),
                "company_name": "MAC Septic",
            }

            # Render template
            subject = template_subject or "Update from MAC Septic"
            html_body = template_html or ""
            text_body = template_text or ""
            for key, value in context.items():
                subject = subject.replace(f"{{{{{key}}}}}", str(value) if value else "")
                html_body = html_body.replace(f"{{{{{key}}}}}", str(value) if value else "")
                text_body = text_body.replace(f"{{{{{key}}}}}", str(value) if value else "")

            try:
                result = await email_service.send_email(
                    to=cust["email"],
                    subject=subject,
                    body=text_body or subject,
                    html_body=html_body,
                )

                # Create message record
                msg = Message(
                    id=uuid.uuid4(),
                    customer_id=uuid.UUID(cust["id"]),
                    message_type="email",
                    direction="outbound",
                    status="sent" if result.get("success") else "failed",
                    from_email="noreply@macseptic.com",
                    to_email=cust["email"],
                    subject=subject,
                    content=text_body[:500] if text_body else subject,
                    campaign_id=uuid.UUID(campaign_id),
                    external_id=result.get("message_id"),
                    sent_at=datetime.utcnow() if result.get("success") else None,
                    error_message=result.get("error"),
                )
                db.add(msg)

                if result.get("success"):
                    sent += 1
                else:
                    failed += 1

            except Exception as e:
                logger.error(f"Failed to send email to {cust['email']}: {e}")
                failed += 1

            # Rate limit: 100ms between sends
            await asyncio.sleep(0.1)

        # Update campaign metrics
        try:
            c_result = await db.execute(
                select(MarketingCampaign).where(MarketingCampaign.id == uuid.UUID(campaign_id))
            )
            campaign = c_result.scalar_one_or_none()
            if campaign:
                campaign.status = "sent"
                campaign.sent_at = datetime.utcnow()
                campaign.total_sent = sent + failed
                campaign.total_delivered = sent
                campaign.total_bounced = failed
            await db.commit()
            logger.info(f"Campaign {campaign_id} complete: {sent} sent, {failed} failed")
        except Exception as e:
            logger.error(f"Failed to update campaign metrics: {e}")
            await db.rollback()


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, db: DbSession, current_user: CurrentUser) -> dict:
    """Delete email campaign (draft/canceled only)."""
    try:
        cid = uuid.UUID(campaign_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid campaign ID")

    result = await db.execute(select(MarketingCampaign).where(MarketingCampaign.id == cid))
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if c.status not in ("draft", "canceled"):
        raise HTTPException(status_code=400, detail=f"Cannot delete campaign with status '{c.status}'")

    await db.delete(c)
    await db.commit()
    return {"success": True}


# ============================================================================
# AI Endpoints
# ============================================================================


@router.get("/ai/suggestions")
async def get_ai_suggestions(db: DbSession, current_user: CurrentUser) -> dict:
    """Get AI campaign suggestions."""
    result = await db.execute(
        select(AISuggestion).order_by(AISuggestion.created_at.desc()).limit(20)
    )
    suggestions = result.scalars().all()
    return {"success": True, "suggestions": [_format_suggestion(s) for s in suggestions]}


@router.post("/ai/generate-suggestions")
async def generate_suggestions(db: DbSession, current_user: CurrentUser) -> List[dict]:
    """Generate AI suggestions based on customer segments."""
    # Gather segment data for context
    segment_counts = {}
    for seg_def in SEGMENT_DEFINITIONS:
        segment_counts[seg_def["id"]] = await _get_segment_count(db, seg_def["id"])

    # Get recent campaigns
    recent_result = await db.execute(
        select(MarketingCampaign).order_by(MarketingCampaign.created_at.desc()).limit(5)
    )
    recent_campaigns = [
        f"{c.name} ({c.status}, sent: {c.total_sent})"
        for c in recent_result.scalars().all()
    ]

    prompt = f"""You are an email marketing AI for MAC Septic, a septic tank service company.

Based on these customer segments:
{json.dumps(segment_counts, indent=2)}

Recent campaigns: {', '.join(recent_campaigns) if recent_campaigns else 'None yet'}

Generate 3-5 email campaign suggestions as a JSON array. Each suggestion should have:
- suggestion_type: "campaign"
- title: Short campaign name
- description: 1-2 sentence description
- target_segment: one of {list(segment_counts.keys())}
- estimated_recipients: number from segment counts above
- estimated_revenue: estimated revenue impact ($)
- priority_score: 1-10 (10 = highest priority)
- ai_rationale: Why this campaign makes sense
- suggested_subject: Email subject line
- suggested_body: Brief email body (HTML)
- suggested_send_date: ISO date string (within next 30 days)

Focus on practical campaigns: service reminders, seasonal promotions, re-engagement, referral asks.
Respond with ONLY valid JSON array, no markdown."""

    ai = AIGateway()
    try:
        result = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.7,
        )
        content = result.get("content", "[]")

        # Strip markdown code blocks
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("["):
                    content = stripped
                    break

        suggestions_data = json.loads(content)
        if not isinstance(suggestions_data, list):
            suggestions_data = [suggestions_data]

    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"AI suggestion generation failed: {e}")
        # Return sensible defaults
        suggestions_data = [
            {
                "suggestion_type": "campaign",
                "title": "Service Reminder Campaign",
                "description": "Remind customers who haven't had service in 10+ months",
                "target_segment": "service_due",
                "estimated_recipients": segment_counts.get("service_due", 0),
                "estimated_revenue": segment_counts.get("service_due", 0) * 350,
                "priority_score": 9,
                "ai_rationale": "Customers overdue for service are likely to convert with a timely reminder.",
                "suggested_subject": "Time for your septic tank service!",
                "suggested_body": "<p>Hi {{customer_name}},</p><p>It's been a while since your last septic service. Schedule now to keep your system healthy!</p>",
                "suggested_send_date": (datetime.utcnow() + timedelta(days=3)).isoformat(),
            },
            {
                "suggestion_type": "campaign",
                "title": "VIP Thank You",
                "description": "Thank loyal VIP customers with a special offer",
                "target_segment": "vip",
                "estimated_recipients": segment_counts.get("vip", 0),
                "estimated_revenue": segment_counts.get("vip", 0) * 100,
                "priority_score": 7,
                "ai_rationale": "VIP customers drive referrals. A thank-you strengthens loyalty.",
                "suggested_subject": "Thank you for being a valued customer!",
                "suggested_body": "<p>Hi {{customer_name}},</p><p>As one of our most valued customers, we want to say thank you! Enjoy 10% off your next service.</p>",
                "suggested_send_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
            },
        ]

    # Persist suggestions to DB
    created = []
    for sdata in suggestions_data:
        send_date = None
        if sdata.get("suggested_send_date"):
            try:
                send_date = datetime.fromisoformat(str(sdata["suggested_send_date"]).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                send_date = datetime.utcnow() + timedelta(days=7)

        s = AISuggestion(
            id=uuid.uuid4(),
            suggestion_type=sdata.get("suggestion_type", "campaign"),
            title=sdata.get("title", "Untitled Suggestion"),
            description=sdata.get("description"),
            target_segment=sdata.get("target_segment"),
            estimated_recipients=sdata.get("estimated_recipients"),
            estimated_revenue=sdata.get("estimated_revenue"),
            priority_score=sdata.get("priority_score"),
            ai_rationale=sdata.get("ai_rationale"),
            suggested_subject=sdata.get("suggested_subject"),
            suggested_body=sdata.get("suggested_body"),
            suggested_send_date=send_date,
            status="pending",
        )
        db.add(s)
        created.append(s)

    await db.commit()
    # Refresh to get created_at
    for s in created:
        await db.refresh(s)

    return [_format_suggestion(s) for s in created]


@router.post("/ai/suggestions/{suggestion_id}/approve")
async def approve_suggestion(
    suggestion_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Approve AI suggestion and create campaign from it."""
    try:
        sid = uuid.UUID(suggestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid suggestion ID")

    result = await db.execute(select(AISuggestion).where(AISuggestion.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    # Create campaign from suggestion
    campaign = MarketingCampaign(
        id=uuid.uuid4(),
        name=s.title,
        description=s.description,
        campaign_type="ai_suggested",
        segment=s.target_segment,
        estimated_audience=s.estimated_recipients,
        status="draft",
        scheduled_at=s.suggested_send_date,
        created_by=str(current_user.id),
    )
    db.add(campaign)

    # Update suggestion
    s.status = "approved"
    s.campaign_id = campaign.id

    await db.commit()
    await db.refresh(campaign)

    return {"success": True, "campaign_id": str(campaign.id), "campaign": _format_campaign(campaign)}


@router.post("/ai/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(
    suggestion_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Dismiss AI suggestion."""
    try:
        sid = uuid.UUID(suggestion_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid suggestion ID")

    result = await db.execute(select(AISuggestion).where(AISuggestion.id == sid))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Suggestion not found")

    s.status = "rejected"
    await db.commit()
    return {"success": True}


@router.post("/ai/generate-content")
async def generate_content(
    body: AIContentRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Generate email content with AI."""
    segment_info = ""
    if body.segment:
        count = await _get_segment_count(db, body.segment)
        segment_info = f"Target segment: {body.segment} ({count} recipients)"

    prompt = f"""You are an email marketing expert for MAC Septic, a septic tank service company.

Generate a marketing email for:
- Campaign type: {body.campaign_type}
- {segment_info}
{f'- Additional context: {json.dumps(body.context)}' if body.context else ''}

Respond with ONLY valid JSON:
{{
    "subject": "Email subject line",
    "body_html": "HTML email body with <p> tags, professional and concise",
    "body_text": "Plain text version"
}}

Use merge fields: {{{{customer_name}}}}, {{{{first_name}}}} where appropriate.
Keep it professional, friendly, and action-oriented. Include a clear call to action."""

    ai = AIGateway()
    try:
        result = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
        )
        content = result.get("content", "{}")

        # Strip markdown
        if "```" in content:
            parts = content.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("{"):
                    content = stripped
                    break

        data = json.loads(content)
        return {
            "success": True,
            "subject": data.get("subject", ""),
            "body_html": data.get("body_html", ""),
            "body_text": data.get("body_text", ""),
        }
    except Exception as e:
        logger.error(f"AI content generation failed: {e}")
        return {
            "success": False,
            "subject": "",
            "body_html": "",
            "body_text": "",
            "error": str(e),
        }


@router.post("/ai/optimize-subject")
async def optimize_subject(
    body: AIOptimizeSubjectRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Optimize email subject line using AI."""
    prompt = f"""You are an email marketing expert. Optimize this subject line for a septic service company.

Current subject: "{body.subject}"
{f'Target segment: {body.segment}' if body.segment else ''}

Generate 5 alternative subject lines that:
- Are concise (under 60 characters)
- Create urgency or curiosity
- Are professional and relevant to septic/plumbing services
- Would improve open rates

Respond with ONLY a JSON array of strings:
["Alternative 1", "Alternative 2", "Alternative 3", "Alternative 4", "Alternative 5"]"""

    ai = AIGateway()
    try:
        result = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.8,
        )
        content = result.get("content", "[]")

        if "```" in content:
            parts = content.split("```")
            for part in parts:
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                if stripped.startswith("["):
                    content = stripped
                    break

        alternatives = json.loads(content)
        if not isinstance(alternatives, list):
            alternatives = []

        return {"success": True, "alternatives": alternatives[:5]}
    except Exception as e:
        logger.error(f"AI subject optimization failed: {e}")
        return {"success": False, "alternatives": [], "error": str(e)}


# ============================================================================
# Analytics Endpoints
# ============================================================================


@router.get("/analytics")
async def get_analytics(
    db: DbSession,
    current_user: CurrentUser,
    days: int = 30,
) -> dict:
    """Get email analytics from real campaign data."""
    cutoff = datetime.utcnow() - timedelta(days=days)

    # Totals
    totals_result = await db.execute(
        select(
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_sent), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_delivered), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_opened), 0),
            sa_func.coalesce(sa_func.sum(MarketingCampaign.total_clicked), 0),
        )
    )
    trow = totals_result.one()
    total_sent = trow[0]
    total_delivered = trow[1]
    total_opened = trow[2]
    total_clicked = trow[3]

    totals = {
        "total_sent": total_sent,
        "total_delivered": total_delivered,
        "total_opened": total_opened,
        "total_clicked": total_clicked,
        "open_rate": round(total_opened / total_sent * 100, 1) if total_sent > 0 else 0,
        "click_rate": round(total_clicked / total_sent * 100, 1) if total_sent > 0 else 0,
    }

    # Top campaigns
    top_result = await db.execute(
        select(MarketingCampaign)
        .where(MarketingCampaign.total_sent > 0)
        .order_by(MarketingCampaign.total_sent.desc())
        .limit(5)
    )
    top_campaigns = []
    for c in top_result.scalars().all():
        ts = c.total_sent or 1
        top_campaigns.append({
            "id": str(c.id),
            "name": c.name,
            "sent": c.total_sent or 0,
            "open_rate": round((c.total_opened or 0) / ts * 100, 1),
            "click_rate": round((c.total_clicked or 0) / ts * 100, 1),
        })

    # Daily stats from messages
    daily_result = await db.execute(
        text("""
            SELECT DATE(sent_at) as date,
                   COUNT(*) as sent,
                   COUNT(*) as delivered,
                   0 as opened,
                   0 as clicked
            FROM messages
            WHERE campaign_id IS NOT NULL
              AND sent_at >= :cutoff
              AND message_type = 'email'
            GROUP BY DATE(sent_at)
            ORDER BY DATE(sent_at)
        """).bindparams(cutoff=cutoff)
    )
    daily_stats = [
        {
            "date": str(row[0]),
            "sent": row[1],
            "delivered": row[2],
            "opened": row[3],
            "clicked": row[4],
        }
        for row in daily_result
    ]

    # Segment performance
    seg_result = await db.execute(
        select(
            MarketingCampaign.segment,
            sa_func.sum(MarketingCampaign.total_sent),
            sa_func.sum(MarketingCampaign.total_opened),
            sa_func.sum(MarketingCampaign.total_clicked),
        )
        .where(MarketingCampaign.segment.isnot(None))
        .group_by(MarketingCampaign.segment)
    )
    segment_performance = []
    for row in seg_result:
        ts = row[1] or 1
        segment_performance.append({
            "segment": row[0],
            "sent": row[1] or 0,
            "open_rate": round((row[2] or 0) / ts * 100, 1),
            "click_rate": round((row[3] or 0) / ts * 100, 1),
        })

    return {
        "totals": totals,
        "top_campaigns": top_campaigns,
        "daily_stats": daily_stats,
        "segment_performance": segment_performance,
    }


# ============================================================================
# Onboarding Endpoints
# ============================================================================


@router.get("/ai/onboarding-questions")
async def get_onboarding_questions(current_user: CurrentUser) -> List[dict]:
    """Get onboarding questions for email marketing setup."""
    return [
        {
            "id": "services",
            "question": "What services does your company offer?",
            "type": "multi_select",
            "required": True,
            "options": [
                "Septic Tank Pumping",
                "Septic Installation",
                "Septic Repair",
                "Grease Trap Cleaning",
                "Drain Cleaning",
                "Portable Toilets",
                "Inspection Services",
            ],
        },
        {
            "id": "customer_count",
            "question": "Approximately how many customers do you have?",
            "type": "select",
            "required": True,
            "options": [
                {"value": "under_100", "label": "Under 100"},
                {"value": "100_500", "label": "100-500"},
                {"value": "500_1000", "label": "500-1,000"},
                {"value": "1000_plus", "label": "1,000+"},
            ],
        },
        {
            "id": "pump_frequency",
            "question": "How often should customers get their tanks pumped?",
            "type": "select",
            "required": True,
            "options": [
                {"value": "1_year", "label": "Every year"},
                {"value": "2_years", "label": "Every 2 years"},
                {"value": "3_years", "label": "Every 3 years"},
                {"value": "5_years", "label": "Every 5 years"},
            ],
        },
        {
            "id": "avg_ticket",
            "question": "What is your average service ticket amount?",
            "type": "number",
            "required": False,
            "placeholder": "e.g., 350",
        },
        {
            "id": "service_area",
            "question": "What areas do you serve?",
            "type": "multi_text",
            "required": False,
            "placeholder": "e.g., East Central Texas",
        },
        {
            "id": "brand_voice",
            "question": "How would you describe your brand voice?",
            "type": "select",
            "required": False,
            "options": [
                {"value": "professional", "label": "Professional & Formal"},
                {"value": "friendly", "label": "Friendly & Casual"},
                {"value": "educational", "label": "Educational & Informative"},
                {"value": "humorous", "label": "Fun & Lighthearted"},
            ],
        },
    ]


@router.post("/onboarding/answers")
async def submit_onboarding(
    body: OnboardingAnswersRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Submit onboarding answers and save to settings."""
    answers = body.answers or {}
    await _save_setting(db, "email_marketing_onboarding", answers)

    # Update profile with relevant answers
    profile = await _get_setting(db, "email_marketing_profile")
    if answers.get("service_area"):
        areas = answers["service_area"]
        if isinstance(areas, str):
            areas = [areas]
        profile["service_areas"] = areas
    if answers.get("brand_voice"):
        profile["brand_voice"] = answers["brand_voice"]
    profile["onboarding_completed"] = True
    await _save_setting(db, "email_marketing_profile", profile)

    return {"success": True}


@router.post("/ai/generate-marketing-plan")
async def generate_marketing_plan(
    body: MarketingPlanRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Generate AI marketing plan based on onboarding answers and segment data."""
    # Load onboarding answers
    answers = body.answers
    if not answers:
        answers = await _get_setting(db, "email_marketing_onboarding")

    # Get segment data
    segment_counts = {}
    for seg_def in SEGMENT_DEFINITIONS:
        segment_counts[seg_def["id"]] = await _get_segment_count(db, seg_def["id"])

    prompt = f"""You are an email marketing strategist for a septic service company.

Business info:
{json.dumps(answers, indent=2) if answers else 'No onboarding data available'}

Customer segments:
{json.dumps(segment_counts, indent=2)}

Create a comprehensive 12-month email marketing plan. Include:
1. Monthly campaign calendar (what to send each month)
2. Recommended segments to target
3. Subject line suggestions
4. Content themes
5. Expected metrics (open rates, click rates)
6. Revenue projections

Format your response as a professional HTML document with headers, tables, and bullet points.
Use <h2>, <h3>, <p>, <table>, <ul>, <li> tags. Make it visually organized.
Start directly with the HTML content (no markdown, no code blocks)."""

    ai = AIGateway()
    try:
        result = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.7,
            use_heavy_model=True,
        )
        html_content = result.get("content", "")

        # Strip markdown code blocks if present
        if html_content.startswith("```"):
            lines = html_content.split("\n")
            html_content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        return {"success": True, "html_content": html_content}
    except Exception as e:
        logger.error(f"AI marketing plan generation failed: {e}")
        return {
            "success": False,
            "html_content": f"<p>Failed to generate marketing plan: {str(e)}</p>",
            "error": str(e),
        }
