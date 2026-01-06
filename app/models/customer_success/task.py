"""
Task Model for Enterprise Customer Success Platform

Manages CS tasks generated from playbooks, journeys, or manually created.
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, Date,
    ForeignKey, Enum as SQLEnum, JSON
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class CSTask(Base):
    """
    Customer Success task.

    Tasks can be generated from:
    - Playbook steps
    - Journey steps
    - Manual creation
    - System alerts
    """
    __tablename__ = "cs_tasks"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)

    # Task origin
    playbook_execution_id = Column(Integer, ForeignKey("cs_playbook_executions.id"), index=True)
    playbook_step_id = Column(Integer, ForeignKey("cs_playbook_steps.id"))
    journey_enrollment_id = Column(Integer, ForeignKey("cs_journey_enrollments.id"), index=True)
    journey_step_id = Column(Integer, ForeignKey("cs_journey_steps.id"))

    # Task details
    title = Column(String(200), nullable=False)
    description = Column(Text)

    task_type = Column(
        SQLEnum(
            'call', 'email', 'meeting', 'internal', 'review',
            'escalation', 'follow_up', 'documentation', 'training',
            'product_demo', 'qbr', 'renewal', 'custom',
            name='cs_task_type_enum'
        ),
        default='custom'
    )

    # Category for filtering/reporting
    category = Column(
        SQLEnum(
            'onboarding', 'adoption', 'retention', 'expansion',
            'support', 'relationship', 'administrative',
            name='cs_task_category_enum'
        )
    )

    # Assignment
    assigned_to_user_id = Column(Integer, ForeignKey("api_users.id"), index=True)
    assigned_to_role = Column(String(50))
    assigned_by_user_id = Column(Integer, ForeignKey("api_users.id"))
    assigned_at = Column(DateTime(timezone=True))

    # Customer contact (who to reach out to)
    contact_name = Column(String(100))
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    contact_role = Column(String(100))

    # Priority and status
    priority = Column(
        SQLEnum('low', 'medium', 'high', 'critical', name='cs_task_priority_enum'),
        default='medium'
    )
    status = Column(
        SQLEnum('pending', 'in_progress', 'completed', 'cancelled', 'blocked', 'snoozed', name='cs_task_status_enum'),
        default='pending'
    )

    # Timing
    due_date = Column(Date)
    due_datetime = Column(DateTime(timezone=True))
    reminder_at = Column(DateTime(timezone=True))
    snoozed_until = Column(DateTime(timezone=True))

    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    cancelled_at = Column(DateTime(timezone=True))

    # Outcome
    outcome = Column(
        SQLEnum(
            'successful', 'unsuccessful', 'rescheduled', 'no_response',
            'voicemail', 'escalated', 'cancelled', 'not_applicable',
            name='cs_task_outcome_enum'
        )
    )
    outcome_notes = Column(Text)

    # Meeting/call details
    scheduled_datetime = Column(DateTime(timezone=True))
    meeting_link = Column(String(500))
    meeting_duration_minutes = Column(Integer)
    meeting_type = Column(String(50))  # 'zoom', 'teams', 'phone', 'in_person'

    # Email details
    email_template_id = Column(Integer)
    email_sent_at = Column(DateTime(timezone=True))
    email_opened_at = Column(DateTime(timezone=True))
    email_clicked_at = Column(DateTime(timezone=True))

    # Required artifacts
    required_artifacts = Column(JSON)  # ["meeting_notes", "action_items"]
    completed_artifacts = Column(JSON)  # {"meeting_notes": "...", "action_items": [...]}

    # Time tracking
    time_spent_minutes = Column(Integer, default=0)
    estimated_minutes = Column(Integer)

    # Dependencies
    depends_on_task_ids = Column(JSON)  # [task_id, task_id]
    blocks_task_ids = Column(JSON)

    # Recurrence
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50))  # 'daily', 'weekly', 'biweekly', 'monthly'
    recurrence_end_date = Column(Date)
    parent_task_id = Column(Integer, ForeignKey("cs_tasks.id"))

    # Templates
    instructions = Column(Text)
    talk_track = Column(Text)
    agenda = Column(Text)

    # Links
    related_url = Column(String(500))
    recording_url = Column(String(500))
    document_url = Column(String(500))

    # Metadata
    source = Column(String(100))  # 'playbook', 'journey', 'manual', 'alert', 'integration'
    tags = Column(JSON)  # ["urgent", "renewal", "vip"]
    task_data = Column(JSON)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    customer = relationship("Customer", backref="cs_tasks")
    playbook_execution = relationship("PlaybookExecution", back_populates="tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id], backref="assigned_cs_tasks")
    parent_task = relationship("CSTask", remote_side=[id], backref="child_tasks")
    touchpoints = relationship("Touchpoint", back_populates="task")

    def __repr__(self):
        return f"<CSTask id={self.id} title='{self.title[:30]}...' status={self.status} priority={self.priority}>"
