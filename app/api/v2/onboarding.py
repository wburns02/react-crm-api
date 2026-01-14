"""
Onboarding & Help API Endpoints

Setup wizard, tutorials, help center:
- Onboarding progress tracking
- Data import
- Tutorials and training
- Help articles and AI chat
- Release notes
"""

from fastapi import APIRouter, Query, HTTPException, UploadFile, File, Form
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SetupStep(BaseModel):
    """Onboarding setup step."""
    id: str
    title: str
    description: str
    category: str  # import, configuration, integrations, team
    status: str  # pending, in_progress, completed, skipped
    is_required: bool = False
    estimated_minutes: int = 5
    order: int


class OnboardingProgress(BaseModel):
    """User's onboarding progress."""
    user_id: str
    steps: list[SetupStep]
    overall_progress: float  # 0-100
    started_at: str
    completed_at: Optional[str] = None


class ImportJob(BaseModel):
    """Data import job."""
    id: str
    source: str  # csv, quickbooks, servicetitan, housecall_pro
    entity_type: str  # customers, work_orders, equipment
    status: str  # pending, validating, processing, completed, failed
    total_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    errors: list[dict] = Field(default_factory=list)
    created_at: str
    completed_at: Optional[str] = None


class Tutorial(BaseModel):
    """Training tutorial."""
    id: str
    title: str
    description: str
    feature: str
    duration_minutes: int
    video_url: Optional[str] = None
    steps: list[dict] = Field(default_factory=list)
    is_interactive: bool = False


class UserTutorialProgress(BaseModel):
    """User's tutorial progress."""
    tutorial_id: str
    user_id: str
    status: str  # not_started, in_progress, completed
    current_step: int = 0
    time_spent_seconds: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class HelpCategory(BaseModel):
    """Help article category."""
    id: str
    name: str
    icon: str
    description: Optional[str] = None
    article_count: int = 0


class HelpArticle(BaseModel):
    """Help article."""
    id: str
    title: str
    excerpt: str
    content_html: Optional[str] = None
    category: str
    tags: list[str] = Field(default_factory=list)
    views: int = 0
    helpful_count: int = 0
    not_helpful_count: int = 0
    created_at: str
    updated_at: Optional[str] = None


class ChatMessage(BaseModel):
    """AI chat message."""
    id: str
    role: str  # user, assistant
    content: str
    timestamp: str
    sources: Optional[list[dict]] = None


class SupportTicket(BaseModel):
    """Support ticket."""
    id: str
    subject: str
    description: str
    category: str
    priority: str  # low, medium, high, urgent
    status: str  # open, in_progress, resolved, closed
    created_by: str
    assigned_to: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class ReleaseNote(BaseModel):
    """Release note."""
    id: str
    version: str
    title: str
    release_date: str
    highlights: list[str] = Field(default_factory=list)
    features: list[dict] = Field(default_factory=list)
    fixes: list[str] = Field(default_factory=list)
    breaking_changes: list[str] = Field(default_factory=list)


# =============================================================================
# Mock Data
# =============================================================================

ONBOARDING_STEPS = [
    SetupStep(
        id="import-customers",
        title="Import Customers",
        description="Import your existing customer database",
        category="import",
        status="pending",
        is_required=True,
        estimated_minutes=10,
        order=1
    ),
    SetupStep(
        id="configure-services",
        title="Configure Services",
        description="Set up your service types and pricing",
        category="configuration",
        status="pending",
        is_required=True,
        estimated_minutes=15,
        order=2
    ),
    SetupStep(
        id="add-technicians",
        title="Add Technicians",
        description="Add your team members",
        category="team",
        status="pending",
        is_required=True,
        estimated_minutes=5,
        order=3
    ),
    SetupStep(
        id="connect-payments",
        title="Connect Payments",
        description="Set up Stripe for payment processing",
        category="integrations",
        status="pending",
        is_required=False,
        estimated_minutes=10,
        order=4
    ),
    SetupStep(
        id="connect-calendar",
        title="Connect Calendar",
        description="Sync with Google Calendar",
        category="integrations",
        status="pending",
        is_required=False,
        estimated_minutes=5,
        order=5
    ),
]

