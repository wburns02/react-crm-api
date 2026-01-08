"""
A/B Test Schemas for Campaign Optimization

Pydantic schemas for A/B testing endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class ABTestType(str, Enum):
    """Type of element being tested."""
    SUBJECT = "subject"
    CONTENT = "content"
    SEND_TIME = "send_time"
    CHANNEL = "channel"


class ABTestStatus(str, Enum):
    """Status of an A/B test."""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class PrimaryMetric(str, Enum):
    """Primary metric for determining winner."""
    CONVERSION = "conversion"
    OPEN = "open"
    CLICK = "click"


# Base Schemas

class ABTestBase(BaseModel):
    """Base A/B test schema."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    test_type: ABTestType = ABTestType.SUBJECT
    variant_a_name: str = Field(default="Control", max_length=200)
    variant_a_config: dict[str, Any] = Field(default_factory=dict)
    variant_b_name: str = Field(default="Variant B", max_length=200)
    variant_b_config: dict[str, Any] = Field(default_factory=dict)
    traffic_split: float = Field(default=50.0, ge=0, le=100)
    min_sample_size: int = Field(default=100, ge=10)
    significance_threshold: float = Field(default=95.0, ge=50, le=99.9)
    auto_winner: bool = True
    primary_metric: PrimaryMetric = PrimaryMetric.CONVERSION


class ABTestCreate(ABTestBase):
    """Schema for creating an A/B test."""
    campaign_id: int


class ABTestUpdate(BaseModel):
    """Schema for updating an A/B test."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    variant_a_name: Optional[str] = Field(None, max_length=200)
    variant_a_config: Optional[dict[str, Any]] = None
    variant_b_name: Optional[str] = Field(None, max_length=200)
    variant_b_config: Optional[dict[str, Any]] = None
    traffic_split: Optional[float] = Field(None, ge=0, le=100)
    min_sample_size: Optional[int] = Field(None, ge=10)
    significance_threshold: Optional[float] = Field(None, ge=50, le=99.9)
    auto_winner: Optional[bool] = None
    primary_metric: Optional[PrimaryMetric] = None


# Response Schemas

class VariantMetrics(BaseModel):
    """Metrics for a single variant."""
    name: str
    config: Optional[dict[str, Any]] = None
    sent: int = 0
    opened: int = 0
    clicked: int = 0
    converted: int = 0
    open_rate: float = 0
    click_rate: float = 0
    conversion_rate: float = 0
    primary_metric_rate: Optional[float] = None


class StatisticalResults(BaseModel):
    """Statistical analysis results."""
    chi_square: Optional[dict[str, Any]] = None
    z_score: Optional[dict[str, Any]] = None
    confidence: float = 0
    is_significant: bool = False
    significance_threshold: float = 95.0
    min_sample_size: int = 100
    current_sample_size: int = 0
    has_min_sample: bool = False


class LiftResult(BaseModel):
    """Lift/improvement calculation."""
    value: float = 0
    direction: str = "none"  # increase, decrease, none
    variant_b_vs_a: str = "0%"


class ABTestResponse(BaseModel):
    """A/B test response schema."""
    id: int
    campaign_id: int
    name: str
    description: Optional[str] = None
    test_type: str
    status: str
    variant_a_name: str
    variant_a_config: Optional[dict[str, Any]] = None
    variant_b_name: str
    variant_b_config: Optional[dict[str, Any]] = None
    traffic_split: float = 50.0
    variant_a_sent: int = 0
    variant_a_opened: int = 0
    variant_a_clicked: int = 0
    variant_a_converted: int = 0
    variant_b_sent: int = 0
    variant_b_opened: int = 0
    variant_b_clicked: int = 0
    variant_b_converted: int = 0
    winning_variant: Optional[str] = None
    confidence_level: Optional[float] = None
    is_significant: bool = False
    min_sample_size: int = 100
    significance_threshold: float = 95.0
    auto_winner: bool = True
    primary_metric: str = "conversion"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ABTestListResponse(BaseModel):
    """Paginated A/B test list response."""
    items: list[ABTestResponse]
    total: int
    page: int
    page_size: int


class ABTestResults(BaseModel):
    """Comprehensive A/B test results with statistical analysis."""
    test_id: int
    test_name: str
    test_type: str
    status: str
    primary_metric: str
    variant_a: VariantMetrics
    variant_b: VariantMetrics
    statistics: StatisticalResults
    winner: Optional[str] = None
    lift: LiftResult
    recommendation: str = ""
    timestamps: Optional[dict[str, Any]] = None


# Action Schemas

class MetricUpdateRequest(BaseModel):
    """Request to update a metric."""
    variant: str = Field(..., pattern="^[ab]$")  # 'a' or 'b'
    metric: str = Field(..., pattern="^(sent|opened|clicked|converted)$")
    increment: int = Field(default=1, ge=1)


class CompleteTestRequest(BaseModel):
    """Request to complete a test with optional manual winner."""
    winner: Optional[str] = Field(None, pattern="^[ab]$")  # 'a' or 'b' or None


class AssignVariantResponse(BaseModel):
    """Response from variant assignment."""
    test_id: int
    assigned_variant: str
    variant_name: str
    variant_config: Optional[dict[str, Any]] = None


class ActionResponse(BaseModel):
    """Generic action response."""
    status: str = "success"
    message: str
    test_id: Optional[int] = None
    new_status: Optional[str] = None
