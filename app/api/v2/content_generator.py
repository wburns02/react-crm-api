"""Content Generator API - World-Class AI Content Generation.

API endpoints for the Content Generator feature:
- Idea generation with AI brainstorming
- Multi-model content generation
- A/B variant generation
- SEO and readability analysis
- Content library management

Routes are prefixed with /content-generator
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime
import uuid

from app.api.deps import CurrentUser
from app.services.content_generator_service import content_generator_service
from app.schemas.content_generator import (
    # Enums
    AIModel, ContentType, ToneType, AudienceType, ContentStatus,
    # Requests
    IdeaGenerateRequest, ContentGenerateRequest, VariantGenerateRequest,
    SEOAnalyzeRequest, ReadabilityAnalyzeRequest,
    ContentSaveRequest, ContentUpdateRequest, ModelPreferenceRequest,
    # Responses
    AIModelInfo, AIModelHealthResponse,
    IdeaGenerateResponse, ContentIdea,
    ContentGenerateResponse, GeneratedContent,
    VariantGenerateResponse,
    SEOAnalyzeResponse, ReadabilityAnalyzeResponse,
    SavedContent, ContentLibraryResponse, ModelPreferenceResponse,
)

router = APIRouter()

# In-memory storage for demo (production would use database)
_saved_content: dict = {}
_user_preferences: dict = {}


# =============================================================================
# AI MODEL ENDPOINTS
# =============================================================================

@router.get("/models", response_model=List[AIModelInfo])
async def list_ai_models(current_user: CurrentUser) -> List[AIModelInfo]:
    """List all available AI models with current status."""
    return await content_generator_service.get_available_models()


@router.get("/models/health", response_model=AIModelHealthResponse)
async def check_model_health(current_user: CurrentUser) -> AIModelHealthResponse:
    """Check health and availability of all AI models."""
    models = await content_generator_service.get_available_models()
    availability = await content_generator_service.check_model_availability()

    # Find recommended model
    recommended = "auto"
    if availability.get("local"):
        recommended = "local/qwen2.5:7b"
    elif availability.get("anthropic"):
        recommended = "anthropic/claude-3.5-sonnet"
    elif availability.get("openai"):
        recommended = "openai/gpt-4o"

    return AIModelHealthResponse(
        models=models,
        recommended_model=recommended,
        local_available=availability.get("local", False),
        cloud_available=availability.get("openai", False) or availability.get("anthropic", False),
    )


@router.put("/models/preference", response_model=ModelPreferenceResponse)
async def save_model_preference(
    request: ModelPreferenceRequest,
    current_user: CurrentUser,
) -> ModelPreferenceResponse:
    """Save user's preferred AI model."""
    user_id = str(current_user.id)
    _user_preferences[user_id] = {
        "preferred_model": request.preferred_model,
        "auto_fallback": request.auto_fallback,
    }

    return ModelPreferenceResponse(
        success=True,
        preferred_model=request.preferred_model,
        auto_fallback=request.auto_fallback,
    )


@router.get("/models/preference", response_model=ModelPreferenceResponse)
async def get_model_preference(current_user: CurrentUser) -> ModelPreferenceResponse:
    """Get user's preferred AI model."""
    user_id = str(current_user.id)
    pref = _user_preferences.get(user_id, {
        "preferred_model": AIModel.AUTO,
        "auto_fallback": True,
    })

    return ModelPreferenceResponse(
        success=True,
        preferred_model=pref["preferred_model"],
        auto_fallback=pref["auto_fallback"],
    )


# =============================================================================
# IDEA GENERATION ENDPOINTS
# =============================================================================

@router.post("/ideas/generate", response_model=IdeaGenerateResponse)
async def generate_ideas(
    request: IdeaGenerateRequest,
    current_user: CurrentUser,
) -> IdeaGenerateResponse:
    """Generate content ideas based on keywords using AI."""
    import time
    start = time.time()

    ideas, model_used, demo_mode = await content_generator_service.generate_ideas(
        keywords=request.keywords,
        content_type=request.content_type,
        audience=request.audience,
        count=request.count,
        seasonality=request.seasonality,
        model=request.model,
    )

    generation_time = int((time.time() - start) * 1000)

    return IdeaGenerateResponse(
        success=True,
        ideas=ideas,
        model_used=model_used,
        generation_time_ms=generation_time,
        demo_mode=demo_mode,
    )


@router.get("/ideas", response_model=List[ContentIdea])
async def list_saved_ideas(
    current_user: CurrentUser,
    content_type: Optional[ContentType] = None,
    limit: int = Query(default=20, le=100),
) -> List[ContentIdea]:
    """List previously generated/saved ideas."""
    # For now, return empty list (ideas could be persisted to DB)
    # This endpoint is a placeholder for future enhancement
    return []


# =============================================================================
# CONTENT GENERATION ENDPOINTS
# =============================================================================

