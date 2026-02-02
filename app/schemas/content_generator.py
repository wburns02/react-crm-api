"""Content Generator Schemas - World-Class AI-Powered Content Generation.

Pydantic schemas for the Content Generator API endpoints.
Supports idea generation, multi-variant generation, SEO/readability analysis.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class ContentType(str, Enum):
    """Supported content types."""
    BLOG = "blog"
    FAQ = "faq"
    GBP_POST = "gbp_post"
    SERVICE_DESCRIPTION = "service_description"


class ContentStatus(str, Enum):
    """Content lifecycle status."""
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"


class AIModel(str, Enum):
    """Available AI models for content generation."""
    AUTO = "auto"
    OPENAI_GPT4O = "openai/gpt-4o"
    OPENAI_GPT4O_MINI = "openai/gpt-4o-mini"
    ANTHROPIC_CLAUDE_SONNET = "anthropic/claude-3.5-sonnet"
    LOCAL_QWEN_7B = "local/qwen2.5:7b"
    LOCAL_LLAMA_70B = "local/llama3.1:70b"


class ToneType(str, Enum):
    """Content tone options."""
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    CASUAL = "casual"
    AUTHORITATIVE = "authoritative"
    EDUCATIONAL = "educational"


class AudienceType(str, Enum):
    """Target audience types."""
    HOMEOWNERS = "homeowners"
    BUSINESSES = "businesses"
    PROPERTY_MANAGERS = "property_managers"
    CONTRACTORS = "contractors"
    GENERAL = "general"


# =============================================================================
# AI MODEL CONFIGURATION
# =============================================================================

class AIModelInfo(BaseModel):
    """Information about an AI model."""
    id: str
    display_name: str
    description: str
    provider: str  # openai, anthropic, local
    speed: Literal["fast", "medium", "slow"]
    quality: Literal["good", "great", "excellent"]
    cost: Literal["free", "low", "medium", "high"]
    available: bool = True
    recommended_for: List[str] = []


class AIModelHealthResponse(BaseModel):
    """Health status of AI models."""
    models: List[AIModelInfo]
    recommended_model: str
    local_available: bool
    cloud_available: bool


# =============================================================================
# IDEA GENERATION
# =============================================================================

class IdeaGenerateRequest(BaseModel):
    """Request to generate content ideas."""
    keywords: List[str] = Field(..., min_length=1, max_length=10, description="Keywords/topics to base ideas on")
    content_type: Optional[ContentType] = None  # If specified, ideas for this type only
    audience: AudienceType = AudienceType.HOMEOWNERS
    count: int = Field(default=5, ge=3, le=10, description="Number of ideas to generate")
    seasonality: Optional[str] = None  # e.g., "winter", "summer", "tax-season"
    model: AIModel = AIModel.AUTO


class ContentIdea(BaseModel):
    """A single content idea."""
    id: str
    topic: str
    description: str
    suggested_type: ContentType
    keywords: List[str]
    estimated_word_count: int
    difficulty: Literal["easy", "medium", "hard"]
    seasonality: Optional[str] = None
    hook: str  # Attention-grabbing opening line


class IdeaGenerateResponse(BaseModel):
    """Response with generated content ideas."""
    success: bool
    ideas: List[ContentIdea]
    model_used: str
    generation_time_ms: int
    demo_mode: bool = False


# =============================================================================
# CONTENT GENERATION
# =============================================================================

class ContentGenerateRequest(BaseModel):
    """Request to generate content."""
    content_type: ContentType
    topic: str = Field(..., min_length=5, max_length=500)
    tone: ToneType = ToneType.PROFESSIONAL
    audience: AudienceType = AudienceType.HOMEOWNERS
    target_keywords: List[str] = Field(default=[], max_length=10)
    word_count: int = Field(default=500, ge=100, le=3000)
    model: AIModel = AIModel.AUTO
    include_cta: bool = True  # Include call-to-action
    include_meta: bool = True  # Generate meta description


class GeneratedContent(BaseModel):
    """A single piece of generated content."""
    id: str
    title: str
    content: str
    content_type: ContentType
    meta_description: Optional[str] = None

    # Generation metadata
    model_used: str
    generation_time_ms: int
    word_count: int

    # Analysis scores (populated after generation)
    seo_score: Optional[int] = None
    readability_score: Optional[float] = None
    keyword_density: Optional[dict] = None


class ContentGenerateResponse(BaseModel):
    """Response with generated content."""
    success: bool
    content: GeneratedContent
    demo_mode: bool = False
    message: str = ""


# =============================================================================
# VARIANT GENERATION (A/B Testing)
# =============================================================================

class VariantGenerateRequest(BaseModel):
    """Request to generate multiple content variants."""
    content_type: ContentType
    topic: str = Field(..., min_length=5, max_length=500)
    tone: ToneType = ToneType.PROFESSIONAL
    audience: AudienceType = AudienceType.HOMEOWNERS
    target_keywords: List[str] = Field(default=[], max_length=10)
    word_count: int = Field(default=500, ge=100, le=3000)
    model: AIModel = AIModel.AUTO
    variant_count: int = Field(default=3, ge=2, le=5)
    variation_style: Literal["tone", "structure", "hook", "mixed"] = "mixed"


class ContentVariant(BaseModel):
    """A content variant for A/B comparison."""
    variant_label: str  # A, B, C, etc.
    title: str
    content: str
    hook_style: str  # Description of the opening approach
    seo_score: Optional[int] = None
    readability_score: Optional[float] = None


class VariantGenerateResponse(BaseModel):
    """Response with multiple content variants."""
    success: bool
    variant_group_id: str
    content_type: ContentType
    topic: str
    variants: List[ContentVariant]
    model_used: str
    total_generation_time_ms: int
    demo_mode: bool = False


# =============================================================================
# SEO ANALYSIS
# =============================================================================

class SEOAnalyzeRequest(BaseModel):
    """Request to analyze content for SEO."""
    content: str = Field(..., min_length=50)
    target_keywords: List[str] = Field(default=[], max_length=10)
    content_type: Optional[ContentType] = None


class KeywordAnalysis(BaseModel):
    """Analysis of a single keyword."""
    keyword: str
    count: int
    density: float  # Percentage
    in_title: bool
    in_first_paragraph: bool
    in_headings: bool
    optimal: bool  # Is density in optimal range (1-3%)?


class SEOAnalyzeResponse(BaseModel):
    """SEO analysis results."""
    success: bool
    overall_score: int = Field(..., ge=0, le=100)

    # Keyword analysis
    keyword_analysis: List[KeywordAnalysis]
    missing_keywords: List[str]  # Target keywords not found

    # Structure analysis
    has_headings: bool
    heading_count: int
    has_meta_description: bool
    meta_description_length: Optional[int] = None

    # Suggestions
    suggestions: List[str]

    # Generated meta description if missing
    suggested_meta_description: Optional[str] = None


# =============================================================================
# READABILITY ANALYSIS
# =============================================================================

class ReadabilityAnalyzeRequest(BaseModel):
    """Request to analyze content readability."""
    content: str = Field(..., min_length=50)


class ReadabilityAnalyzeResponse(BaseModel):
    """Readability analysis results."""
    success: bool

    # Flesch-Kincaid metrics
    flesch_reading_ease: float  # 0-100, higher = easier
    flesch_kincaid_grade: float  # US grade level

    # Additional metrics
    word_count: int
    sentence_count: int
    avg_words_per_sentence: float
    avg_syllables_per_word: float

    # Interpretation
    reading_level: Literal["very_easy", "easy", "fairly_easy", "standard", "fairly_difficult", "difficult", "very_difficult"]
    target_audience: str  # e.g., "General public", "College educated"

    # Suggestions
    suggestions: List[str]


# =============================================================================
# CONTENT LIBRARY
# =============================================================================

class SavedContent(BaseModel):
    """Content saved to the library."""
    id: str
    title: str
    content: str
    content_type: ContentType
    status: ContentStatus

    # Generation metadata
    model_used: str
    topic: str
    tone: ToneType
    audience: AudienceType
    target_keywords: List[str]

    # Scores
    seo_score: Optional[int] = None
    readability_score: Optional[float] = None

    # Variant tracking
    variant_group_id: Optional[str] = None
    variant_label: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    published_url: Optional[str] = None

    class Config:
        from_attributes = True


class ContentLibraryResponse(BaseModel):
    """Paginated content library response."""
    success: bool
    items: List[SavedContent]
    total: int
    page: int
    page_size: int


class ContentSaveRequest(BaseModel):
    """Request to save content to library."""
    title: str
    content: str
    content_type: ContentType
    topic: str
    tone: ToneType = ToneType.PROFESSIONAL
    audience: AudienceType = AudienceType.HOMEOWNERS
    target_keywords: List[str] = []
    model_used: str = "unknown"
    seo_score: Optional[int] = None
    readability_score: Optional[float] = None
    variant_group_id: Optional[str] = None
    variant_label: Optional[str] = None


class ContentUpdateRequest(BaseModel):
    """Request to update saved content."""
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[ContentStatus] = None
    published_url: Optional[str] = None


# =============================================================================
# USER PREFERENCES
# =============================================================================

class ModelPreferenceRequest(BaseModel):
    """Request to save user's AI model preference."""
    preferred_model: AIModel
    auto_fallback: bool = True  # Fallback to other models if preferred unavailable


class ModelPreferenceResponse(BaseModel):
    """User's saved model preference."""
    success: bool
    preferred_model: AIModel
    auto_fallback: bool
