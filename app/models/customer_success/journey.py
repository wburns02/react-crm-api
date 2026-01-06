"""
Journey Models for Enterprise Customer Success Platform

Orchestrates automated customer journeys with multi-step flows,
branching logic, and human touchpoints.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Journey(Base):
    """
    Customer journey definition.

    A journey is an automated sequence of steps that guide customers
    through key milestones (onboarding, adoption, renewal, etc.).
    """
    __tablename__ = "cs_journeys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Journey type
    journey_type = Column(
        SQLEnum(
            'onboarding', 'adoption', 'renewal', 'expansion',
            'risk_mitigation', 'advocacy', 'win_back', 'custom',
            name='cs_journey_type_enum'
        ),
        default='custom'
    )

    # Trigger configuration
    trigger_type = Column(
        SQLEnum(
            'manual', 'segment_entry', 'event', 'scheduled',
            'health_change', 'renewal_window',
            name='cs_journey_trigger_enum'
        ),
        default='manual'
    )

    # Trigger conditions (JSON configuration)
    trigger_config = Column(JSON)
    # Examples:
    # segment_entry: {"segment_id": 5}
    # event: {"event_type": "support_escalation"}
    # health_change: {"direction": "down", "threshold": 60}
    # renewal_window: {"days_before": 90}

    # Segment-based trigger
    trigger_segment_id = Column(Integer, ForeignKey("cs_segments.id"))

    # Journey settings
    status = Column(
        SQLEnum(
            'draft', 'active', 'paused', 'archived',
            name='cs_journey_status_enum'
        ),
        default='draft'
    )
    is_active = Column(Boolean, default=True)  # Deprecated: use status instead
    allow_re_enrollment = Column(Boolean, default=False)
    re_enrollment_cooldown_days = Column(Integer, default=90)
    max_concurrent_enrollments = Column(Integer)  # null = unlimited

    # Exit conditions
    exit_on_segment_leave = Column(Boolean, default=True)
    exit_on_health_threshold = Column(Integer)  # Exit if health goes above this
    exit_on_event = Column(String(100))  # e.g., "renewal_signed"

    # Goals
    goal_metric = Column(String(100))  # e.g., "health_score", "feature_adoption"
    goal_target = Column(Float)  # e.g., 80.0
    goal_timeframe_days = Column(Integer)

    # Metrics (auto-updated)
    total_enrolled = Column(Integer, default=0)
    active_enrolled = Column(Integer, default=0)  # Currently active enrollments
    currently_active = Column(Integer, default=0)  # Deprecated: use active_enrolled
    completed_count = Column(Integer, default=0)
    total_completed = Column(Integer, default=0)  # Deprecated: use completed_count
    goal_achieved_count = Column(Integer, default=0)
    total_exited_early = Column(Integer, default=0)
    avg_completion_days = Column(Float)
    conversion_rate = Column(Float)  # goal_achieved / completed
    success_rate = Column(Float)  # Completed goal / Total completed
    priority = Column(Integer, default=0)  # Higher priority journeys override lower

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    owned_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    steps = relationship("JourneyStep", back_populates="journey", order_by="JourneyStep.step_order", cascade="all, delete-orphan")
    enrollments = relationship("JourneyEnrollment", back_populates="journey", cascade="all, delete-orphan")
    trigger_segment = relationship("Segment", back_populates="journeys")

    def __repr__(self):
        return f"<Journey id={self.id} name='{self.name}' type={self.journey_type} active={self.is_active}>"


class JourneyStep(Base):
    """
    Individual step within a journey.

    Supports various step types: emails, tasks, waits, conditions, etc.
    """
    __tablename__ = "cs_journey_steps"

    id = Column(Integer, primary_key=True, index=True)
    journey_id = Column(Integer, ForeignKey("cs_journeys.id"), nullable=False, index=True)

    step_order = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Step type
    step_type = Column(
        SQLEnum(
            'email', 'in_app_message', 'task', 'wait', 'condition',
            'webhook', 'segment_update', 'health_check', 'human_touchpoint',
            'sms', 'slack_notification', 'custom',
            name='cs_journey_step_type_enum'
        ),
        nullable=False
    )

    # Configuration based on step_type (JSON)
    config = Column(JSON)
    # Examples:
    # email: {"template_id": 5, "subject_override": "...", "personalization": {...}}
    # task: {"title": "...", "type": "call", "assignee_role": "csm", "due_days": 3}
    # wait: {"days": 7} or {"until_event": "email_opened"}
    # condition: {"rules": {...}, "true_step": 5, "false_step": 6}
    # webhook: {"url": "...", "method": "POST", "payload": {...}}

    # Wait configuration (for 'wait' type)
    wait_days = Column(Integer)
    wait_hours = Column(Integer)
    wait_until_event = Column(String(100))
    wait_until_date_field = Column(String(100))  # e.g., "renewal_date"

    # Condition configuration (for 'condition' type)
    condition_rules = Column(JSON)
    true_next_step_id = Column(Integer)
    false_next_step_id = Column(Integer)

    # Branching
    next_step_id = Column(Integer)  # Default next step (null = end)
    is_terminal = Column(Boolean, default=False)

    # Task defaults (for 'task' and 'human_touchpoint' types)
    default_assignee_role = Column(String(50))
    task_due_days = Column(Integer)
    task_priority = Column(String(20))

    # Email/message templates
    email_template_id = Column(Integer)
    in_app_message_config = Column(JSON)

    # Metrics (auto-updated)
    times_executed = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    avg_completion_time_hours = Column(Float)

    # Settings
    is_active = Column(Boolean, default=True)
    skip_if_condition = Column(JSON)  # Skip step if condition met

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    journey = relationship("Journey", back_populates="steps")
    executions = relationship("JourneyStepExecution", back_populates="step")

    def __repr__(self):
        return f"<JourneyStep id={self.id} journey_id={self.journey_id} order={self.step_order} type={self.step_type}>"


class JourneyEnrollment(Base):
    """
    Customer enrollment in a journey.

    Tracks progress through journey steps and outcomes.
    """
    __tablename__ = "cs_journey_enrollments"

    id = Column(Integer, primary_key=True, index=True)
    journey_id = Column(Integer, ForeignKey("cs_journeys.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Current status
    status = Column(
        SQLEnum(
            'active', 'paused', 'completed', 'exited', 'failed',
            name='cs_enrollment_status_enum'
        ),
        default='active'
    )

    # Progress
    current_step_id = Column(Integer, ForeignKey("cs_journey_steps.id"))
    current_step_started_at = Column(DateTime(timezone=True))
    current_step_order = Column(Integer, default=0)
    steps_completed = Column(Integer, default=0)
    steps_total = Column(Integer, default=0)

    # Timing
    enrolled_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    paused_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    exited_at = Column(DateTime(timezone=True))

    # Exit details
    exit_reason = Column(
        SQLEnum(
            'completed', 'goal_achieved', 'manual_exit', 'segment_exit',
            'health_threshold', 'event_triggered', 'timeout', 'error',
            name='cs_exit_reason_enum'
        )
    )
    exit_notes = Column(Text)

    # Goal tracking
    goal_achieved = Column(Boolean, default=False)
    goal_value_at_start = Column(Float)
    goal_value_at_end = Column(Float)

    # Health tracking
    health_score_at_start = Column(Integer)
    health_score_at_end = Column(Integer)

    # Enrollment source
    enrolled_by = Column(String(100))  # 'system', 'user:123', 'segment:5'
    enrollment_reason = Column(Text)  # Why they were enrolled
    enrollment_trigger = Column(String(100))

    # Extra data
    extra_data = Column(JSON)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    journey = relationship("Journey", back_populates="enrollments")
    customer = relationship("Customer", backref="journey_enrollments")
    current_step = relationship("JourneyStep", foreign_keys=[current_step_id])
    step_executions = relationship("JourneyStepExecution", back_populates="enrollment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<JourneyEnrollment id={self.id} journey_id={self.journey_id} customer_id={self.customer_id} status={self.status}>"


class JourneyStepExecution(Base):
    """
    Record of a journey step being executed for an enrollment.

    Provides audit trail and analytics for journey performance.
    """
    __tablename__ = "cs_journey_step_executions"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, ForeignKey("cs_journey_enrollments.id"), nullable=False, index=True)
    step_id = Column(Integer, ForeignKey("cs_journey_steps.id"), nullable=False, index=True)

    # Execution status
    status = Column(
        SQLEnum(
            'pending', 'in_progress', 'completed', 'skipped', 'failed', 'waiting',
            name='cs_step_execution_status_enum'
        ),
        default='pending'
    )

    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    scheduled_for = Column(DateTime(timezone=True))  # For wait steps

    # Outcome
    outcome = Column(String(100))  # e.g., 'email_sent', 'task_created', 'condition_true'
    outcome_details = Column(JSON)

    # For condition steps
    condition_result = Column(Boolean)
    condition_evaluation = Column(JSON)  # Details of rule evaluation

    # For task steps
    task_id = Column(Integer, ForeignKey("cs_tasks.id"))

    # Error handling
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    enrollment = relationship("JourneyEnrollment", back_populates="step_executions")
    step = relationship("JourneyStep", back_populates="executions")

    def __repr__(self):
        return f"<JourneyStepExecution id={self.id} enrollment_id={self.enrollment_id} step_id={self.step_id} status={self.status}>"