HELP_CATEGORIES = [
    HelpCategory(id="getting-started", name="Getting Started", icon="🚀", article_count=12),
    HelpCategory(id="work-orders", name="Work Orders", icon="📋", article_count=18),
    HelpCategory(id="scheduling", name="Scheduling", icon="📅", article_count=10),
    HelpCategory(id="invoicing", name="Invoicing", icon="💰", article_count=8),
    HelpCategory(id="mobile-app", name="Mobile App", icon="📱", article_count=6),
    HelpCategory(id="integrations", name="Integrations", icon="🔗", article_count=15),
]


# =============================================================================
# Onboarding Endpoints
# =============================================================================

@router.get("/progress")
async def get_onboarding_progress(
    db: DbSession,
    current_user: CurrentUser,
) -> OnboardingProgress:
    """Get current user's onboarding progress."""
    completed = sum(1 for s in ONBOARDING_STEPS if s.status == "completed")
    total = len(ONBOARDING_STEPS)
    progress = (completed / total) * 100 if total > 0 else 0

    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=ONBOARDING_STEPS,
        overall_progress=round(progress, 1),
        started_at="2024-03-01T00:00:00Z"
    )


@router.patch("/steps/{step_id}")
async def update_step_status(
    db: DbSession,
    current_user: CurrentUser,
    step_id: str,
    status: str,
    data: Optional[dict] = None,
) -> OnboardingProgress:
    """Update a setup step's status."""
    for step in ONBOARDING_STEPS:
        if step.id == step_id:
            step.status = status
            break

    completed = sum(1 for s in ONBOARDING_STEPS if s.status == "completed")
    total = len(ONBOARDING_STEPS)

    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=ONBOARDING_STEPS,
        overall_progress=round((completed / total) * 100, 1),
        started_at="2024-03-01T00:00:00Z"
    )


@router.post("/steps/{step_id}/skip")
async def skip_step(
    db: DbSession,
    current_user: CurrentUser,
    step_id: str,
) -> OnboardingProgress:
    """Skip a setup step."""
    for step in ONBOARDING_STEPS:
        if step.id == step_id and not step.is_required:
            step.status = "skipped"
            break

    completed = sum(1 for s in ONBOARDING_STEPS if s.status in ["completed", "skipped"])
    total = len(ONBOARDING_STEPS)

    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=ONBOARDING_STEPS,
        overall_progress=round((completed / total) * 100, 1),
        started_at="2024-03-01T00:00:00Z"
    )


