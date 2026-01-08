"""
Segment Schemas for Enterprise Customer Success Platform
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal, Any, Union
from enum import Enum


class SegmentType(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    AI_GENERATED = "ai_generated"
    NESTED = "nested"


class SegmentCategory(str, Enum):
    LIFECYCLE = "lifecycle"
    VALUE = "value"
    SERVICE = "service"
    ENGAGEMENT = "engagement"
    GEOGRAPHIC = "geographic"


class RuleOperator(str, Enum):
    EQUALS = "eq"
    NOT_EQUALS = "neq"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    GREATER_THAN_OR_EQUALS = "gte"
    LESS_THAN_OR_EQUALS = "lte"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    BETWEEN = "between"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class SegmentRule(BaseModel):
    """Single segment rule definition."""
    field: str = Field(..., description="Field to evaluate (e.g., 'health_score', 'contract_value')")
    operator: RuleOperator
    value: Any = Field(None, description="Value to compare against")
    value2: Optional[Any] = Field(None, description="Second value for 'between' operator")


class SegmentRuleSet(BaseModel):
    """Rule set with AND/OR logic."""
    logic: Literal["and", "or"] = "and"
    rules: list[Union[SegmentRule, "SegmentRuleSet"]] = Field(default_factory=list)


# Enable self-referencing
SegmentRuleSet.model_rebuild()


class SegmentBase(BaseModel):
    """Base segment schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    segment_type: SegmentType = SegmentType.DYNAMIC

    # Rules for dynamic segments
    rules: Optional[SegmentRuleSet] = None

    # Priority for overlapping segments
    priority: int = Field(0, description="Higher priority segments evaluated first")

    # Settings
    is_active: bool = True
    auto_update: bool = True
    update_frequency_hours: int = Field(24, ge=1, le=168)

    # Actions on entry/exit
    on_entry_playbook_id: Optional[int] = None
    on_entry_journey_id: Optional[int] = None
    on_exit_playbook_id: Optional[int] = None
    on_exit_journey_id: Optional[int] = None

    # Metadata
    color: Optional[str] = Field(None, max_length=7, description="Hex color for UI")
    icon: Optional[str] = Field(None, max_length=50)
    tags: Optional[list[str]] = None

    # Smart segment metadata
    category: Optional[SegmentCategory] = None
    ai_insight: Optional[str] = Field(None, description="AI-generated insight message for this segment")
    recommended_actions: Optional[list[dict]] = Field(None, description="List of recommended actions for segment members")


class RecommendedAction(BaseModel):
    """Recommended action for segment members."""
    action: str = Field(..., description="Action identifier")
    label: str = Field(..., description="Human-readable action label")
    priority: str = Field("medium", description="Action priority: critical, high, medium, low")


class SegmentCreate(SegmentBase):
    """Schema for creating a segment."""
    pass


