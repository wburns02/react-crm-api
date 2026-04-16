from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class HrWorkflowTemplate(Base):
    __tablename__ = "hr_workflow_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(200), nullable=False)
    category = Column(String(32), nullable=False)  # onboarding | offboarding | recruiting | operational
    version = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    tasks = relationship(
        "HrWorkflowTemplateTask",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="HrWorkflowTemplateTask.position",
    )


class HrWorkflowTemplateTask(Base):
    __tablename__ = "hr_workflow_template_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    position = Column(Integer, nullable=False)
    stage = Column(String(64), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    kind = Column(String(32), nullable=False)  # form_sign | document_upload | training_video | verify | assignment | manual
    assignee_role = Column(String(32), nullable=False)
    due_offset_days = Column(Integer, default=0, nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    config = Column(JSON, default=dict)

    template = relationship("HrWorkflowTemplate", back_populates="tasks")


class HrWorkflowTemplateDependency(Base):
    __tablename__ = "hr_workflow_template_dependencies"

    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_template_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class HrWorkflowInstance(Base):
    __tablename__ = "hr_workflow_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    template_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_workflow_templates.id"), nullable=False
    )
    template_version = Column(Integer, nullable=False)
    subject_type = Column(String(32), nullable=False)  # employee | applicant | truck | customer
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(16), default="active", nullable=False)
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    started_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)

    tasks = relationship(
        "HrWorkflowTask",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="HrWorkflowTask.position",
    )


class HrWorkflowTask(Base):
    __tablename__ = "hr_workflow_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    template_task_id = Column(
        UUID(as_uuid=True), ForeignKey("hr_workflow_template_tasks.id"), nullable=True
    )
    position = Column(Integer, nullable=False)
    stage = Column(String(64), nullable=True)
    name = Column(String(200), nullable=False)
    kind = Column(String(32), nullable=False)
    # Integer FK api_users.id.  NULL for subject-based roles (hire / employee);
    # the UI derives the subject from (assignee_role, instance.subject_id).
    assignee_user_id = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    # For subject-based roles we persist the subject's UUID so callers can render
    # "who is this assigned to" without joining through the instance.
    assignee_subject_id = Column(UUID(as_uuid=True), nullable=True)
    assignee_role = Column(String(32), nullable=False)
    status = Column(String(16), default="blocked", nullable=False)  # blocked|ready|in_progress|completed|skipped
    due_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    completed_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    config = Column(JSON, default=dict)
    result = Column(JSON, default=dict)

    instance = relationship("HrWorkflowInstance", back_populates="tasks")
    dependencies = relationship(
        "HrWorkflowTaskDependency",
        foreign_keys="HrWorkflowTaskDependency.task_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_hr_workflow_tasks_instance_status", "instance_id", "status"),
        Index("ix_hr_workflow_tasks_assignee_open", "assignee_user_id", "status"),
    )


class HrWorkflowTaskDependency(Base):
    __tablename__ = "hr_workflow_task_dependencies"

    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    depends_on_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class HrWorkflowTaskComment(Base):
    __tablename__ = "hr_workflow_task_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(Integer, ForeignKey("api_users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class HrWorkflowTaskAttachment(Base):
    __tablename__ = "hr_workflow_task_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("hr_workflow_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key = Column(String(512), nullable=False)
    filename = Column(String(256), nullable=False)
    mime_type = Column(String(128), nullable=True)
    size = Column(Integer, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("api_users.id"), nullable=True)
    uploaded_at = Column(DateTime, server_default=func.now(), nullable=False)
