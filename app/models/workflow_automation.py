from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from uuid import uuid4
from app.database import Base


class WorkflowAutomation(Base):
    __tablename__ = "workflow_automations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("company_entities.id"), nullable=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    trigger_type = Column(String(50), nullable=False)
    trigger_config = Column(JSON, default=dict)
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)
    status = Column(String(20), default="draft")
    run_count = Column(Integer, default=0)
    last_run_at = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("api_users.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflow_automations.id", ondelete="CASCADE"))
    trigger_event = Column(JSON, nullable=True)
    steps_executed = Column(JSON, default=list)
    status = Column(String(20), default="running")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)
