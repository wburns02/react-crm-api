"""
Email Marketing API - Stub endpoints for frontend compatibility.

Provides email marketing status, subscription, profiles, templates, segments,
campaigns, and AI features.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.api.deps import CurrentUser

router = APIRouter()


# Response Models


class Subscription(BaseModel):
    tier: str = "free"
    tier_name: str = "Free"
    emails_sent: int = 0
    emails_limit: int = 100
    features: List[str] = ["basic_templates", "manual_send"]
    renews_at: Optional[str] = None


class BusinessProfile(BaseModel):
    company_name: str = ""
    industry: str = ""
    target_audience: str = ""
    brand_voice: str = ""
    logo_url: Optional[str] = None


class Analytics(BaseModel):
    total_sent: int = 0
    total_opened: int = 0
    total_clicked: int = 0
    open_rate: float = 0
    click_rate: float = 0
    unsubscribe_rate: float = 0


class StatusResponse(BaseModel):
    success: bool = True
    subscription: Subscription = Subscription()
    profile: BusinessProfile = BusinessProfile()
    analytics: Analytics = Analytics()
    tiers: dict = {
        "free": {"name": "Free", "price": 0, "features": ["100 emails/month"]},
        "starter": {"name": "Starter", "price": 29, "features": ["1000 emails/month"]},
        "pro": {"name": "Pro", "price": 79, "features": ["10000 emails/month", "AI features"]},
    }


# Status & Subscription Endpoints


@router.get("/status")
async def get_email_marketing_status(current_user: CurrentUser) -> StatusResponse:
    """Get email marketing integration status."""
    return StatusResponse()


@router.get("/subscription")
async def get_subscription(current_user: CurrentUser) -> dict:
    """Get subscription details."""
    return {"success": True, "subscription": Subscription().model_dump()}


@router.post("/subscription")
async def update_subscription(current_user: CurrentUser, tier: str = "free") -> dict:
    """Update subscription tier."""
    return {"success": True, "message": "Subscription updated"}


# Profile Endpoints


@router.get("/profile")
async def get_profile(current_user: CurrentUser) -> dict:
    """Get business profile."""
    return {"success": True, "profile": BusinessProfile().model_dump()}


@router.put("/profile")
async def update_profile(current_user: CurrentUser) -> dict:
    """Update business profile."""
    return {"success": True, "message": "Profile updated"}


# Template Endpoints


@router.get("/templates")
async def get_templates(
    current_user: CurrentUser,
    category: Optional[str] = None,
    include_system: bool = False,
) -> List[dict]:
    """Get email templates."""
    return []


@router.get("/templates/{template_id}")
async def get_template(template_id: str, current_user: CurrentUser) -> dict:
    """Get a specific template."""
    return {"success": True, "template": None}


@router.post("/templates")
async def create_template(current_user: CurrentUser) -> dict:
    """Create email template."""
    return {"success": True, "template": None}


@router.put("/templates/{template_id}")
async def update_template(template_id: str, current_user: CurrentUser) -> dict:
    """Update email template."""
    return {"success": True, "message": "Template updated"}


@router.post("/templates/{template_id}/preview")
async def preview_template(template_id: str, current_user: CurrentUser) -> dict:
    """Preview email template."""
    return {"success": True, "preview": ""}


# Segment Endpoints


@router.get("/segments")
async def get_segments(current_user: CurrentUser) -> List[dict]:
    """Get customer segments."""
    return [
        {"id": "all", "name": "All Customers", "count": 0},
        {"id": "active", "name": "Active Customers", "count": 0},
        {"id": "inactive", "name": "Inactive Customers", "count": 0},
        {"id": "new", "name": "New Customers (30 days)", "count": 0},
    ]


@router.get("/segments/{segment}/customers")
async def get_segment_customers(
    segment: str,
    current_user: CurrentUser,
    limit: int = 100,
) -> dict:
    """Get customers in a segment."""
    return {"success": True, "customers": [], "total": 0}


# Campaign Endpoints


@router.get("/campaigns")
async def get_campaigns(
    current_user: CurrentUser,
    status: Optional[str] = None,
) -> List[dict]:
    """Get email campaigns."""
    return []


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, current_user: CurrentUser) -> dict:
    """Get a specific campaign."""
    return {"success": True, "campaign": None}


@router.post("/campaigns")
async def create_campaign(current_user: CurrentUser) -> dict:
    """Create email campaign."""
    return {"success": True, "campaign": None}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: str, current_user: CurrentUser) -> dict:
    """Send email campaign."""
    return {"success": True, "message": "Campaign sending not configured"}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, current_user: CurrentUser) -> dict:
    """Delete email campaign."""
    return {"success": True, "message": "Campaign deleted"}


# AI Endpoints


@router.get("/ai/suggestions")
async def get_ai_suggestions(current_user: CurrentUser) -> dict:
    """Get AI campaign suggestions."""
    return {"success": True, "suggestions": []}


@router.post("/ai/generate-suggestions")
async def generate_suggestions(current_user: CurrentUser) -> List[dict]:
    """Generate AI suggestions."""
    return []


@router.post("/ai/suggestions/{suggestion_id}/approve")
async def approve_suggestion(suggestion_id: str, current_user: CurrentUser) -> dict:
    """Approve AI suggestion."""
    return {"success": True, "campaign_id": None}


@router.post("/ai/suggestions/{suggestion_id}/dismiss")
async def dismiss_suggestion(suggestion_id: str, current_user: CurrentUser) -> dict:
    """Dismiss AI suggestion."""
    return {"success": True}


@router.post("/ai/generate-content")
async def generate_content(current_user: CurrentUser) -> dict:
    """Generate email content with AI."""
    return {"success": True, "subject": "", "body_html": "", "body_text": ""}


@router.post("/ai/optimize-subject")
async def optimize_subject(current_user: CurrentUser) -> dict:
    """Optimize email subject line."""
    return {"success": True, "alternatives": []}


@router.get("/ai/onboarding-questions")
async def get_onboarding_questions(current_user: CurrentUser) -> List[dict]:
    """Get onboarding questions."""
    return []


@router.post("/ai/generate-marketing-plan")
async def generate_marketing_plan(current_user: CurrentUser) -> dict:
    """Generate marketing plan."""
    return {"success": True, "html_content": ""}


# Analytics Endpoints


@router.get("/analytics")
async def get_analytics(
    current_user: CurrentUser,
    days: int = 30,
) -> Analytics:
    """Get email analytics."""
    return Analytics()


# Onboarding Endpoints


@router.post("/onboarding/answers")
async def submit_onboarding(current_user: CurrentUser) -> dict:
    """Submit onboarding answers."""
    return {"success": True}
