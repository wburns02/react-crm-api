"""
Escalation Schemas for Enterprise Customer Success Platform
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class EscalationType(str, Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    SERVICE = "service"
    PRODUCT = "product"
    RELATIONSHIP = "relationship"
    EXECUTIVE = "executive"
    CUSTOM = "custom"


class EscalationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EscalationStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    PENDING_CUSTOMER = "pending_customer"
    PENDING_INTERNAL = "pending_internal"
    RESOLVED = "resolved"
    CLOSED = "closed"


class NoteType(str, Enum):
    UPDATE = "update"
    INTERNAL = "internal"
    CUSTOMER_COMMUNICATION = "customer_communication"
    RESOLUTION = "resolution"


# Escalation Note Schemas

class EscalationNoteBase(BaseModel):
    """Base escalation note schema."""
    content: str = Field(..., min_length=1)
    note_type: NoteType = NoteType.UPDATE
    is_internal: bool = True


class EscalationNoteCreate(EscalationNoteBase):
    """Schema for creating a note."""
    pass


class EscalationNoteUpdate(BaseModel):
    """Schema for updating a note."""
    content: Optional[str] = None
    note_type: Optional[NoteType] = None
    is_internal: Optional[bool] = None


class EscalationNoteResponse(EscalationNoteBase):
    """Escalation note response."""
    id: int
    escalation_id: int
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Escalation Activity Schemas

class EscalationActivityResponse(BaseModel):
    """Escalation activity response."""
    id: int
    escalation_id: int
    activity_type: str
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    performed_by_user_id: Optional[int] = None
    performed_by_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Escalation Schemas

class EscalationBase(BaseModel):
    """Base escalation schema."""
    title: str = Field(..., min_length=1, max_length=300)
    description: str = Field(..., min_length=1)
    escalation_type: EscalationType = EscalationType.SERVICE
    severity: EscalationSeverity = EscalationSeverity.MEDIUM
    priority: int = 50
    source: Optional[str] = None
    source_id: Optional[int] = None
    sla_hours: int = 24
    first_response_sla_hours: int = 4
    revenue_at_risk: Optional[float] = None
    churn_probability: Optional[float] = None
    impact_description: Optional[str] = None
    tags: Optional[list[str]] = None


class EscalationCreate(EscalationBase):
    """Schema for creating an escalation."""
    customer_id: int
    assigned_to_user_id: Optional[int] = None
    escalated_to_user_id: Optional[int] = None


class EscalationUpdate(BaseModel):
    """Schema for updating an escalation."""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    escalation_type: Optional[EscalationType] = None
    severity: Optional[EscalationSeverity] = None
    priority: Optional[int] = None
    status: Optional[EscalationStatus] = None
    assigned_to_user_id: Optional[int] = None
    escalated_to_user_id: Optional[int] = None
    sla_hours: Optional[int] = None
    first_response_sla_hours: Optional[int] = None
    revenue_at_risk: Optional[float] = None
    churn_probability: Optional[float] = None
    impact_description: Optional[str] = None
    root_cause_category: Optional[str] = None
    root_cause_description: Optional[str] = None
    resolution_summary: Optional[str] = None
    resolution_category: Optional[str] = None
    customer_satisfaction: Optional[int] = None
    tags: Optional[list[str]] = None


class EscalationResponse(EscalationBase):
    """Escalation response schema."""
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    status: EscalationStatus = EscalationStatus.OPEN

    # Assignment
    assigned_to_user_id: Optional[int] = None
    assigned_to_name: Optional[str] = None
    escalated_by_user_id: Optional[int] = None
    escalated_by_name: Optional[str] = None
    escalated_to_user_id: Optional[int] = None
    escalated_to_name: Optional[str] = None

    # SLA tracking
    sla_deadline: Optional[datetime] = None
    sla_breached: bool = False
    first_response_at: Optional[datetime] = None
    first_response_breached: bool = False

    # Root cause
    root_cause_category: Optional[str] = None
    root_cause_description: Optional[str] = None

    # Resolution
    resolution_summary: Optional[str] = None
    resolution_category: Optional[str] = None
    customer_satisfaction: Optional[int] = None

    # Related data
    notes: list[EscalationNoteResponse] = []
    activities: list[EscalationActivityResponse] = []

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EscalationListResponse(BaseModel):
    """Paginated escalation list response."""
    items: list[EscalationResponse]
    total: int
    page: int
    page_size: int


# Escalation Analytics

class EscalationAnalytics(BaseModel):
    """Escalation analytics response."""
    total_open: int = 0
    total_in_progress: int = 0
    total_resolved: int = 0
    total_closed: int = 0
    avg_resolution_time_hours: Optional[float] = None
    sla_compliance_rate: Optional[float] = None
    first_response_compliance_rate: Optional[float] = None
    by_severity: dict = {}  # {critical: 5, high: 10, ...}
    by_type: dict = {}  # {technical: 15, billing: 8, ...}
    trend: list[dict] = []  # [{date, opened, resolved}]
    top_root_causes: list[dict] = []  # [{category, count}]