class SegmentUpdate(BaseModel):
    """Schema for updating a segment."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    segment_type: Optional[SegmentType] = None
    rules: Optional[SegmentRuleSet] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    auto_update: Optional[bool] = None
    update_frequency_hours: Optional[int] = Field(None, ge=1, le=168)
    on_entry_playbook_id: Optional[int] = None
    on_entry_journey_id: Optional[int] = None
    on_exit_playbook_id: Optional[int] = None
    on_exit_journey_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[list[str]] = None
    category: Optional[SegmentCategory] = None
    ai_insight: Optional[str] = None
    recommended_actions: Optional[list[dict]] = None


class SegmentResponse(SegmentBase):
    """Segment response schema."""
    id: int

    # System segment flag
    is_system: bool = False

    # Metrics (auto-calculated)
    customer_count: int = 0
    total_arr: Optional[float] = None
    avg_health_score: Optional[float] = None
    churn_risk_count: Optional[int] = None
    at_risk_count: Optional[int] = None

    # Timing
    last_evaluated_at: Optional[datetime] = None
    next_evaluation_at: Optional[datetime] = None
    last_refreshed_at: Optional[datetime] = None

    # Ownership
    created_by_user_id: Optional[int] = None
    owned_by_user_id: Optional[int] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SegmentListResponse(BaseModel):
    """Paginated segment list response."""
    items: list[SegmentResponse]
    total: int
    page: int
    page_size: int


# Customer Segment Membership

class CustomerSegmentBase(BaseModel):
    """Base customer segment membership schema."""
    customer_id: int
    segment_id: int
    entry_reason: Optional[str] = None


class CustomerSegmentResponse(CustomerSegmentBase):
    """Customer segment membership response."""
    id: int
    entered_at: Optional[datetime] = None
    exited_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    is_active: bool = True

    # Metrics at entry
    health_score_at_entry: Optional[int] = None
    arr_at_entry: Optional[float] = None

    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Segment Preview

class SegmentPreviewRequest(BaseModel):
    """Request to preview segment membership before saving."""
    rules: SegmentRuleSet
    limit: int = Field(100, ge=1, le=1000)


class SegmentPreviewResponse(BaseModel):
    """Segment preview response."""
    total_matches: int
    sample_customers: list[dict]  # [{"id": 1, "name": "...", "health_score": 75}]
    estimated_arr: Optional[float] = None
    avg_health_score: Optional[float] = None
    health_distribution: Optional[dict[str, int]] = None
    customer_type_distribution: Optional[dict[str, int]] = None
    geographic_distribution: Optional[dict[str, int]] = None
    execution_time_ms: Optional[float] = None


# Enhanced Segment Preview with Inclusions/Exclusions

class EnhancedSegmentPreviewRequest(BaseModel):
    """Enhanced preview request with segment inclusions/exclusions."""
    rules: SegmentRuleSet
    include_segments: Optional[list[int]] = Field(None, description="Segment IDs to include (union)")
    exclude_segments: Optional[list[int]] = Field(None, description="Segment IDs to exclude")
    sample_size: int = Field(50, ge=1, le=200)


# AI-Powered Segment Schemas

class NaturalLanguageQueryRequest(BaseModel):
    """Request to parse natural language into segment rules."""
    query: str = Field(..., min_length=3, max_length=500, description="Natural language query")
    use_llm: bool = Field(False, description="Use LLM for complex queries (if available)")


class NaturalLanguageQueryResponse(BaseModel):
    """Response from parsing natural language query."""
    success: bool
    rules: Optional[SegmentRuleSet] = None
    confidence: float = Field(0.0, ge=0, le=1)
    explanation: str = ""
    suggestions: list[str] = []
    parsed_entities: Optional[dict[str, Any]] = None


class SegmentSuggestion(BaseModel):
    """AI-generated segment suggestion."""
    name: str
    description: str
    rules: dict[str, Any]
    reasoning: str
    estimated_count: int = 0
    revenue_opportunity: Optional[float] = None
    priority: int = Field(0, ge=0, le=10, description="1-10, higher is more important")
    category: str = "general"
    tags: list[str] = []


class SegmentSuggestionsResponse(BaseModel):
    """Response containing AI-generated segment suggestions."""
    suggestions: list[SegmentSuggestion]
    total: int


class RevenueOpportunityResponse(BaseModel):
    """Revenue opportunity analysis for a segment."""
    segment_id: int
    segment_name: str
    total_customers: int
    total_potential_revenue: float
    avg_revenue_per_customer: float
    upsell_candidates: int
    at_risk_revenue: float
    expansion_probability: float
    recommended_actions: list[str]
    reasoning: str


# Segment Membership History

class SegmentMembershipResponse(BaseModel):
    """Detailed segment membership record."""
    id: int
    segment_id: int
    customer_id: int
    is_active: bool
    entered_at: Optional[datetime] = None
    exited_at: Optional[datetime] = None
    entry_reason: Optional[str] = None
    exit_reason: Optional[str] = None
    entry_source: Optional[str] = None
    exit_source: Optional[str] = None
    health_score_at_entry: Optional[int] = None
    customer_type_at_entry: Optional[str] = None
    ai_match_score: Optional[float] = None
    ai_match_reasons: Optional[list[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Segment Snapshot

class SegmentSnapshotResponse(BaseModel):
    """Point-in-time snapshot of segment membership."""
    id: int
    segment_id: int
    snapshot_at: datetime
    member_count: int
    previous_count: Optional[int] = None
    count_change: Optional[int] = None
    total_arr: Optional[float] = None
    avg_health_score: Optional[float] = None
    at_risk_count: Optional[int] = None
    healthy_count: Optional[int] = None
    members_entered: int = 0
    members_exited: int = 0
    snapshot_type: Optional[str] = None
    metadata_json: Optional[dict] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SegmentSnapshotListResponse(BaseModel):
    """Paginated list of segment snapshots."""
    items: list[SegmentSnapshotResponse]
    total: int
    page: int
    page_size: int


# Available Fields and Operators

class FieldDefinitionResponse(BaseModel):
    """Available field for segment rules."""
    name: str
    display_name: str
    category: str
    data_type: str
    description: str = ""


class OperatorDefinitionResponse(BaseModel):
    """Available operator for segment rules."""
    name: str
    display: str
    types: list[str]


class SegmentFieldsResponse(BaseModel):
    """Available fields for segment rules."""
    fields: list[FieldDefinitionResponse]
    operators: list[OperatorDefinitionResponse]


# Segment Evaluation

class SegmentEvaluationRequest(BaseModel):
    """Request to evaluate/refresh a segment."""
    track_history: bool = Field(True, description="Track entry/exit in membership history")
    create_snapshot: bool = Field(True, description="Create a snapshot of the results")


class SegmentEvaluationResponse(BaseModel):
    """Response from segment evaluation."""
    segment_id: int
    total_members: int
    customers_added: int
    customers_removed: int
    execution_time_ms: float
    snapshot_created: bool = False


# Segment Members with Details

class SegmentMemberDetail(BaseModel):
    """Customer details for segment member."""
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    customer_type: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: Optional[bool] = None
    created_at: Optional[datetime] = None
    health_score: Optional[int] = None
    health_status: Optional[str] = None
    churn_probability: Optional[float] = None
    score_trend: Optional[str] = None


class SegmentMembersResponse(BaseModel):
    """Paginated segment members with details."""
    items: list[SegmentMemberDetail]
    total: int
    page: int
    page_size: int
    segment_id: int
    segment_name: str


# Segment Templates

class SegmentTemplateResponse(BaseModel):
    """Pre-built segment template."""
    key: str
    name: str
    description: str
    rules: dict[str, Any]


class SegmentTemplatesResponse(BaseModel):
    """List of available segment templates."""
    templates: list[SegmentTemplateResponse]


# Smart Segment Schemas

class SmartSegmentCategory(BaseModel):
    """Smart segment category information."""
    code: str
    label: str
    description: str
    count: int = 0


class SmartSegmentSeedResponse(BaseModel):
    """Response from seeding smart segments."""
    created: int
    updated: int
    skipped: int
    total: int


class SmartSegmentListResponse(BaseModel):
    """List of smart segments with category information."""
    segments: list[SegmentResponse]
    categories: list[SmartSegmentCategory]
    total: int
