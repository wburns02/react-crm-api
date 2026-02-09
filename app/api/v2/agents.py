"""AI Agents API - Autonomous customer engagement.

Features:
- Agent configuration and management
- Conversation tracking
- Message handling
- Task creation
- Escalation management
"""

from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.ai_agent import AIAgent, AgentConversation, AgentMessage, AgentTask
from app.models.customer import Customer
from app.services.ai_gateway import ai_gateway
from app.services.twilio_service import TwilioService
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models


class AgentCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    agent_type: str  # lead_qualification, customer_support, scheduling, follow_up
    system_prompt: str
    personality: str = "professional"
    allowed_tools: Optional[List[str]] = None
    trigger_type: str = "manual"
    trigger_config: Optional[dict] = None
    max_messages_per_day: int = 100
    max_messages_per_customer: int = 5
    escalation_config: Optional[dict] = None


class StartConversationRequest(BaseModel):
    agent_code: str
    customer_id: str
    channel: str = "sms"  # sms, email
    initial_context: Optional[dict] = None
    goal: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


# Helper functions


def agent_to_response(agent: AIAgent) -> dict:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "code": agent.code,
        "description": agent.description,
        "agent_type": agent.agent_type,
        "personality": agent.personality,
        "allowed_tools": agent.allowed_tools,
        "trigger_type": agent.trigger_type,
        "trigger_config": agent.trigger_config,
        "max_messages_per_day": agent.max_messages_per_day,
        "max_messages_per_customer": agent.max_messages_per_customer,
        "is_active": agent.is_active,
        "total_conversations": agent.total_conversations,
        "total_messages_sent": agent.total_messages_sent,
        "success_rate": agent.success_rate,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


def conversation_to_response(conv: AgentConversation) -> dict:
    return {
        "id": str(conv.id),
        "agent_id": str(conv.agent_id),
        "customer_id": str(conv.customer_id),
        "status": conv.status,
        "channel": conv.channel,
        "goal": conv.goal,
        "goal_achieved": conv.goal_achieved,
        "message_count": conv.message_count,
        "customer_sentiment": conv.customer_sentiment,
        "escalated_at": conv.escalated_at.isoformat() if conv.escalated_at else None,
        "escalated_to": conv.escalated_to,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
    }


# Agent Management Endpoints


