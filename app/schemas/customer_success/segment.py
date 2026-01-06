"""
Segment Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal, Any
from enum import Enum


class SegmentType(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"
    AI_GENERATED = "ai_generated"


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
    rules: list[SegmentRule | "SegmentRuleSet"] = Field(default_factory=list)


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


class SegmentResponse(SegmentBase):
    """Segment response schema."""
    id: int

    # Metrics (auto-calculated)
    customer_count: int = 0
    total_arr: Optional[float] = None
    avg_health_score: Optional[float] = None
    churn_risk_count: Optional[int] = None

    # Timing
    last_evaluated_at: Optional[datetime] = None
    next_evaluation_at: Optional[datetime] = None

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
