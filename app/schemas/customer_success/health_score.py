"""
Health Score Schemas for Enterprise Customer Success Platform
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Literal
from enum import Enum

from app.schemas.types import UUIDStr


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    CHURNED = "churned"


class ScoreTrend(str, Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class HealthEventType(str, Enum):
    SCORE_CALCULATED = "score_calculated"
    MANUAL_OVERRIDE = "manual_override"
    COMPONENT_UPDATE = "component_update"
    THRESHOLD_CROSSED = "threshold_crossed"
    ALERT_TRIGGERED = "alert_triggered"


class HealthScoreBase(BaseModel):
    """Base health score schema."""

    overall_score: int = Field(50, ge=0, le=100, description="Overall health score 0-100")
    health_status: Optional[HealthStatus] = None

    # Component scores
    product_adoption_score: Optional[int] = Field(None, ge=0, le=100)
    engagement_score: Optional[int] = Field(None, ge=0, le=100)
    relationship_score: Optional[int] = Field(None, ge=0, le=100)
    financial_score: Optional[int] = Field(None, ge=0, le=100)
    support_score: Optional[int] = Field(None, ge=0, le=100)

    # Component weights (must sum to 100)
    adoption_weight: int = Field(30, ge=0, le=100)
    engagement_weight: int = Field(25, ge=0, le=100)
    relationship_weight: int = Field(15, ge=0, le=100)
    financial_weight: int = Field(20, ge=0, le=100)
    support_weight: int = Field(10, ge=0, le=100)

    # Predictive scores
    churn_probability: Optional[float] = Field(None, ge=0, le=1)
    expansion_probability: Optional[float] = Field(None, ge=0, le=1)

    # Trend
    score_trend: Optional[ScoreTrend] = None
    trend_percentage: Optional[float] = None

    # Override
    is_manually_set: bool = False
    manual_override_reason: Optional[str] = None


class HealthScoreCreate(HealthScoreBase):
    """Schema for creating a health score."""

    customer_id: UUIDStr


class HealthScoreUpdate(BaseModel):
    """Schema for updating a health score."""

    overall_score: Optional[int] = Field(None, ge=0, le=100)
    health_status: Optional[HealthStatus] = None

    product_adoption_score: Optional[int] = Field(None, ge=0, le=100)
    engagement_score: Optional[int] = Field(None, ge=0, le=100)
    relationship_score: Optional[int] = Field(None, ge=0, le=100)
    financial_score: Optional[int] = Field(None, ge=0, le=100)
    support_score: Optional[int] = Field(None, ge=0, le=100)

    adoption_weight: Optional[int] = Field(None, ge=0, le=100)
    engagement_weight: Optional[int] = Field(None, ge=0, le=100)
    relationship_weight: Optional[int] = Field(None, ge=0, le=100)
    financial_weight: Optional[int] = Field(None, ge=0, le=100)
    support_weight: Optional[int] = Field(None, ge=0, le=100)

    churn_probability: Optional[float] = Field(None, ge=0, le=1)
    expansion_probability: Optional[float] = Field(None, ge=0, le=1)

    is_manually_set: Optional[bool] = None
    manual_override_reason: Optional[str] = None


class HealthScoreResponse(HealthScoreBase):
    """Health score response schema."""

    id: int
    customer_id: UUIDStr

    # Thresholds (at time of scoring)
    healthy_threshold: int
    at_risk_threshold: int
    critical_threshold: int

    # Component details
    adoption_details: Optional[dict] = None
    engagement_details: Optional[dict] = None
    relationship_details: Optional[dict] = None
    financial_details: Optional[dict] = None
    support_details: Optional[dict] = None

    # Timestamps
    calculated_at: Optional[datetime] = None
    previous_score: Optional[int] = None
    previous_score_date: Optional[datetime] = None
    next_review_date: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HealthScoreListResponse(BaseModel):
    """Paginated health score list response."""

    items: list[HealthScoreResponse]
    total: int
    page: int
    page_size: int


# Health Score Events


class HealthScoreEventBase(BaseModel):
    """Base health score event schema."""

    event_type: HealthEventType
    old_score: Optional[int] = None
    new_score: Optional[int] = None
    change_amount: Optional[int] = None
    component_affected: Optional[str] = None
    reason: Optional[str] = None
    details: Optional[dict] = None


class HealthScoreEventCreate(HealthScoreEventBase):
    """Schema for creating a health score event."""

    health_score_id: int
    triggered_by_user_id: Optional[int] = None


class HealthScoreEventResponse(HealthScoreEventBase):
    """Health score event response schema."""

    id: int
    health_score_id: int
    triggered_by_user_id: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HealthScoreEventListResponse(BaseModel):
    """Paginated health score event list response."""

    items: list[HealthScoreEventResponse]
    total: int
    page: int
    page_size: int


# Bulk Operations


class HealthScoreBulkCalculateRequest(BaseModel):
    """Request to bulk calculate health scores."""

    customer_ids: Optional[list[str]] = Field(None, description="Specific customer IDs, or None for all")
    segment_id: Optional[int] = Field(None, description="Calculate for all customers in segment")
    force_recalculate: bool = Field(False, description="Recalculate even if recently calculated")


class HealthScoreTrendResponse(BaseModel):
    """Health score trend data for charts."""

    customer_id: UUIDStr
    data_points: list[dict]  # [{"date": "2024-01-01", "score": 75, "status": "healthy"}]
    period_start: datetime
    period_end: datetime
    average_score: float
    min_score: int
    max_score: int
    trend: ScoreTrend
    change_percentage: float
