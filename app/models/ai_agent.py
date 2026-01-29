"""AI Agent models for autonomous customer engagement."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AIAgent(Base):
    """AI Agent definition and configuration."""

    __tablename__ = "ai_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Agent identification
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    agent_type = Column(String(50), nullable=False, index=True)
    # Types: lead_qualification, customer_support, scheduling, follow_up

    # System prompt and behavior
    system_prompt = Column(Text, nullable=False)
    personality = Column(String(50), default="professional")  # professional, friendly, formal

    # Available tools/actions
    allowed_tools = Column(JSON, nullable=True)
    # Example: ["send_sms", "send_email", "create_task", "update_customer", "schedule_appointment"]

    # Trigger conditions
    trigger_type = Column(String(50), nullable=False)  # event, schedule, manual
    trigger_config = Column(JSON, nullable=True)
    # Event example: {"event": "new_lead", "conditions": {"source": "website"}}
    # Schedule example: {"cron": "0 9 * * *"}  # Daily at 9am

    # Rate limiting
    max_messages_per_day = Column(Integer, default=100)
    max_messages_per_customer = Column(Integer, default=5)
    cool_down_hours = Column(Integer, default=24)

    # Escalation rules
    escalation_config = Column(JSON, nullable=True)
    # Example: {"after_messages": 3, "on_keywords": ["angry", "cancel"], "to": "human"}

    # Status
    is_active = Column(Boolean, default=True)

    # Metrics
    total_conversations = Column(Integer, default=0)
    total_messages_sent = Column(Integer, default=0)
    success_rate = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<AIAgent {self.code} - {self.agent_type}>"


class AgentConversation(Base):
    """Agent conversation with a customer."""

    __tablename__ = "agent_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # References
    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    customer_id = Column(Integer, nullable=False, index=True)

    # Conversation state
    status = Column(String(30), default="active", index=True)
    # active, paused, escalated, completed, abandoned

    # Context
    context = Column(JSON, nullable=True)  # Accumulated context from conversation
    goal = Column(String(255), nullable=True)  # Current goal
    goal_achieved = Column(Boolean, default=False)

    # Channel
    channel = Column(String(20), nullable=False)  # sms, email, chat

    # Escalation
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to = Column(String(100), nullable=True)
    escalation_reason = Column(Text, nullable=True)

    # Metrics
    message_count = Column(Integer, default=0)
    customer_sentiment = Column(String(20), nullable=True)
    last_sentiment_score = Column(Float, nullable=True)

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AgentConversation {self.id} - {self.status}>"


class AgentMessage(Base):
    """Individual message in agent conversation."""

    __tablename__ = "agent_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    conversation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Message details
    role = Column(String(20), nullable=False)  # agent, customer
    content = Column(Text, nullable=False)
    channel = Column(String(20), nullable=False)  # sms, email

    # Delivery status
    delivery_status = Column(String(20), default="pending")  # pending, sent, delivered, failed
    external_id = Column(String(100), nullable=True)  # Twilio SID, etc.

    # AI reasoning (for agent messages)
    reasoning = Column(Text, nullable=True)  # Why the agent said this
    tools_used = Column(JSON, nullable=True)  # Tools invoked

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<AgentMessage {self.role}: {self.content[:50]}>"


class AgentTask(Base):
    """Task created by AI agent."""

    __tablename__ = "agent_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # References
    agent_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    customer_id = Column(Integer, nullable=False, index=True)

    # Task details
    task_type = Column(String(50), nullable=False)  # follow_up_call, send_quote, schedule_service
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(20), default="normal")

    # Assignment
    assigned_to = Column(String(100), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(20), default="pending")  # pending, completed, cancelled
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AgentTask {self.task_type} - {self.status}>"
