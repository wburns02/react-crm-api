"""
Marketplace API Endpoints

Third-party integration directory:
- Browse available apps
- Install/uninstall apps
- Manage installed app settings
- App reviews
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================


class AppScreenshot(BaseModel):
    """App screenshot."""

    url: str
    caption: Optional[str] = None


class AppPricing(BaseModel):
    """App pricing info."""

    type: str  # free, paid, freemium, trial
    price: Optional[float] = None
    billing_period: Optional[str] = None  # monthly, yearly
    trial_days: Optional[int] = None


class MarketplaceApp(BaseModel):
    """Marketplace app listing."""

    id: str
    name: str
    slug: str
    shortDescription: str
    description: str
    category: str
    iconUrl: str
    rating: float
    reviewCount: int
    installCount: int
    developer: str
    version: str
    pricing: AppPricing
    screenshots: list[AppScreenshot] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    isFeatured: bool = False
    isVerified: bool = True
    createdAt: str
    updatedAt: str


class InstalledApp(BaseModel):
    """Installed app instance."""

    appId: str
    app: MarketplaceApp
    installStatus: str  # installed, needs_update, error, installing
    version: str
    installedAt: str
    lastSync: Optional[str] = None
    settings: dict = Field(default_factory=dict)
    errorMessage: Optional[str] = None


class AppReview(BaseModel):
    """App review."""

    id: str
    appId: str
    userId: str
    userName: str
    rating: int
    title: str
    body: str
    helpful_count: int = 0
    createdAt: str
    updatedAt: Optional[str] = None


class CategoryStat(BaseModel):
    """Category statistics."""

    category: str
    count: int


# =============================================================================
# Mock Data
# =============================================================================

MOCK_APPS = [
    MarketplaceApp(
        id="app-quickbooks",
        name="QuickBooks Integration",
        slug="quickbooks",
        shortDescription="Sync invoices and payments with QuickBooks",
        description="Automatically sync your invoices, payments, and customer data with QuickBooks Online. Real-time two-way sync keeps your books up to date.",
        category="accounting",
        iconUrl="https://example.com/icons/quickbooks.png",
        rating=4.7,
        reviewCount=234,
        installCount=1500,
        developer="Intuit",
        version="2.3.1",
        pricing=AppPricing(type="freemium", price=29.99, billing_period="monthly"),
        features=["Two-way sync", "Invoice automation", "Payment reconciliation"],
        permissions=["invoices:read", "invoices:write", "payments:read"],
        isFeatured=True,
        isVerified=True,
        createdAt="2023-01-15T00:00:00Z",
        updatedAt="2024-02-20T00:00:00Z",
    ),
    MarketplaceApp(
        id="app-stripe",
        name="Stripe Payments",
        slug="stripe",
        shortDescription="Accept credit card payments in the field",
        description="Enable card payments anywhere with Stripe integration. Accept credit cards, Apple Pay, and Google Pay directly from work orders.",
        category="payments",
        iconUrl="https://example.com/icons/stripe.png",
        rating=4.9,
        reviewCount=567,
        installCount=2800,
        developer="Stripe",
        version="3.1.0",
        pricing=AppPricing(type="free"),
        features=["Card payments", "Apple Pay", "Payment links", "Automatic deposits"],
        permissions=["payments:read", "payments:write", "customers:read"],
        isFeatured=True,
        isVerified=True,
        createdAt="2022-06-01T00:00:00Z",
        updatedAt="2024-03-01T00:00:00Z",
    ),
    MarketplaceApp(
        id="app-google-calendar",
        name="Google Calendar Sync",
        slug="google-calendar",
        shortDescription="Sync schedules with Google Calendar",
        description="Keep your team's schedules in sync with Google Calendar. Work orders appear as calendar events with full details.",
        category="scheduling",
        iconUrl="https://example.com/icons/google-calendar.png",
        rating=4.5,
        reviewCount=189,
        installCount=980,
        developer="Google",
        version="1.8.0",
        pricing=AppPricing(type="free"),
        features=["Two-way sync", "Team calendars", "Event notifications"],
        permissions=["schedule:read", "schedule:write"],
        isFeatured=False,
        isVerified=True,
        createdAt="2023-03-10T00:00:00Z",
        updatedAt="2024-01-15T00:00:00Z",
    ),
    MarketplaceApp(
        id="app-twilio",
        name="Twilio SMS & Voice",
        slug="twilio",
        shortDescription="Customer communications via SMS and voice",
        description="Send automated SMS notifications and enable voice calling directly from the CRM. Appointment reminders, status updates, and more.",
        category="communication",
        iconUrl="https://example.com/icons/twilio.png",
        rating=4.6,
        reviewCount=312,
        installCount=1200,
        developer="Twilio",
        version="2.5.0",
        pricing=AppPricing(type="paid", price=0.01, billing_period="per message"),
        features=["SMS notifications", "Voice calls", "Automated reminders"],
        permissions=["customers:read", "notifications:write"],
        isFeatured=True,
        isVerified=True,
        createdAt="2023-02-01T00:00:00Z",
        updatedAt="2024-02-28T00:00:00Z",
    ),
    MarketplaceApp(
        id="app-mailchimp",
        name="Mailchimp Marketing",
        slug="mailchimp",
        shortDescription="Email marketing campaigns",
        description="Create and send email marketing campaigns to your customers. Sync contacts and track engagement.",
        category="marketing",
        iconUrl="https://example.com/icons/mailchimp.png",
        rating=4.4,
        reviewCount=145,
        installCount=650,
        developer="Mailchimp",
        version="1.2.0",
        pricing=AppPricing(type="freemium", price=14.99, billing_period="monthly"),
        features=["Email campaigns", "Contact sync", "Analytics"],
        permissions=["customers:read", "marketing:write"],
        isFeatured=False,
        isVerified=True,
        createdAt="2023-08-15T00:00:00Z",
        updatedAt="2024-01-20T00:00:00Z",
    ),
]

MOCK_INSTALLED = []


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/apps")
async def get_marketplace_apps(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
    status: Optional[str] = None,
    pricing: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "popular",
    page: int = 1,
    page_size: int = 12,
) -> dict:
    """Get marketplace apps with filters."""
    apps = MOCK_APPS.copy()

    # Apply filters
    if category:
        apps = [a for a in apps if a.category == category]
    if pricing:
        apps = [a for a in apps if a.pricing.type == pricing]
    if search:
        search_lower = search.lower()
        apps = [a for a in apps if search_lower in a.name.lower() or search_lower in a.description.lower()]

    # Sort
    if sort == "popular":
        apps.sort(key=lambda x: x.installCount, reverse=True)
    elif sort == "rating":
        apps.sort(key=lambda x: x.rating, reverse=True)
    elif sort == "recent":
        apps.sort(key=lambda x: x.updatedAt, reverse=True)
    elif sort == "name":
        apps.sort(key=lambda x: x.name)

    # Paginate
    total = len(apps)
    start = (page - 1) * page_size
    end = start + page_size
    apps = apps[start:end]

    return {"apps": [a.model_dump() for a in apps], "total": total, "page": page, "pageSize": page_size}


@router.get("/apps/{app_id}")
async def get_marketplace_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> MarketplaceApp:
    """Get single marketplace app."""
    for app in MOCK_APPS:
        if app.id == app_id:
            return app
    raise HTTPException(status_code=404, detail="App not found")


@router.get("/apps/{app_id}/reviews")
async def get_app_reviews(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> list[AppReview]:
    """Get reviews for an app."""
    reviews = [
        AppReview(
            id="review-1",
            appId=app_id,
            userId="user-1",
            userName="John D.",
            rating=5,
            title="Great integration!",
            body="Works perfectly with our workflow. Easy setup.",
            helpful_count=12,
            createdAt="2024-02-15T00:00:00Z",
        ),
        AppReview(
            id="review-2",
            appId=app_id,
            userId="user-2",
            userName="Sarah M.",
            rating=4,
            title="Good but could be better",
            body="Does what it says, would like more customization options.",
            helpful_count=5,
            createdAt="2024-01-20T00:00:00Z",
        ),
    ]
    return reviews


@router.post("/apps/{app_id}/reviews")
async def submit_app_review(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
    rating: int = Query(..., ge=1, le=5),
    title: str = Query(...),
    body: str = Query(...),
) -> AppReview:
    """Submit a review for an app."""
    review = AppReview(
        id=f"review-{uuid4().hex[:8]}",
        appId=app_id,
        userId=str(current_user.id),
        userName=current_user.email.split("@")[0],
        rating=rating,
        title=title,
        body=body,
        createdAt=datetime.utcnow().isoformat(),
    )
    return review


@router.get("/featured")
async def get_featured_apps(
    db: DbSession,
    current_user: CurrentUser,
) -> list[MarketplaceApp]:
    """Get featured apps."""
    return [a for a in MOCK_APPS if a.isFeatured]


@router.get("/categories")
async def get_category_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> list[CategoryStat]:
    """Get category statistics."""
    categories = {}
    for app in MOCK_APPS:
        if app.category not in categories:
            categories[app.category] = 0
        categories[app.category] += 1

    return [CategoryStat(category=cat, count=count) for cat, count in categories.items()]


@router.get("/installed")
async def get_installed_apps(
    db: DbSession,
    current_user: CurrentUser,
) -> list[InstalledApp]:
    """Get installed apps for current account."""
    # Return mock installed apps
    if not MOCK_INSTALLED:
        # Default installed app
        for app in MOCK_APPS:
            if app.id == "app-stripe":
                MOCK_INSTALLED.append(
                    InstalledApp(
                        appId=app.id,
                        app=app,
                        installStatus="installed",
                        version=app.version,
                        installedAt="2024-01-01T00:00:00Z",
                        lastSync="2024-03-01T00:00:00Z",
                    )
                )
    return MOCK_INSTALLED


@router.post("/install")
async def install_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str = Query(...),
) -> dict:
    """Install an app."""
    for app in MOCK_APPS:
        if app.id == app_id:
            installed = InstalledApp(
                appId=app.id,
                app=app,
                installStatus="installed",
                version=app.version,
                installedAt=datetime.utcnow().isoformat(),
            )
            MOCK_INSTALLED.append(installed)
            return {
                "success": True,
                "message": f"Successfully installed {app.name}",
                "installed_app": installed.model_dump(),
            }
    raise HTTPException(status_code=404, detail="App not found")


@router.delete("/installed/{app_id}")
async def uninstall_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> dict:
    """Uninstall an app."""
    global MOCK_INSTALLED
    MOCK_INSTALLED = [i for i in MOCK_INSTALLED if i.appId != app_id]
    return {"success": True}


@router.patch("/installed/{app_id}/settings")
async def update_app_settings(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
    settings: dict,
) -> InstalledApp:
    """Update installed app settings."""
    for installed in MOCK_INSTALLED:
        if installed.appId == app_id:
            installed.settings.update(settings)
            return installed
    raise HTTPException(status_code=404, detail="Installed app not found")


@router.post("/installed/{app_id}/sync")
async def sync_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> InstalledApp:
    """Trigger sync for an installed app."""
    for installed in MOCK_INSTALLED:
        if installed.appId == app_id:
            installed.lastSync = datetime.utcnow().isoformat()
            return installed
    raise HTTPException(status_code=404, detail="Installed app not found")
