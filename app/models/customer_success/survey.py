"""
Survey Models for Enterprise Customer Success Platform

Enables NPS, CSAT, CES and custom surveys with:
- Survey creation and management
- Question templates
- Response collection and analysis
- Automated survey triggers
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
