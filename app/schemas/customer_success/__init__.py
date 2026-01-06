"""
Customer Success Platform Pydantic Schemas

Comprehensive schemas for the Enterprise Customer Success Platform.
"""

from app.schemas.customer_success.health_score import (
    HealthScoreBase, HealthScoreCreate, HealthScoreUpdate, HealthScoreResponse,
    HealthScoreEventBase, HealthScoreEventCreate, HealthScoreEventResponse,
    HealthScoreListResponse, HealthScoreEventListResponse,
    HealthScoreBulkCalculateRequest, HealthScoreTrendResponse,
)
from app.schemas.customer_success.segment import (
    SegmentBase, SegmentCreate, SegmentUpdate, SegmentResponse,
    CustomerSegmentBase, CustomerSegmentResponse,
    SegmentListResponse, SegmentRuleSet, SegmentRule,
    SegmentPreviewRequest, SegmentPreviewResponse,
)
from app.schemas.customer_success.journey import (
    JourneyBase, JourneyCreate, JourneyUpdate, JourneyResponse,
    JourneyStepBase, JourneyStepCreate, JourneyStepUpdate, JourneyStepResponse,
    JourneyEnrollmentBase, JourneyEnrollmentCreate, JourneyEnrollmentResponse,
    JourneyStepExecutionResponse,
    JourneyListResponse, JourneyEnrollmentListResponse,
    JourneyEnrollRequest, JourneyBulkEnrollRequest,
)
from app.schemas.customer_success.playbook import (
    PlaybookBase, PlaybookCreate, PlaybookUpdate, PlaybookResponse,
    PlaybookStepBase, PlaybookStepCreate, PlaybookStepUpdate, PlaybookStepResponse,
    PlaybookExecutionBase, PlaybookExecutionCreate, PlaybookExecutionResponse,
    PlaybookListResponse, PlaybookExecutionListResponse,
    PlaybookTriggerRequest, PlaybookBulkTriggerRequest,
)
from app.schemas.customer_success.task import (
    CSTaskBase, CSTaskCreate, CSTaskUpdate, CSTaskResponse,
    CSTaskListResponse, CSTaskBulkUpdateRequest,
    CSTaskCompleteRequest, CSTaskAssignRequest,
)
from app.schemas.customer_success.touchpoint import (
    TouchpointBase, TouchpointCreate, TouchpointUpdate, TouchpointResponse,
    TouchpointListResponse, TouchpointSentimentAnalysis,
    TouchpointTimelineResponse,
)

__all__ = [
    # Health Score
    "HealthScoreBase", "HealthScoreCreate", "HealthScoreUpdate", "HealthScoreResponse",
    "HealthScoreEventBase", "HealthScoreEventCreate", "HealthScoreEventResponse",
    "HealthScoreListResponse", "HealthScoreEventListResponse",
    "HealthScoreBulkCalculateRequest", "HealthScoreTrendResponse",
    # Segment
    "SegmentBase", "SegmentCreate", "SegmentUpdate", "SegmentResponse",
    "CustomerSegmentBase", "CustomerSegmentResponse",
    "SegmentListResponse", "SegmentRuleSet", "SegmentRule",
    "SegmentPreviewRequest", "SegmentPreviewResponse",
    # Journey
    "JourneyBase", "JourneyCreate", "JourneyUpdate", "JourneyResponse",
    "JourneyStepBase", "JourneyStepCreate", "JourneyStepUpdate", "JourneyStepResponse",
    "JourneyEnrollmentBase", "JourneyEnrollmentCreate", "JourneyEnrollmentResponse",
    "JourneyStepExecutionResponse",
    "JourneyListResponse", "JourneyEnrollmentListResponse",
    "JourneyEnrollRequest", "JourneyBulkEnrollRequest",
    # Playbook
    "PlaybookBase", "PlaybookCreate", "PlaybookUpdate", "PlaybookResponse",
    "PlaybookStepBase", "PlaybookStepCreate", "PlaybookStepUpdate", "PlaybookStepResponse",
    "PlaybookExecutionBase", "PlaybookExecutionCreate", "PlaybookExecutionResponse",
    "PlaybookListResponse", "PlaybookExecutionListResponse",
    "PlaybookTriggerRequest", "PlaybookBulkTriggerRequest",
    # Task
    "CSTaskBase", "CSTaskCreate", "CSTaskUpdate", "CSTaskResponse",
    "CSTaskListResponse", "CSTaskBulkUpdateRequest",
    "CSTaskCompleteRequest", "CSTaskAssignRequest",
    # Touchpoint
    "TouchpointBase", "TouchpointCreate", "TouchpointUpdate", "TouchpointResponse",
    "TouchpointListResponse", "TouchpointSentimentAnalysis",
    "TouchpointTimelineResponse",
]