@router.post("/generate", response_model=ContentGenerateResponse)
async def generate_content(
    request: ContentGenerateRequest,
    current_user: CurrentUser,
) -> ContentGenerateResponse:
    """Generate content using AI."""
    content, demo_mode = await content_generator_service.generate_content(
        content_type=request.content_type,
        topic=request.topic,
        tone=request.tone,
        audience=request.audience,
        target_keywords=request.target_keywords,
        word_count=request.word_count,
        model=request.model,
        include_cta=request.include_cta,
        include_meta=request.include_meta,
    )

    # Run analysis on generated content
    seo_result = content_generator_service.analyze_seo(
        content.content,
        request.target_keywords,
    )
    readability_result = content_generator_service.analyze_readability(content.content)

    content.seo_score = seo_result["overall_score"]
    content.readability_score = readability_result["flesch_reading_ease"]
    content.keyword_density = {ka.keyword: ka.density for ka in seo_result["keyword_analysis"]}

    message = "Content generated successfully"
    if demo_mode:
        message = "Demo content generated (AI service unavailable)"

    return ContentGenerateResponse(
        success=True,
        content=content,
        demo_mode=demo_mode,
        message=message,
    )


@router.post("/generate/variants", response_model=VariantGenerateResponse)
async def generate_variants(
    request: VariantGenerateRequest,
    current_user: CurrentUser,
) -> VariantGenerateResponse:
    """Generate multiple content variants for A/B testing."""
    (
        variant_group_id,
        variants,
        model_used,
        total_time,
        demo_mode,
    ) = await content_generator_service.generate_variants(
        content_type=request.content_type,
        topic=request.topic,
        tone=request.tone,
        audience=request.audience,
        target_keywords=request.target_keywords,
        word_count=request.word_count,
        model=request.model,
        variant_count=request.variant_count,
        variation_style=request.variation_style,
    )

    # Run analysis on each variant
    for variant in variants:
        seo_result = content_generator_service.analyze_seo(
            variant.content,
            request.target_keywords,
        )
        readability_result = content_generator_service.analyze_readability(variant.content)

        variant.seo_score = seo_result["overall_score"]
        variant.readability_score = readability_result["flesch_reading_ease"]

    return VariantGenerateResponse(
        success=True,
        variant_group_id=variant_group_id,
        content_type=request.content_type,
        topic=request.topic,
        variants=variants,
        model_used=model_used,
        total_generation_time_ms=total_time,
        demo_mode=demo_mode,
    )


# =============================================================================
# ANALYSIS ENDPOINTS
# =============================================================================

@router.post("/analyze/seo", response_model=SEOAnalyzeResponse)
async def analyze_seo(
    request: SEOAnalyzeRequest,
    current_user: CurrentUser,
) -> SEOAnalyzeResponse:
    """Analyze content for SEO optimization."""
    result = content_generator_service.analyze_seo(
        content=request.content,
        target_keywords=request.target_keywords,
    )

    # Generate suggested meta description if analyzing blog content
    suggested_meta = None
    if request.content_type == ContentType.BLOG:
        # Take first ~150 chars of content as suggested meta
        clean_content = request.content.replace('#', '').replace('*', '').strip()
        if len(clean_content) > 160:
            suggested_meta = clean_content[:157] + "..."
        else:
            suggested_meta = clean_content

    return SEOAnalyzeResponse(
        success=True,
        overall_score=result["overall_score"],
        keyword_analysis=result["keyword_analysis"],
        missing_keywords=result["missing_keywords"],
        has_headings=result["has_headings"],
        heading_count=result["heading_count"],
        has_meta_description=False,  # Would need to detect META_DESCRIPTION line
        meta_description_length=None,
        suggestions=result["suggestions"],
        suggested_meta_description=suggested_meta,
    )


@router.post("/analyze/readability", response_model=ReadabilityAnalyzeResponse)
async def analyze_readability(
    request: ReadabilityAnalyzeRequest,
    current_user: CurrentUser,
) -> ReadabilityAnalyzeResponse:
    """Analyze content readability."""
    result = content_generator_service.analyze_readability(request.content)

    return ReadabilityAnalyzeResponse(
        success=True,
        flesch_reading_ease=result["flesch_reading_ease"],
        flesch_kincaid_grade=result["flesch_kincaid_grade"],
        word_count=result["word_count"],
        sentence_count=result["sentence_count"],
        avg_words_per_sentence=result["avg_words_per_sentence"],
        avg_syllables_per_word=result["avg_syllables_per_word"],
        reading_level=result["reading_level"],
        target_audience=result["target_audience"],
        suggestions=result["suggestions"],
    )


# =============================================================================
# CONTENT LIBRARY ENDPOINTS
# =============================================================================

