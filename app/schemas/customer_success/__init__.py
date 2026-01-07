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
from app.schemas.customer_success.survey import (
    SurveyType, SurveyStatus, SurveyTrigger, QuestionType, Sentiment,
    SurveyQuestionBase, SurveyQuestionCreate, SurveyQuestionUpdate, SurveyQuestionResponse,
    SurveyBase, SurveyCreate, SurveyUpdate, SurveyResponse, SurveyListResponse,
    SurveyAnswerCreate, SurveySubmissionCreate, SurveyAnswerResponse, SurveySubmissionResponse,
    SurveyResponseListResponse, NPSBreakdown, SurveyAnalytics,
)
from app.schemas.customer_success.campaign import (
    CampaignType, CampaignStatus, CampaignChannel, StepType, EnrollmentStatus, ExecutionStatus,
    CampaignStepBase, CampaignStepCreate, CampaignStepUpdate, CampaignStepResponse,
    CampaignBase, CampaignCreate, CampaignUpdate, CampaignResponse, CampaignListResponse,
    CampaignEnrollmentCreate, CampaignEnrollmentUpdate, CampaignEnrollmentResponse,
    EnrollmentListResponse, StepExecutionResponse, CampaignAnalytics,
)
from app.schemas.customer_success.escalation import (
    EscalationType, EscalationSeverity, EscalationStatus, NoteType,
    EscalationNoteBase, EscalationNoteCreate, EscalationNoteUpdate, EscalationNoteResponse,
    EscalationActivityResponse,
    EscalationBase, EscalationCreate, EscalationUpdate, EscalationResponse, EscalationListResponse,
    EscalationAnalytics,
)
from app.schemas.customer_success.collaboration import (
    ResourceType, ResourceCategory, Visibility,
    ResourceCommentBase, ResourceCommentCreate, ResourceCommentResponse,
    ResourceBase, ResourceCreate, ResourceUpdate, ResourceResponse, ResourceListResponse,
    TeamNoteCommentBase, TeamNoteCommentCreate, TeamNoteCommentResponse,
    TeamNoteBase, TeamNoteCreate, TeamNoteUpdate, TeamNoteResponse, TeamNoteListResponse,
    ActivityCreate, ActivityResponse, ActivityListResponse,
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
    # Survey
    "SurveyType", "SurveyStatus", "SurveyTrigger", "QuestionType", "Sentiment",
    "SurveyQuestionBase", "SurveyQuestionCreate", "SurveyQuestionUpdate", "SurveyQuestionResponse",
    "SurveyBase", "SurveyCreate", "SurveyUpdate", "SurveyResponse", "SurveyListResponse",
    "SurveyAnswerCreate", "SurveySubmissionCreate", "SurveyAnswerResponse", "SurveySubmissionResponse",
    "SurveyResponseListResponse", "NPSBreakdown", "SurveyAnalytics",
    # Campaign
    "CampaignType", "CampaignStatus", "CampaignChannel", "StepType", "EnrollmentStatus", "ExecutionStatus",
    "CampaignStepBase", "CampaignStepCreate", "CampaignStepUpdate", "CampaignStepResponse",
    "CampaignBase", "CampaignCreate", "CampaignUpdate", "CampaignResponse", "CampaignListResponse",
    "CampaignEnrollmentCreate", "CampaignEnrollmentUpdate", "CampaignEnrollmentResponse",
    "EnrollmentListResponse", "StepExecutionResponse", "CampaignAnalytics",
    # Escalation
    "EscalationType", "EscalationSeverity", "EscalationStatus", "NoteType",
    "EscalationNoteBase", "EscalationNoteCreate", "EscalationNoteUpdate", "EscalationNoteResponse",
    "EscalationActivityResponse",
    "EscalationBase", "EscalationCreate", "EscalationUpdate", "EscalationResponse", "EscalationListResponse",
    "EscalationAnalytics",
    # Collaboration
    "ResourceType", "ResourceCategory", "Visibility",
    "ResourceCommentBase", "ResourceCommentCreate", "ResourceCommentResponse",
    "ResourceBase", "ResourceCreate", "ResourceUpdate", "ResourceResponse", "ResourceListResponse",
    "TeamNoteCommentBase", "TeamNoteCommentCreate", "TeamNoteCommentResponse",
    "TeamNoteBase", "TeamNoteCreate", "TeamNoteUpdate", "TeamNoteResponse", "TeamNoteListResponse",
    "ActivityCreate", "ActivityResponse", "ActivityListResponse",
]
