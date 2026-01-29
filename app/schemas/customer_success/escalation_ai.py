"""
Escalation AI Schemas for Enterprise Customer Success Platform

Schemas for AI-guided escalation management - the "What Do I Do Now?" system.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class UrgencyLevel(str, Enum):
    IMMEDIATE = "immediate"
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"


class ActionType(str, Enum):
    CALL = "call"
    EMAIL = "email"
    SCHEDULE_MEETING = "schedule_meeting"
    SEND_APOLOGY = "send_apology"
    OFFER_DISCOUNT = "offer_discount"
    ESCALATE_TO_MANAGER = "escalate_to_manager"
    ASSIGN_SENIOR_REP = "assign_senior_rep"
    FOLLOW_UP = "follow_up"


# Sentiment schemas


class SentimentResponse(BaseModel):
    """Customer sentiment analysis result."""

    score: float = Field(..., ge=-1, le=1, description="Sentiment score from -1 (negative) to 1 (positive)")
    label: str = Field(..., description="Human-readable sentiment label")
    emoji: str = Field(..., description="Visual emoji indicator")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in the analysis")
    key_phrases: List[str] = Field(default_factory=list, description="Key emotional phrases detected")


# Action schemas


class RecommendedActionResponse(BaseModel):
    """AI-recommended action to take."""

    type: ActionType = Field(..., description="Type of action to take")
    urgency: UrgencyLevel = Field(..., description="How urgent the action is")
    urgency_minutes: int = Field(..., description="Minutes until action should be taken")
    reason: str = Field(..., description="Why this action is recommended")
    predicted_success: float = Field(..., ge=0, le=1, description="Predicted success rate")
    time_estimate_minutes: int = Field(..., description="Estimated time to complete action")
    big_button_text: str = Field(..., description="Text for the main action button")


# Script schemas


class ScriptResponse(BaseModel):
    """Script guidance with exact words to say."""

    opening: str = Field(..., description="How to open the conversation")
    key_points: List[str] = Field(default_factory=list, description="Key points to cover")
    empathy_statements: List[str] = Field(default_factory=list, description="Empathy statements to use")
    closing: str = Field(..., description="How to close the conversation")
    what_not_to_say: List[str] = Field(default_factory=list, description="Things to avoid saying")


# Playbook schemas


class PlaybookStepResponse(BaseModel):
    """Single step in a playbook."""

    order: int
    action: str
    description: str
    script: Optional[str] = None


class PlaybookResponse(BaseModel):
    """Playbook details."""

    id: Optional[str] = None
    name: Optional[str] = None
    success_rate: Optional[float] = None
    steps: List[PlaybookStepResponse] = Field(default_factory=list)


# SLA schemas


class SLAStatusResponse(BaseModel):
    """SLA status with visual indicators."""

    status: str = Field(..., description="on_track, warning, critical, or breached")
    color: str = Field(..., description="green, yellow, red, or gray")
    message: str = Field(..., description="Human-readable status message")
    hours_remaining: Optional[float] = None


# Customer context


class CustomerContextResponse(BaseModel):
    """Customer context for the escalation."""

    name: str
    tenure_days: int = 0
    lifetime_value: Optional[float] = None
    past_escalations: int = 0


# Similar case schemas


class SimilarCaseResponse(BaseModel):
    """Similar past escalation for reference."""

    id: int
    title: str
    outcome: str
    resolution_time_hours: Optional[float] = None
    resolution_summary: Optional[str] = None


# Main guidance response


class EscalationGuidanceResponse(BaseModel):
    """
    Complete AI guidance for an escalation.
    This is the 'WHAT DO I DO NOW?' answer.
    """

    escalation_id: int
    summary: str = Field(..., description="Brief situation summary")
    sentiment: SentimentResponse
    recommended_action: RecommendedActionResponse
    script: ScriptResponse
    win_condition: str = Field(..., description="What success looks like")
    playbook: Optional[PlaybookResponse] = None
    similar_cases: List[SimilarCaseResponse] = Field(default_factory=list)
    priority_score: int = Field(..., ge=1, le=100, description="Priority score for sorting")
    sla_status: SLAStatusResponse
    customer_context: CustomerContextResponse


# Alert schemas


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProactiveAlertResponse(BaseModel):
    """Proactive alert for escalation needing attention."""

    type: str = Field(..., description="Alert type: sla_warning, unassigned_critical, no_response, etc.")
    severity: AlertSeverity
    escalation_id: int
    title: str
    message: str
    action: str = Field(..., description="Recommended action to take")


class ProactiveAlertsListResponse(BaseModel):
    """List of proactive alerts."""

    alerts: List[ProactiveAlertResponse]
    total: int


# Response generation schemas


class GenerateResponseRequest(BaseModel):
    """Request to generate a response."""

    response_type: str = Field(default="email", description="Type of response: email, sms, chat")


class GeneratedResponseResponse(BaseModel):
    """Generated response text."""

    escalation_id: int
    response_type: str
    generated_text: str
    editable: bool = True


# Playbook progress schemas


class PlaybookProgressResponse(BaseModel):
    """Track progress through a playbook."""

    playbook_id: str
    playbook_name: str
    total_steps: int
    completed_steps: int
    current_step: int
    steps: List[Dict[str, Any]]


# Queue item for action queue


class ActionQueueItem(BaseModel):
    """Single item in the action queue."""

    escalation_id: int
    customer_name: str
    title: str
    severity: str
    sentiment_emoji: str
    sentiment_label: str
    time_remaining_minutes: Optional[int] = None
    sla_status: str
    sla_color: str
    recommended_action: str
    big_button_text: str
    priority_score: int


class ActionQueueResponse(BaseModel):
    """Prioritized action queue."""

    items: List[ActionQueueItem]
    total: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
