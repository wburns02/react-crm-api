"""
Marketing Hub API - Stub endpoints for frontend compatibility.

Provides marketing overview, ads, SEO, leads, and reviews endpoints.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.api.deps import CurrentUser

router = APIRouter()


# Response Models


class MarketingOverview(BaseModel):
    success: bool = True
    period_days: int = 30
    overview: dict = {
        "website_traffic": {"sessions": 0, "users": 0, "conversions": 0},
        "paid_ads": {"spend": 0, "clicks": 0, "conversions": 0, "roas": 0},
        "seo": {"score": 0, "grade": "N/A", "trend": "neutral"},
        "leads": {"new": 0, "engaged": 0, "converted": 0, "conversion_rate": 0},
    }
    quick_actions: list = []


class AdsPerformance(BaseModel):
    success: bool = True
    metrics: dict = {
        "cost": 0,
        "clicks": 0,
        "impressions": 0,
        "conversions": 0,
        "ctr": 0,
        "cpa": 0,
    }
    campaigns: list = []
    recommendations: list = []


class AdsStatus(BaseModel):
    success: bool = True
    connected: bool = False
    customer_id: Optional[str] = None
    account_name: Optional[str] = None


class SEOOverview(BaseModel):
    success: bool = True
    overall_score: dict = {"overall": 0, "grade": "N/A", "trend": "neutral"}
    keyword_rankings: list = []
    recommendations: list = []


class LeadPipeline(BaseModel):
    success: bool = True
    pipeline: dict = {"new": 0, "engaged": 0, "qualified": 0, "converted": 0}
    hot_leads: list = []
    conversion_rate: float = 0


class PendingReviews(BaseModel):
    success: bool = True
    reviews: list = []


class IntegrationSettings(BaseModel):
    success: bool = True
    integrations: dict = {
        "ga4": {"configured": False},
        "google_ads": {"configured": False},
        "anthropic": {"configured": False},
        "openai": {"configured": False},
        "search_console": {"configured": False},
    }
    automation: dict = {
        "ai_advisor_enabled": False,
        "auto_campaigns_enabled": False,
        "lead_scoring_enabled": False,
    }


# Overview Endpoints


@router.get("/overview")
async def get_overview(
    current_user: CurrentUser,
    days: int = 30,
) -> MarketingOverview:
    """Get marketing hub overview."""
    return MarketingOverview(period_days=days)


# Ads Endpoints


@router.get("/ads/performance")
async def get_ads_performance(
    current_user: CurrentUser,
    days: int = 30,
) -> AdsPerformance:
    """Get Google Ads performance metrics."""
    return AdsPerformance()


@router.get("/ads/status")
async def get_ads_status(current_user: CurrentUser) -> AdsStatus:
    """Get Google Ads connection status."""
    return AdsStatus()


# SEO Endpoints


@router.get("/seo/overview")
async def get_seo_overview(current_user: CurrentUser) -> SEOOverview:
    """Get SEO overview and rankings."""
    return SEOOverview()


@router.get("/seo/blog-ideas")
async def get_blog_ideas(current_user: CurrentUser) -> dict:
    """Get AI-generated blog ideas."""
    return {"success": True, "ideas": []}


@router.post("/seo/generate-blog")
async def generate_blog(
    current_user: CurrentUser,
    topic: str = "",
    keyword: Optional[str] = None,
    word_count: int = 800,
) -> dict:
    """Generate blog content."""
    return {"success": True, "content": "", "message": "Blog generation not configured"}


# Leads Endpoints


@router.get("/leads/pipeline")
async def get_lead_pipeline(current_user: CurrentUser) -> LeadPipeline:
    """Get lead pipeline metrics."""
    return LeadPipeline()


@router.get("/leads/hot")
async def get_hot_leads(current_user: CurrentUser) -> dict:
    """Get hot leads list."""
    return {"success": True, "leads": []}


# Reviews Endpoints


@router.get("/reviews/pending")
async def get_pending_reviews(current_user: CurrentUser) -> PendingReviews:
    """Get pending reviews."""
    return PendingReviews()


@router.post("/reviews/reply")
async def reply_to_review(
    current_user: CurrentUser,
    review_id: str = "",
    reply: str = "",
) -> dict:
    """Reply to a review."""
    return {"success": True, "message": "Review reply not configured"}


# Campaigns Endpoints


@router.get("/campaigns")
async def get_campaigns(current_user: CurrentUser) -> dict:
    """Get marketing campaigns."""
    return {"success": True, "campaigns": []}


@router.post("/campaigns")
async def create_campaign(
    current_user: CurrentUser,
) -> dict:
    """Create a marketing campaign."""
    return {"success": True, "campaign_id": None, "message": "Campaigns not configured"}


# AI Endpoints


@router.get("/ai/recommendations")
async def get_ai_recommendations(current_user: CurrentUser) -> dict:
    """Get AI marketing recommendations."""
    return {"success": True, "recommendations": []}


@router.post("/ai/generate-content")
async def generate_content(
    current_user: CurrentUser,
) -> dict:
    """Generate AI marketing content."""
    return {"success": True, "content": None, "message": "AI generation not configured"}


@router.post("/ai/generate-landing-page")
async def generate_landing_page(
    current_user: CurrentUser,
    city: str = "",
    service: Optional[str] = None,
    keywords: Optional[str] = None,
) -> dict:
    """Generate landing page content."""
    return {"success": True, "content": None, "message": "Landing page generation not configured"}


# Settings Endpoints


@router.get("/settings")
async def get_settings(current_user: CurrentUser) -> IntegrationSettings:
    """Get marketing hub settings."""
    return IntegrationSettings()


@router.post("/settings")
async def save_settings(
    current_user: CurrentUser,
) -> dict:
    """Save marketing hub settings."""
    return {"success": True, "message": "Settings saved"}