@router.get("")
async def list_agents(
    db: DbSession,
    current_user: CurrentUser,
    agent_type: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    """List AI agents."""
    query = select(AIAgent)

    if agent_type:
        query = query.where(AIAgent.agent_type == agent_type)
    if is_active is not None:
        query = query.where(AIAgent.is_active == is_active)

    query = query.order_by(AIAgent.name)
    result = await db.execute(query)
    agents = result.scalars().all()

    return {"items": [agent_to_response(a) for a in agents]}


@router.post("")
async def create_agent(
    request: AgentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new AI agent."""
    existing = await db.execute(select(AIAgent).where(AIAgent.code == request.code))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent code '{request.code}' already exists",
        )

    agent = AIAgent(**request.model_dump())
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return agent_to_response(agent)


@router.get("/{agent_id}")
async def get_agent(
    agent_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get an agent by ID."""
    result = await db.execute(select(AIAgent).where(AIAgent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent_to_response(agent)


@router.patch("/{agent_id}/toggle")
async def toggle_agent(
    agent_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Toggle agent active status."""
    result = await db.execute(select(AIAgent).where(AIAgent.id == agent_id))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agent.is_active = not agent.is_active
    await db.commit()

    return {"is_active": agent.is_active}


# Conversation Endpoints


@router.post("/conversations")
async def start_conversation(
    request: StartConversationRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Start a new agent conversation with a customer."""
    # Get agent
    result = await db.execute(select(AIAgent).where(AIAgent.code == request.agent_code))
    agent = result.scalar_one_or_none()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{request.agent_code}' not found",
        )

    if not agent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is not active",
        )

    # Check for existing active conversation
    existing = await db.execute(
        select(AgentConversation).where(
            AgentConversation.agent_id == agent.id,
            AgentConversation.customer_id == request.customer_id,
            AgentConversation.status == "active",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active conversation already exists for this customer",
        )

    # Create conversation
    conversation = AgentConversation(
        agent_id=agent.id,
        customer_id=request.customer_id,
        channel=request.channel,
        context=request.initial_context,
        goal=request.goal,
        status="active",
    )
    db.add(conversation)

    # Update agent stats
    agent.total_conversations += 1

    await db.commit()
    await db.refresh(conversation)

    return conversation_to_response(conversation)


@router.get("/conversations")
async def list_conversations(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    agent_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List agent conversations."""
    query = select(AgentConversation)

    if agent_id:
        query = query.where(AgentConversation.agent_id == agent_id)
    if customer_id:
        query = query.where(AgentConversation.customer_id == customer_id)
    if status_filter:
        query = query.where(AgentConversation.status == status_filter)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(AgentConversation.started_at.desc())

    result = await db.execute(query)
    conversations = result.scalars().all()

    return {
        "items": [conversation_to_response(c) for c in conversations],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a conversation with messages."""
    conv_result = await db.execute(select(AgentConversation).where(AgentConversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Get messages
    msg_result = await db.execute(
        select(AgentMessage).where(AgentMessage.conversation_id == conversation_id).order_by(AgentMessage.created_at)
    )
    messages = msg_result.scalars().all()

    return {
        **conversation_to_response(conversation),
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "delivery_status": m.delivery_status,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.post("/conversations/{conversation_id}/messages")
async def send_agent_message(
    conversation_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send a message from the agent (manual override)."""
    conv_result = await db.execute(select(AgentConversation).where(AgentConversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Create message
    message = AgentMessage(
        conversation_id=conversation.id,
        role="agent",
        content=request.content,
        channel=conversation.channel,
        delivery_status="pending",
    )
    db.add(message)

    # Update conversation
    conversation.message_count += 1
    conversation.last_message_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)

    # Send via appropriate channel in background
    async def send_agent_message_async():
        from app.database import async_session
        async with async_session() as session:
            # Reload message
            msg_result = await session.execute(
                select(AgentMessage).where(AgentMessage.id == message.id)
            )
            msg = msg_result.scalar_one_or_none()
            if not msg:
                return

            # Get customer contact info
            conv_result2 = await session.execute(
                select(AgentConversation).where(AgentConversation.id == conversation_id)
            )
            conv = conv_result2.scalar_one_or_none()
            if not conv:
                return

            cust_result = await session.execute(
                select(Customer).where(Customer.id == conv.customer_id)
            )
            customer = cust_result.scalar_one_or_none()
            if not customer:
                msg.delivery_status = "failed"
                await session.commit()
                return

            try:
                if conv.channel == "sms" and customer.phone:
                    twilio = TwilioService()
                    await twilio.send_sms(customer.phone, msg.content)
                    msg.delivery_status = "sent"
                elif conv.channel == "email" and customer.email:
                    email_svc = EmailService()
                    await email_svc.send_email(
                        to_email=customer.email,
                        subject="Message from Mac Septic Services",
                        body=msg.content,
                    )
                    msg.delivery_status = "sent"
                else:
                    msg.delivery_status = "sent"  # chat channel — already displayed
            except Exception as e:
                logger.error(f"Failed to send agent message {message.id}: {e}")
                msg.delivery_status = "failed"

            await session.commit()

    background_tasks.add_task(send_agent_message_async)

    return {
        "message_id": str(message.id),
        "status": "queued",
    }


@router.post("/conversations/{conversation_id}/escalate")
async def escalate_conversation(
    conversation_id: str,
    reason: str = Query(...),
    assign_to: Optional[str] = None,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Escalate conversation to human."""
    conv_result = await db.execute(select(AgentConversation).where(AgentConversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.status = "escalated"
    conversation.escalated_at = datetime.utcnow()
    conversation.escalated_to = assign_to or current_user.email
    conversation.escalation_reason = reason

    await db.commit()

    return {"status": "escalated", "escalated_to": conversation.escalated_to}


@router.post("/conversations/{conversation_id}/complete")
async def complete_conversation(
    conversation_id: str,
    goal_achieved: bool = True,
    db: DbSession = None,
    current_user: CurrentUser = None,
):
    """Mark conversation as completed."""
    conv_result = await db.execute(select(AgentConversation).where(AgentConversation.id == conversation_id))
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    conversation.status = "completed"
    conversation.completed_at = datetime.utcnow()
    conversation.goal_achieved = goal_achieved

    await db.commit()

    return {"status": "completed", "goal_achieved": goal_achieved}


# Task Endpoints


@router.get("/tasks")
async def list_agent_tasks(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    assigned_to: Optional[str] = None,
):
    """List tasks created by agents."""
    query = select(AgentTask)

    if status_filter:
        query = query.where(AgentTask.status == status_filter)
    if assigned_to:
        query = query.where(AgentTask.assigned_to == assigned_to)

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(AgentTask.created_at.desc())

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "items": [
            {
                "id": str(t.id),
                "agent_id": str(t.agent_id),
                "customer_id": str(t.customer_id),
                "task_type": t.task_type,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "assigned_to": t.assigned_to,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.patch("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a task as completed."""
    result = await db.execute(select(AgentTask).where(AgentTask.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    task.status = "completed"
    task.completed_at = datetime.utcnow()
    task.completed_by = current_user.email

    await db.commit()

    return {"status": "completed"}