@router.get("/library", response_model=ContentLibraryResponse)
async def list_library_content(
    current_user: CurrentUser,
    content_type: Optional[ContentType] = None,
    status: Optional[ContentStatus] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
) -> ContentLibraryResponse:
    """List saved content from the library."""
    # Filter content
    items = list(_saved_content.values())

    if content_type:
        items = [i for i in items if i.get("content_type") == content_type]
    if status:
        items = [i for i in items if i.get("status") == status]

    # Sort by created_at descending
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Paginate
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return ContentLibraryResponse(
        success=True,
        items=[SavedContent(**item) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/library", response_model=SavedContent)
async def save_content_to_library(
    request: ContentSaveRequest,
    current_user: CurrentUser,
) -> SavedContent:
    """Save generated content to the library."""
    content_id = str(uuid.uuid4())
    now = datetime.utcnow()

    saved = {
        "id": content_id,
        "title": request.title,
        "content": request.content,
        "content_type": request.content_type,
        "status": ContentStatus.DRAFT,
        "model_used": request.model_used,
        "topic": request.topic,
        "tone": request.tone,
        "audience": request.audience,
        "target_keywords": request.target_keywords,
        "seo_score": request.seo_score,
        "readability_score": request.readability_score,
        "variant_group_id": request.variant_group_id,
        "variant_label": request.variant_label,
        "created_at": now,
        "updated_at": now,
        "published_at": None,
        "published_url": None,
    }

    _saved_content[content_id] = saved

    return SavedContent(**saved)


@router.get("/library/{content_id}", response_model=SavedContent)
async def get_library_content(
    content_id: str,
    current_user: CurrentUser,
) -> SavedContent:
    """Get a specific piece of saved content."""
    if content_id not in _saved_content:
        raise HTTPException(status_code=404, detail="Content not found")

    return SavedContent(**_saved_content[content_id])


@router.patch("/library/{content_id}", response_model=SavedContent)
async def update_library_content(
    content_id: str,
    request: ContentUpdateRequest,
    current_user: CurrentUser,
) -> SavedContent:
    """Update saved content."""
    if content_id not in _saved_content:
        raise HTTPException(status_code=404, detail="Content not found")

    content = _saved_content[content_id]

    if request.title is not None:
        content["title"] = request.title
    if request.content is not None:
        content["content"] = request.content
    if request.status is not None:
        content["status"] = request.status
    if request.published_url is not None:
        content["published_url"] = request.published_url

    content["updated_at"] = datetime.utcnow()

    return SavedContent(**content)


@router.delete("/library/{content_id}")
async def delete_library_content(
    content_id: str,
    current_user: CurrentUser,
) -> dict:
    """Delete content from the library."""
    if content_id not in _saved_content:
        raise HTTPException(status_code=404, detail="Content not found")

    del _saved_content[content_id]

    return {"success": True, "message": "Content deleted"}


@router.post("/library/{content_id}/publish", response_model=SavedContent)
async def publish_content(
    content_id: str,
    published_url: Optional[str] = None,
    current_user: CurrentUser = None,
) -> SavedContent:
    """Mark content as published."""
    if content_id not in _saved_content:
        raise HTTPException(status_code=404, detail="Content not found")

    content = _saved_content[content_id]
    content["status"] = ContentStatus.PUBLISHED
    content["published_at"] = datetime.utcnow()
    content["updated_at"] = datetime.utcnow()

    if published_url:
        content["published_url"] = published_url

    return SavedContent(**content)


# =============================================================================
# QUICK ACTIONS (simplified endpoints for common tasks)
# =============================================================================

@router.post("/quick/blog")
async def quick_generate_blog(
    topic: str,
    keywords: Optional[str] = None,
    current_user: CurrentUser = None,
) -> ContentGenerateResponse:
    """Quick endpoint to generate a blog post."""
    request = ContentGenerateRequest(
        content_type=ContentType.BLOG,
        topic=topic,
        tone=ToneType.PROFESSIONAL,
        target_keywords=keywords.split(",") if keywords else [],
        word_count=800,
    )
    return await generate_content(request, current_user)


@router.post("/quick/gbp")
async def quick_generate_gbp_post(
    topic: str,
    current_user: CurrentUser = None,
) -> ContentGenerateResponse:
    """Quick endpoint to generate a Google Business Profile post."""
    request = ContentGenerateRequest(
        content_type=ContentType.GBP_POST,
        topic=topic,
        tone=ToneType.FRIENDLY,
        word_count=150,
    )
    return await generate_content(request, current_user)


@router.post("/quick/faq")
async def quick_generate_faq(
    question: str,
    current_user: CurrentUser = None,
) -> ContentGenerateResponse:
    """Quick endpoint to generate an FAQ answer."""
    request = ContentGenerateRequest(
        content_type=ContentType.FAQ,
        topic=question,
        tone=ToneType.EDUCATIONAL,
        word_count=250,
    )
    return await generate_content(request, current_user)
