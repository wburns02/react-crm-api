"""
Survey Models for Enterprise Customer Success Platform

Enables NPS, CSAT, CES and custom surveys with:
- Survey creation and management
- Question templates
- Response collection and analysis
- Automated survey triggers
- AI-powered analysis and insights (2025-2026 enhancements)
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Survey(Base):
    """
    Survey definition for NPS, CSAT, CES, or custom surveys.
    """
    __tablename__ = "cs_surveys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Survey type
    survey_type = Column(
        SQLEnum('nps', 'csat', 'ces', 'custom', name='cs_survey_type_enum'),
        default='nps'
    )

    # Status
    status = Column(
        SQLEnum('draft', 'active', 'paused', 'completed', name='cs_survey_status_enum'),
        default='draft'
    )

    # Trigger configuration
    trigger_type = Column(
        SQLEnum('manual', 'scheduled', 'event', 'milestone', name='cs_survey_trigger_enum'),
        default='manual'
    )

    # For scheduled triggers
    scheduled_at = Column(DateTime(timezone=True))
    schedule_recurrence = Column(String(50))  # 'once', 'weekly', 'monthly', 'quarterly'

    # For event triggers
    trigger_event = Column(String(100))  # e.g., 'onboarding_complete', 'support_ticket_resolved'

    # Target segment (optional)
    target_segment_id = Column(Integer, ForeignKey("cs_segments.id"))

    # Survey settings
    is_anonymous = Column(Boolean, default=False)
    allow_multiple_responses = Column(Boolean, default=False)
    send_reminder = Column(Boolean, default=True)
    reminder_days = Column(Integer, default=3)

    # 2025-2026 Enhancements: Delivery and A/B Testing
    delivery_channel = Column(String(50))  # 'email', 'sms', 'in_app', 'multi'
    reminder_count = Column(Integer, default=1)  # Number of reminders to send
    last_reminder_sent = Column(DateTime(timezone=True))  # Timestamp of last reminder
    response_rate = Column(Float)  # Calculated response rate percentage
    a_b_test_variant = Column(String(50))  # For A/B testing different survey versions
    conditional_logic = Column(JSON)  # Question branching rules {"question_id": {"condition": "equals", "value": 5, "next_question_id": 10}}

    # Metrics (auto-calculated)
    responses_count = Column(Integer, default=0)
    avg_score = Column(Float)
    completion_rate = Column(Float)

    # NPS specific
    promoters_count = Column(Integer, default=0)
    passives_count = Column(Integer, default=0)
    detractors_count = Column(Integer, default=0)

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    questions = relationship("SurveyQuestion", back_populates="survey", cascade="all, delete-orphan", order_by="SurveyQuestion.order")
    responses = relationship("SurveyResponse", back_populates="survey", cascade="all, delete-orphan")
    analyses = relationship("SurveyAnalysis", back_populates="survey", cascade="all, delete-orphan")
    target_segment = relationship("Segment", foreign_keys=[target_segment_id])

    def __repr__(self):
        return f"<Survey id={self.id} name='{self.name}' type={self.survey_type}>"


class SurveyQuestion(Base):
    """
    Individual question within a survey.
    """
    __tablename__ = "cs_survey_questions"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("cs_surveys.id"), nullable=False, index=True)

    # Question content
    text = Column(Text, nullable=False)
    description = Column(Text)  # Helper text for the question

    # Question type
    question_type = Column(
        SQLEnum('rating', 'scale', 'text', 'multiple_choice', 'single_choice', name='cs_question_type_enum'),
        nullable=False
    )

    # Order within survey
    order = Column(Integer, default=0)

    # Settings
    is_required = Column(Boolean, default=True)

    # For scale questions
    scale_min = Column(Integer, default=0)
    scale_max = Column(Integer, default=10)
    scale_min_label = Column(String(100))  # e.g., "Not likely"
    scale_max_label = Column(String(100))  # e.g., "Very likely"

    # For multiple choice
    options = Column(JSON)  # ["Option A", "Option B", "Option C"]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    survey = relationship("Survey", back_populates="questions")
    answers = relationship("SurveyAnswer", back_populates="question", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SurveyQuestion id={self.id} type={self.question_type}>"


class SurveyResponse(Base):
    """
    A customer's response to a survey (contains multiple answers).
    """
    __tablename__ = "cs_survey_responses"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("cs_surveys.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Overall survey metrics for this response
    overall_score = Column(Float)  # Calculated score (NPS score, CSAT rating, etc.)

    # Sentiment analysis
    sentiment = Column(
        SQLEnum('positive', 'neutral', 'negative', name='cs_sentiment_enum')
    )
    sentiment_score = Column(Float)  # -1 to 1

    # 2025-2026 Enhancements: AI-detected insights
    feedback_text = Column(Text)  # Consolidated open-text feedback from all text answers
    topics_detected = Column(JSON)  # AI-detected topics ["billing", "support", "feature_request"]
    urgency_level = Column(
        SQLEnum('critical', 'high', 'medium', 'low', name='cs_urgency_level_enum')
    )  # AI-determined urgency

    # Action tracking for follow-up
    action_taken = Column(Boolean, default=False)
    action_type = Column(String(50))  # 'callback', 'ticket', 'offer', 'escalation', 'task'
    action_taken_at = Column(DateTime(timezone=True))
    action_taken_by = Column(Integer, ForeignKey("api_users.id"))

    # Response metadata
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    is_complete = Column(Boolean, default=False)
    completion_time_seconds = Column(Integer)

    # Source tracking
    source = Column(String(50))  # 'email', 'in_app', 'sms'
    device = Column(String(50))  # 'desktop', 'mobile', 'tablet'

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    survey = relationship("Survey", back_populates="responses")
    customer = relationship("Customer", backref="survey_responses")
    answers = relationship("SurveyAnswer", back_populates="response", cascade="all, delete-orphan")
    analyses = relationship("SurveyAnalysis", back_populates="response", cascade="all, delete-orphan")
    action_user = relationship("User", foreign_keys=[action_taken_by])

    def __repr__(self):
        return f"<SurveyResponse id={self.id} survey_id={self.survey_id} customer_id={self.customer_id}>"


class SurveyAnswer(Base):
    """
    Individual answer to a survey question.
    """
    __tablename__ = "cs_survey_answers"

    id = Column(Integer, primary_key=True, index=True)
    response_id = Column(Integer, ForeignKey("cs_survey_responses.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("cs_survey_questions.id"), nullable=False, index=True)

    # Answer content (depends on question type)
    rating_value = Column(Integer)  # For rating/scale questions
    text_value = Column(Text)  # For text questions
    choice_values = Column(JSON)  # For multiple choice ["Option A", "Option B"]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    response = relationship("SurveyResponse", back_populates="answers")
    question = relationship("SurveyQuestion", back_populates="answers")

    def __repr__(self):
        return f"<SurveyAnswer id={self.id} question_id={self.question_id}>"


class SurveyAnalysis(Base):
    """
    AI-powered analysis results for surveys and individual responses.

    2025-2026 Enhancement: Stores sentiment analysis, theme extraction,
    churn risk indicators, and actionable recommendations generated by AI.
    """
    __tablename__ = "cs_survey_analyses"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("cs_surveys.id"), nullable=False, index=True)
    response_id = Column(Integer, ForeignKey("cs_survey_responses.id"), nullable=True, index=True)  # null = survey-level analysis

    # AI Analysis Results - Sentiment
    sentiment_breakdown = Column(JSON)  # {"positive": 45, "neutral": 30, "negative": 25}

    # AI Analysis Results - Themes and Topics
    key_themes = Column(JSON)  # ["slow response", "great product", "pricing concerns"]

    # AI Analysis Results - Issues and Risks
    urgent_issues = Column(JSON)  # [{"text": "...", "customer_id": 1, "severity": "high"}]
    churn_risk_indicators = Column(JSON)  # [{"indicator": "competitor_mention", "weight": 0.8, "details": "..."}]
    competitor_mentions = Column(JSON)  # [{"competitor": "CompanyX", "context": "considering switch", "customer_id": 1}]

    # AI Analysis Results - Recommendations
    action_recommendations = Column(JSON)  # [{"type": "callback", "customer_id": 1, "reason": "...", "priority": "high"}]

    # Calculated Scores (-1 to 1 for sentiment, 0 to 100 for others)
    overall_sentiment_score = Column(Float)  # -1 to 1 scale
    churn_risk_score = Column(Float)  # 0 to 100 - likelihood of churn
    urgency_score = Column(Float)  # 0 to 100 - how urgent is follow-up

    # Summary text for quick review
    executive_summary = Column(Text)  # AI-generated summary of key findings

    # Metadata
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())
    analysis_version = Column(String(20))  # Track AI model version, e.g., "gpt-4-2025", "claude-3"
    analysis_model = Column(String(100))  # Specific model identifier
    tokens_used = Column(Integer)  # Track API usage for cost analysis

    # Status tracking
    status = Column(
        SQLEnum('pending', 'processing', 'completed', 'failed', name='cs_analysis_status_enum'),
        default='pending'
    )
    error_message = Column(Text)  # Store error details if analysis fails

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    survey = relationship("Survey", back_populates="analyses")
    response = relationship("SurveyResponse", back_populates="analyses")

    def __repr__(self):
        scope = f"response_id={self.response_id}" if self.response_id else "survey-level"
        return f"<SurveyAnalysis id={self.id} survey_id={self.survey_id} {scope}>"


class SurveyAction(Base):
    """
    Actions created from AI insights or manual review of survey responses.

    Links survey insights to concrete follow-up actions like tasks, callbacks,
    tickets, or offers.
    """
    __tablename__ = "cs_survey_actions"

    id = Column(Integer, primary_key=True, index=True)
    survey_id = Column(Integer, ForeignKey("cs_surveys.id"), nullable=False, index=True)
    response_id = Column(Integer, ForeignKey("cs_survey_responses.id"), nullable=True, index=True)
    analysis_id = Column(Integer, ForeignKey("cs_survey_analyses.id"), nullable=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Action details
    action_type = Column(
        SQLEnum('callback', 'task', 'ticket', 'offer', 'escalation', 'email', 'meeting', name='cs_survey_action_type_enum'),
        nullable=False
    )
    title = Column(String(300), nullable=False)
    description = Column(Text)
    priority = Column(
        SQLEnum('low', 'medium', 'high', 'critical', name='cs_action_priority_enum'),
        default='medium'
    )

    # Source of the action
    source = Column(String(50))  # 'ai_recommendation', 'manual', 'automation'
    ai_confidence = Column(Float)  # 0 to 1 - AI confidence in recommendation

    # Assignment and ownership
    assigned_to_user_id = Column(Integer, ForeignKey("api_users.id"))
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Status tracking
    status = Column(
        SQLEnum('pending', 'in_progress', 'completed', 'cancelled', name='cs_action_status_enum'),
        default='pending'
    )

    # Due date and completion
    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    outcome = Column(Text)  # Result of the action

    # Link to created entity (if action creates something)
    linked_entity_type = Column(String(50))  # 'task', 'ticket', 'escalation', etc.
    linked_entity_id = Column(Integer)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    survey = relationship("Survey")
    response = relationship("SurveyResponse")
    analysis = relationship("SurveyAnalysis")
    customer = relationship("Customer")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    def __repr__(self):
        return f"<SurveyAction id={self.id} type={self.action_type} status={self.status}>"
