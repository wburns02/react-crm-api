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
# NOTE: Not yet DB-backed. Returns empty results until database models are added.
# =============================================================================


# =============================================================================
# Onboarding Endpoints
# =============================================================================


@router.get("/progress")
async def get_onboarding_progress(
    db: DbSession,
    current_user: CurrentUser,
) -> OnboardingProgress:
    """Get current user's onboarding progress."""
    # TODO: Query onboarding progress from database
    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=[],
        overall_progress=0.0,
        started_at=datetime.utcnow().isoformat(),
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
    # TODO: Update step status in database
    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=[],
        overall_progress=0.0,
        started_at=datetime.utcnow().isoformat(),
    )


@router.post("/steps/{step_id}/skip")
async def skip_step(
    db: DbSession,
    current_user: CurrentUser,
    step_id: str,
) -> OnboardingProgress:
    """Skip a setup step."""
    # TODO: Update step status in database
    return OnboardingProgress(
        user_id=str(current_user.id),
        steps=[],
        overall_progress=0.0,
        started_at=datetime.utcnow().isoformat(),
    )


@router.post("/complete")
async def complete_onboarding(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Mark onboarding as complete."""
    return {"success": True, "completed_at": datetime.utcnow().isoformat()}


@router.get("/recommendations")
async def get_onboarding_recommendations(
    db: DbSession,
    current_user: CurrentUser,
) -> list[dict]:
    """Get AI-powered onboarding recommendations based on user progress."""
    # TODO: Generate recommendations from database state
    return []


@router.get("/contextual-help")
async def get_contextual_help(
    db: DbSession,
    current_user: CurrentUser,
    page: str = Query(default="default"),
    action: Optional[str] = None,
) -> list[dict]:
    """Get context-aware help suggestions based on current page/action."""
    # TODO: Serve contextual help from database
    return []


@router.get("/tour/{feature_id}")
async def get_feature_tour(
    db: DbSession,
    current_user: CurrentUser,
    feature_id: str,
) -> dict:
    """Get guided tour steps for a specific feature."""
    # TODO: Serve feature tours from database
    return {"steps": [], "estimated_duration": 0}


# =============================================================================
# Import Endpoints
# =============================================================================


@router.get("/import/jobs")
async def get_import_jobs(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get import jobs."""
    # TODO: Query import jobs from database
    return {"jobs": []}


@router.get("/import/jobs/{job_id}")
async def get_import_job(
    db: DbSession,
    current_user: CurrentUser,
    job_id: str,
) -> dict:
    """Get single import job."""
    # TODO: Query import job from database
    raise HTTPException(status_code=404, detail="Import job not found")


@router.post("/import/preview")
async def upload_import_file(
    db: DbSession,
    current_user: CurrentUser,
    source: str = Form(...),
    entity_type: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Upload file for import preview."""
    # TODO: Parse uploaded file and return preview
    return {
        "preview_rows": [],
        "detected_fields": [],
        "suggested_mappings": [],
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
        created_at=datetime.utcnow().isoformat(),
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
    return {"auth_url": f"https://api.{source}.com/oauth", "connected": False}


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
    # TODO: Query tutorials from database
    return {"tutorials": []}


@router.get("/tutorials/recommended")
async def get_recommended_tutorials(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get recommended tutorials for user."""
    # TODO: Generate recommendations from database
    return {"tutorials": []}


@router.get("/tutorials/progress")
async def get_tutorial_progress(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get user's tutorial progress."""
    # TODO: Query tutorial progress from database
    return {"progress": []}


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
        started_at=datetime.utcnow().isoformat(),
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
        completed_at=datetime.utcnow().isoformat(),
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
    # TODO: Query help categories from database
    return {"categories": []}


@router.get("/help/articles")
async def get_help_articles(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
) -> dict:
    """Get help articles."""
    # TODO: Query help articles from database
    return {"articles": []}


@router.get("/help/articles/{article_id}")
async def get_help_article(
    db: DbSession,
    current_user: CurrentUser,
    article_id: str,
) -> dict:
    """Get single help article."""
    # TODO: Query help article from database
    raise HTTPException(status_code=404, detail="Help article not found")


@router.get("/help/search")
async def search_help(
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query(..., min_length=2),
) -> dict:
    """Search help articles."""
    # TODO: Search help articles in database
    return {"results": []}


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
    # TODO: Integrate with AI backend for real responses
    response = ChatMessage(
        id=uuid4().hex,
        role="assistant",
        content="AI help chat is not yet configured. Please contact support for assistance.",
        timestamp=datetime.utcnow().isoformat(),
        sources=[],
    )
    return {"conversation_id": conversation_id or uuid4().hex, "message": response.model_dump()}


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
        created_at=datetime.utcnow().isoformat(),
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
    # TODO: Query release notes from database
    return {"releases": []}


@router.get("/releases/latest")
async def get_latest_release(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get latest release."""
    # TODO: Query latest release from database
    return {"release": None}


@router.get("/releases/unread")
async def get_unread_release_count(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get unread release count."""
    # TODO: Query from database
    return {"count": 0, "latest_version": None}


@router.post("/releases/mark-read")
async def mark_releases_read(
    db: DbSession,
    current_user: CurrentUser,
    version: Optional[str] = None,
) -> dict:
    """Mark releases as read."""
    return {"success": True}