@router.post("/complete")
async def complete_onboarding(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Mark onboarding as complete."""
    return {
        "success": True,
        "completed_at": datetime.utcnow().isoformat()
    }


@router.get("/recommendations")
async def get_onboarding_recommendations(
    db: DbSession,
    current_user: CurrentUser,
) -> list[dict]:
    """Get AI-powered onboarding recommendations based on user progress."""
    return [
        {
            "id": "rec-1",
            "title": "Import Your Customer Data",
            "description": "You haven't imported any existing customer data yet. Importing customers will help you get started faster.",
            "reason": "Based on your account age and current customer count",
            "priority": "high",
            "estimated_impact": "Save 2-3 hours of manual data entry",
            "next_steps": [
                "Export customers from your previous system as CSV",
                "Go to Settings > Import Data",
                "Map your columns to CRM fields",
                "Review and confirm the import",
            ],
        },
        {
            "id": "rec-2",
            "title": "Set Up Automated Reminders",
            "description": "Automated appointment reminders can reduce no-shows by up to 40%.",
            "reason": "You have scheduled work orders but no reminder templates",
            "priority": "medium",
            "estimated_impact": "Reduce no-shows and improve customer satisfaction",
            "next_steps": [
                "Navigate to Settings > Notifications",
                "Enable appointment reminders",
                "Customize the reminder timing (e.g., 24 hours before)",
                "Review the default message template",
            ],
        },
        {
            "id": "rec-3",
            "title": "Complete Your Company Profile",
            "description": "A complete company profile improves customer communications and invoice professionalism.",
            "reason": "Missing: logo, business hours, service areas",
            "priority": "low",
            "estimated_impact": "Professional appearance on all customer-facing documents",
            "next_steps": [
                "Go to Settings > Company Profile",
                "Upload your company logo",
                "Set your business hours",
                "Define your service areas",
            ],
        },
    ]


@router.get("/contextual-help")
async def get_contextual_help(
    db: DbSession,
    current_user: CurrentUser,
    page: str = Query(default="default"),
    action: Optional[str] = None,
) -> list[dict]:
    """Get context-aware help suggestions based on current page/action."""
    help_by_page = {
        "workorders": [
            {
                "id": "help-1",
                "title": "Quick Tip: Work Order Status",
                "content": "Drag work orders between columns to update their status quickly. The system will automatically notify relevant parties.",
                "type": "tip",
                "relevance_score": 0.95,
                "related_feature": "work-order-management",
            },
            {
                "id": "help-2",
                "title": "New Feature: AI Scheduling",
                "content": "Try our AI-powered scheduling assistant to automatically find the best time slots based on technician availability and location.",
                "type": "feature",
                "relevance_score": 0.88,
                "related_feature": "ai-scheduling",
                "action": {"label": "Try It", "url": "/schedule?ai=true"},
            },
        ],
        "customers": [
            {
                "id": "help-3",
                "title": "Customer Health Scores",
                "content": "The health score indicates how likely a customer is to remain active. Scores below 60 may need attention.",
                "type": "tutorial",
                "relevance_score": 0.92,
                "related_feature": "customer-health",
            },
        ],
        "schedule": [
            {
                "id": "help-4",
                "title": "Drag & Drop Scheduling",
                "content": "Simply drag unassigned work orders from the sidebar onto a technician's timeline to schedule them.",
                "type": "tip",
                "relevance_score": 0.97,
                "related_feature": "scheduling",
            },
        ],
        "default": [
            {
                "id": "help-default",
                "title": "Need Help?",
                "content": "Click the help icon in the bottom right to access tutorials, documentation, and support.",
                "type": "tip",
                "relevance_score": 0.7,
                "related_feature": "help-center",
            },
        ],
    }
    return help_by_page.get(page, help_by_page["default"])


@router.get("/tour/{feature_id}")
async def get_feature_tour(
    db: DbSession,
    current_user: CurrentUser,
    feature_id: str,
) -> dict:
    """Get guided tour steps for a specific feature."""
    tours = {
        "work-orders": {
            "steps": [
                {
                    "id": "step-1",
                    "target": "[data-tour='create-button']",
                    "title": "Create Work Orders",
                    "content": "Click here to create a new work order. You can also use keyboard shortcut Ctrl+N.",
                    "position": "bottom",
                },
                {
                    "id": "step-2",
                    "target": "[data-tour='filters']",
                    "title": "Filter & Search",
                    "content": "Use filters to find specific work orders by status, date, technician, or customer.",
                    "position": "bottom",
                },
                {
                    "id": "step-3",
                    "target": "[data-tour='kanban']",
                    "title": "Kanban View",
                    "content": "Drag work orders between columns to update their status. Changes are saved automatically.",
                    "position": "left",
                },
            ],
            "estimated_duration": 3,
        },
        "schedule": {
            "steps": [
                {
                    "id": "step-1",
                    "target": "[data-tour='unscheduled']",
                    "title": "Unscheduled Work Orders",
                    "content": "Work orders waiting to be scheduled appear here. Drag them to the timeline to schedule.",
                    "position": "right",
                },
                {
                    "id": "step-2",
                    "target": "[data-tour='timeline']",
                    "title": "Technician Timeline",
                    "content": "Each row shows a technician's schedule. Hover to see details, drag to reschedule.",
                    "position": "bottom",
                },
            ],
            "estimated_duration": 2,
        },
    }
    return tours.get(feature_id, {"steps": [], "estimated_duration": 0})


# =============================================================================
# Import Endpoints
# =============================================================================

@router.get("/import/jobs")
async def get_import_jobs(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get import jobs."""
    jobs = [
        ImportJob(
            id="import-001",
            source="csv",
            entity_type="customers",
            status="completed",
            total_records=150,
            processed_records=148,
            failed_records=2,
            created_at="2024-02-15T00:00:00Z",
            completed_at="2024-02-15T00:05:00Z"
        ),
    ]
    return {"jobs": [j.model_dump() for j in jobs]}


@router.get("/import/jobs/{job_id}")
async def get_import_job(
    db: DbSession,
    current_user: CurrentUser,
    job_id: str,
) -> dict:
    """Get single import job."""
    job = ImportJob(
        id=job_id,
        source="csv",
        entity_type="customers",
        status="completed",
        total_records=150,
        processed_records=148,
        failed_records=2,
        created_at="2024-02-15T00:00:00Z",
        completed_at="2024-02-15T00:05:00Z"
    )
    return {"job": job.model_dump()}


@router.post("/import/preview")
async def upload_import_file(
    db: DbSession,
    current_user: CurrentUser,
    source: str = Form(...),
    entity_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Upload file for import preview."""
    return {
        "preview_rows": [
            {"name": "John Smith", "email": "john@example.com", "phone": "555-1234"},
            {"name": "Jane Doe", "email": "jane@example.com", "phone": "555-5678"},
        ],
        "detected_fields": ["name", "email", "phone"],
        "suggested_mappings": [
            {"source_field": "name", "target_field": "full_name", "confidence": 0.95},
            {"source_field": "email", "target_field": "email", "confidence": 1.0},
            {"source_field": "phone", "target_field": "phone", "confidence": 0.9},
        ]
    }


@router.post("/import/start")
async def start_import(
    db: DbSession,
    current_user: CurrentUser,
    source: str,
    entity_type: str,
    file_id: str,
    mappings: list[dict],
) -> dict:
    """Start import job."""
    job = ImportJob(
        id=f"import-{uuid4().hex[:8]}",
        source=source,
        entity_type=entity_type,
        status="processing",
        created_at=datetime.utcnow().isoformat()
    )
    return {"job": job.model_dump()}


@router.post("/import/connect")
async def connect_external_crm(
    db: DbSession,
    current_user: CurrentUser,
    source: str,
    credentials: dict,
) -> dict:
    """Connect to external CRM for import."""
    return {
        "auth_url": f"https://api.{source}.com/oauth",
        "connected": False
    }


# =============================================================================
# Tutorial Endpoints
# =============================================================================

@router.get("/tutorials")
async def get_tutorials(
    db: DbSession,
    current_user: CurrentUser,
    feature: Optional[str] = None,
) -> dict:
    """Get tutorials."""
    tutorials = [
        Tutorial(
            id="tut-work-orders",
            title="Creating Work Orders",
            description="Learn how to create and manage work orders",
            feature="work_orders",
            duration_minutes=8,
            video_url="https://example.com/tutorials/work-orders",
            is_interactive=True
        ),
        Tutorial(
            id="tut-scheduling",
            title="Scheduling & Dispatch",
            description="Master the scheduling calendar and dispatch board",
            feature="scheduling",
            duration_minutes=12,
            video_url="https://example.com/tutorials/scheduling",
            is_interactive=True
        ),
        Tutorial(
            id="tut-invoicing",
            title="Invoicing Customers",
            description="Create invoices and collect payments",
            feature="invoicing",
            duration_minutes=6,
            video_url="https://example.com/tutorials/invoicing"
        ),
    ]

    if feature:
        tutorials = [t for t in tutorials if t.feature == feature]

    return {"tutorials": [t.model_dump() for t in tutorials]}


@router.get("/tutorials/recommended")
async def get_recommended_tutorials(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get recommended tutorials for user."""
    tutorials = [
        Tutorial(
            id="tut-work-orders",
            title="Creating Work Orders",
            description="Learn how to create and manage work orders",
            feature="work_orders",
            duration_minutes=8
        ),
    ]
    return {"tutorials": [t.model_dump() for t in tutorials]}


@router.get("/tutorials/progress")
async def get_tutorial_progress(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get user's tutorial progress."""
    progress = [
        UserTutorialProgress(
            tutorial_id="tut-work-orders",
            user_id=str(current_user.id),
            status="completed",
            completed_at="2024-02-20T00:00:00Z"
        ),
    ]
    return {"progress": [p.model_dump() for p in progress]}


@router.patch("/tutorials/{tutorial_id}/progress")
async def update_tutorial_progress(
    db: DbSession,
    current_user: CurrentUser,
    tutorial_id: str,
    current_step: Optional[int] = None,
    status: Optional[str] = None,
    time_spent_seconds: Optional[int] = None,
) -> UserTutorialProgress:
    """Update tutorial progress."""
    return UserTutorialProgress(
        tutorial_id=tutorial_id,
        user_id=str(current_user.id),
        status=status or "in_progress",
        current_step=current_step or 0,
        time_spent_seconds=time_spent_seconds or 0,
        started_at=datetime.utcnow().isoformat()
    )


@router.post("/tutorials/{tutorial_id}/complete")
async def complete_tutorial(
    db: DbSession,
    current_user: CurrentUser,
    tutorial_id: str,
) -> UserTutorialProgress:
    """Mark tutorial as complete."""
    return UserTutorialProgress(
        tutorial_id=tutorial_id,
        user_id=str(current_user.id),
        status="completed",
        completed_at=datetime.utcnow().isoformat()
    )


# =============================================================================
# Help Endpoints
# =============================================================================

@router.get("/help/categories")
async def get_help_categories(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get help categories."""
    return {"categories": [c.model_dump() for c in HELP_CATEGORIES]}


@router.get("/help/articles")
async def get_help_articles(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
) -> dict:
    """Get help articles."""
    articles = [
        HelpArticle(
            id="art-001",
            title="Getting Started with Work Orders",
            excerpt="Learn the basics of creating and managing work orders",
            category="work-orders",
            tags=["work-orders", "basics"],
            views=1250,
            helpful_count=89,
            not_helpful_count=3,
            created_at="2024-01-15T00:00:00Z"
        ),
        HelpArticle(
            id="art-002",
            title="Setting Up Your First Schedule",
            excerpt="Configure the scheduling calendar and add your first jobs",
            category="scheduling",
            tags=["scheduling", "setup"],
            views=980,
            helpful_count=65,
            not_helpful_count=5,
            created_at="2024-01-20T00:00:00Z"
        ),
    ]

    if category:
        articles = [a for a in articles if a.category == category]

    return {"articles": [a.model_dump() for a in articles]}


@router.get("/help/articles/{article_id}")
async def get_help_article(
    db: DbSession,
    current_user: CurrentUser,
    article_id: str,
) -> dict:
    """Get single help article."""
    article = HelpArticle(
        id=article_id,
        title="Getting Started with Work Orders",
        excerpt="Learn the basics of creating and managing work orders",
        content_html="<h2>Creating Work Orders</h2><p>Work orders are the core of your service business...</p>",
        category="work-orders",
        tags=["work-orders", "basics"],
        views=1251,
        helpful_count=89,
        not_helpful_count=3,
        created_at="2024-01-15T00:00:00Z"
    )
    return {"article": article.model_dump()}


@router.get("/help/search")
async def search_help(
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query(..., min_length=2),
) -> dict:
    """Search help articles."""
    results = [
        HelpArticle(
            id="art-001",
            title="Getting Started with Work Orders",
            excerpt="Learn the basics of creating and managing work orders",
            category="work-orders",
            tags=["work-orders", "basics"],
            views=1250,
            helpful_count=89,
            not_helpful_count=3,
            created_at="2024-01-15T00:00:00Z"
        ),
    ]
    return {"results": [r.model_dump() for r in results]}


@router.post("/help/articles/{article_id}/rate")
async def rate_article(
    db: DbSession,
    current_user: CurrentUser,
    article_id: str,
    helpful: bool,
) -> dict:
    """Rate article helpfulness."""
    return {"success": True}


@router.post("/help/chat")
async def ai_help_chat(
    db: DbSession,
    current_user: CurrentUser,
    message: str,
    conversation_id: Optional[str] = None,
) -> dict:
    """AI help chat."""
    response = ChatMessage(
        id=uuid4().hex,
        role="assistant",
        content="I'd be happy to help! Based on your question, here's what I found...",
        timestamp=datetime.utcnow().isoformat(),
        sources=[
            {"type": "article", "title": "Related Article", "url": "/help/articles/art-001"}
        ]
    )
    return {
        "conversation_id": conversation_id or uuid4().hex,
        "message": response.model_dump()
    }


@router.post("/help/tickets")
async def create_support_ticket(
    db: DbSession,
    current_user: CurrentUser,
    subject: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    priority: str = Form("medium"),
) -> dict:
    """Create support ticket."""
    ticket = SupportTicket(
        id=f"ticket-{uuid4().hex[:8]}",
        subject=subject,
        description=description,
        category=category,
        priority=priority,
        status="open",
        created_by=str(current_user.id),
        created_at=datetime.utcnow().isoformat()
    )
    return {"ticket": ticket.model_dump()}


# =============================================================================
# Release Notes Endpoints
# =============================================================================

@router.get("/releases")
async def get_release_notes(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get release notes."""
    releases = [
        ReleaseNote(
            id="rel-2.5.0",
            version="2.5.0",
            title="AI-Powered Dispatch & IoT Integration",
            release_date="2024-03-01",
            highlights=[
                "AI dispatch suggestions for optimal technician assignment",
                "IoT device integration for predictive maintenance",
                "New financial dashboard with cash flow forecasting"
            ],
            features=[
                {"title": "AI Dispatch", "description": "Smart technician assignment recommendations"},
                {"title": "IoT Integration", "description": "Connect thermostats and sensors"}
            ],
            fixes=["Fixed scheduling conflict detection", "Improved invoice PDF generation"]
        ),
        ReleaseNote(
            id="rel-2.4.0",
            version="2.4.0",
            title="Enterprise Features & Multi-Region",
            release_date="2024-02-15",
            highlights=["Multi-region support", "Franchise management", "Advanced permissions"],
            features=[],
            fixes=[]
        ),
    ]
    return {"releases": [r.model_dump() for r in releases]}


@router.get("/releases/latest")
async def get_latest_release(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get latest release."""
    release = ReleaseNote(
        id="rel-2.5.0",
        version="2.5.0",
        title="AI-Powered Dispatch & IoT Integration",
        release_date="2024-03-01",
        highlights=[
            "AI dispatch suggestions for optimal technician assignment",
            "IoT device integration for predictive maintenance"
        ],
        features=[],
        fixes=[]
    )
    return {"release": release.model_dump()}


@router.get("/releases/unread")
async def get_unread_release_count(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get unread release count."""
    return {
        "count": 1,
        "latest_version": "2.5.0"
    }


@router.post("/releases/mark-read")
async def mark_releases_read(
    db: DbSession,
    current_user: CurrentUser,
    version: Optional[str] = None,
) -> dict:
    """Mark releases as read."""
    return {"success": True}
