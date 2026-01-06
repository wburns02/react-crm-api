"""
Playbook Models for Enterprise Customer Success Platform

Defines repeatable, best-practice workflows for common CS scenarios
like onboarding, risk response, renewal, and expansion.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class Playbook(Base):
    """
    Playbook definition - a codified best-practice workflow.

    Playbooks are triggered by specific conditions and create
    a series of tasks for CSMs to execute.
    """
    __tablename__ = "cs_playbooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Playbook category
    category = Column(
        SQLEnum(
            'onboarding', 'adoption', 'renewal', 'churn_risk',
            'expansion', 'escalation', 'qbr', 'executive_sponsor',
            'champion_change', 'implementation', 'training', 'custom',
            name='cs_playbook_category_enum'
        ),
        default='custom'
    )

    # Trigger conditions
    trigger_type = Column(
        SQLEnum(
            'manual', 'health_threshold', 'segment_entry', 'event',
            'days_to_renewal', 'scheduled',
            name='cs_playbook_trigger_enum'
        ),
        default='manual'
    )

    # Health-based trigger
    trigger_health_threshold = Column(Integer)  # Trigger when health drops below
    trigger_health_direction = Column(String(10))  # 'below', 'above'

    # Time-based trigger
    trigger_days_to_renewal = Column(Integer)

    # Event-based trigger
    trigger_event = Column(String(100))

    # Segment-based trigger
    trigger_segment_id = Column(Integer, ForeignKey("cs_segments.id"))

    # Trigger configuration (JSON for complex conditions)
    trigger_config = Column(JSON)

    # Playbook settings
    priority = Column(
        SQLEnum('low', 'medium', 'high', 'critical', name='cs_playbook_priority_enum'),
        default='medium'
    )
    is_active = Column(Boolean, default=True)

    # Assignment
    auto_assign = Column(Boolean, default=True)
    default_assignee_role = Column(String(50))  # 'csm', 'manager', 'executive'
    escalation_assignee_role = Column(String(50))

    # Timing
    estimated_hours = Column(Float)
    target_completion_days = Column(Integer)

    # Success criteria (JSON)
    success_criteria = Column(JSON)
    # Example: {"health_score_increase": 15, "meeting_held": true}

    # Settings
    allow_parallel_execution = Column(Boolean, default=False)
    max_active_per_customer = Column(Integer, default=1)
    cooldown_days = Column(Integer)  # Min days between executions for same customer

    # Metrics (auto-updated)
    times_triggered = Column(Integer, default=0)
    times_completed = Column(Integer, default=0)
    times_successful = Column(Integer, default=0)
    avg_completion_days = Column(Float)
    success_rate = Column(Float)

    # Ownership
    created_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    owned_by_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    steps = relationship("PlaybookStep", back_populates="playbook", order_by="PlaybookStep.step_order", cascade="all, delete-orphan")
    executions = relationship("PlaybookExecution", back_populates="playbook", cascade="all, delete-orphan")
    trigger_segment = relationship("Segment", back_populates="playbooks")

    def __repr__(self):
        return f"<Playbook id={self.id} name='{self.name}' category={self.category}>"


class PlaybookStep(Base):
    """
    Individual step within a playbook.

    Each step typically generates a task for the CSM.
    """
    __tablename__ = "cs_playbook_steps"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("cs_playbooks.id"), nullable=False, index=True)

    step_order = Column(Integer, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Step type
    step_type = Column(
        SQLEnum(
            'call', 'email', 'meeting', 'internal_task', 'product_demo',
            'training', 'review', 'escalation', 'documentation',
            'approval', 'notification', 'custom',
            name='cs_playbook_step_type_enum'
        ),
        nullable=False
    )

    # Assignee
    default_assignee_role = Column(String(50))  # 'csm', 'manager', 'executive', 'support'
    assignee_override_allowed = Column(Boolean, default=True)

    # Timing
    days_from_start = Column(Integer, default=0)  # Suggested start day
    due_days = Column(Integer)  # Days allowed to complete
    is_required = Column(Boolean, default=True)

    # Dependencies
    depends_on_step_ids = Column(JSON)  # [1, 2] - must complete these first
    blocks_step_ids = Column(JSON)  # [4, 5] - these wait for this

    # Templates and content
    email_template_id = Column(Integer)
    email_subject = Column(String(255))
    email_body_template = Column(Text)

    meeting_agenda_template = Column(Text)
    talk_track = Column(Text)
    instructions = Column(Text)

    # Required artifacts/outcomes
    required_artifacts = Column(JSON)  # ["meeting_notes", "action_items", "screenshot"]
    required_outcomes = Column(JSON)  # ["customer_agreed", "escalation_resolved"]

    # Completion criteria
    completion_type = Column(
        SQLEnum('manual', 'auto_email_sent', 'auto_meeting_scheduled', 'approval_received', name='cs_completion_type_enum'),
        default='manual'
    )

    # Settings
    is_active = Column(Boolean, default=True)
    skip_if_condition = Column(JSON)  # Skip if condition met

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    playbook = relationship("Playbook", back_populates="steps")

    def __repr__(self):
        return f"<PlaybookStep id={self.id} playbook_id={self.playbook_id} order={self.step_order} type={self.step_type}>"


class PlaybookExecution(Base):
    """
    Instance of a playbook being executed for a customer.

    Tracks progress through playbook steps and outcomes.
    """
    __tablename__ = "cs_playbook_executions"

    id = Column(Integer, primary_key=True, index=True)
    playbook_id = Column(Integer, ForeignKey("cs_playbooks.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Status
    status = Column(
        SQLEnum(
            'active', 'paused', 'completed', 'cancelled', 'failed',
            name='cs_playbook_exec_status_enum'
        ),
        default='active'
    )

    # Progress
    current_step_order = Column(Integer, default=1)
    steps_completed = Column(Integer, default=0)
    steps_total = Column(Integer)

    # Assignment
    assigned_to_user_id = Column(Integer, ForeignKey("api_users.id"))
    escalated_to_user_id = Column(Integer, ForeignKey("api_users.id"))

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    target_completion_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))

    # Trigger info
    triggered_by = Column(String(100))  # 'system:health_threshold', 'user:123', 'segment:5'
    trigger_reason = Column(Text)

    # Outcome
    outcome = Column(
        SQLEnum('successful', 'unsuccessful', 'partial', 'cancelled', name='cs_playbook_outcome_enum')
    )
    outcome_notes = Column(Text)

    # Success criteria evaluation
    success_criteria_met = Column(JSON)  # {"health_score_increase": true, "meeting_held": true}

    # Health tracking
    health_score_at_start = Column(Integer)
    health_score_at_end = Column(Integer)

    # Time tracking
    total_time_spent_minutes = Column(Integer, default=0)

    # Extra data
    extra_data = Column(JSON)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    playbook = relationship("Playbook", back_populates="executions")
    customer = relationship("Customer", backref="playbook_executions")
    tasks = relationship("CSTask", back_populates="playbook_execution")

    def __repr__(self):
        return f"<PlaybookExecution id={self.id} playbook_id={self.playbook_id} customer_id={self.customer_id} status={self.status}>"
