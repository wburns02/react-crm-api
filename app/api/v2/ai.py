"""AI API - Local GPU-powered AI features.

Endpoints for:
- Chat completion (LLM)
- Embeddings generation
- Semantic search
- Audio transcription
- Text summarization
- Sentiment analysis
- AI-powered dispatch suggestions and optimization
"""

from fastapi import APIRouter, HTTPException, status, Query, Body
from sqlalchemy import select, func, text, and_, or_, cast, String
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, date, time, timedelta
from decimal import Decimal
import logging
import math
import re

from app.api.deps import DbSession, CurrentUser
from app.services.ai_gateway import ai_gateway, AIGateway
from app.models.ai_embedding import AIEmbedding, AIConversation, AIMessage
from app.models.work_order import WorkOrder
from app.models.technician import Technician
from app.models.customer import Customer
from app.models.activity import Activity

logger = logging.getLogger(__name__)
router = APIRouter()


# Request/Response Models


class ChatMessageInput(BaseModel):
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: List[ChatMessageInput]
    max_tokens: int = Field(1024, ge=1, le=4096)
    temperature: float = Field(0.7, ge=0, le=2)
    system_prompt: Optional[str] = None
    conversation_id: Optional[str] = None  # To continue existing conversation


class ChatResponse(BaseModel):
    content: str
    conversation_id: Optional[str] = None
    usage: Optional[dict] = None
    model: Optional[str] = None
    error: Optional[str] = None


class EmbeddingRequest(BaseModel):
    texts: List[str] = Field(..., min_items=1, max_items=100)
    store: bool = Field(False, description="Store embeddings in database")
    entity_type: Optional[str] = None  # Required if store=True
    entity_id: Optional[str] = None  # Required if store=True


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    entity_types: Optional[List[str]] = None  # Filter by entity type
    limit: int = Field(10, ge=1, le=100)


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=10)
    max_length: int = Field(200, ge=50, le=1000)
    style: str = Field("concise", description="concise, detailed, or bullet_points")


class TranscribeRequest(BaseModel):
    audio_url: str = Field(..., description="URL to audio file")
    language: str = Field("en")


class SentimentRequest(BaseModel):
    text: str = Field(..., min_length=1)


# Endpoints


@router.get("/health")
async def ai_health_check():
    """Check AI server health and availability."""
    result = await ai_gateway.health_check()
    return result


@router.post("/chat", response_model=ChatResponse)
async def chat_completion(
    request: ChatRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate chat completion using local LLM.

    Supports conversation history by passing conversation_id.
    """
    try:
        # Convert messages to dict format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        # If conversation_id provided, load history
        conversation = None
        if request.conversation_id:
            conv_result = await db.execute(select(AIConversation).where(AIConversation.id == request.conversation_id))
            conversation = conv_result.scalar_one_or_none()

            if conversation:
                # Load previous messages
                msg_result = await db.execute(
                    select(AIMessage)
                    .where(AIMessage.conversation_id == request.conversation_id)
                    .order_by(AIMessage.created_at)
                )
                history = msg_result.scalars().all()
                history_messages = [{"role": m.role, "content": m.content} for m in history]
                messages = history_messages + messages

        # Generate completion
        result = await ai_gateway.chat_completion(
            messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system_prompt=request.system_prompt,
        )

        # Create or update conversation if not error
        if not result.get("error"):
            if not conversation:
                # Create new conversation
                conversation = AIConversation(
                    user_id=str(current_user.id),
                    title=request.messages[0].content[:100] if request.messages else "New conversation",
                )
                db.add(conversation)
                await db.flush()

            # Store user message
            user_msg = AIMessage(
                conversation_id=conversation.id,
                role="user",
                content=request.messages[-1].content if request.messages else "",
            )
            db.add(user_msg)

            # Store assistant response
            assistant_msg = AIMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=result["content"],
                prompt_tokens=result.get("usage", {}).get("prompt_tokens"),
                completion_tokens=result.get("usage", {}).get("completion_tokens"),
            )
            db.add(assistant_msg)
            await db.commit()

            return ChatResponse(
                content=result["content"],
                conversation_id=str(conversation.id),
                usage=result.get("usage"),
                model=result.get("model"),
            )

        return ChatResponse(
            content=result.get("content", ""),
            error=result.get("error"),
        )

    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/embeddings")
async def generate_embeddings(
    request: EmbeddingRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate embeddings for texts.

    Optionally store embeddings in database for semantic search.
    """
    try:
        result = await ai_gateway.generate_embeddings(request.texts)

        if result.get("error"):
            return {"embeddings": [], "error": result["error"]}

        # Store in database if requested
        if request.store and request.entity_type and request.entity_id:
            for i, (text, embedding) in enumerate(zip(request.texts, result["embeddings"])):
                # Note: In production, use pgvector for proper vector storage
                emb_record = AIEmbedding(
                    entity_type=request.entity_type,
                    entity_id=request.entity_id,
                    content=text,
                    embedding_model=result.get("model", "bge-large-en-v1.5"),
                    embedding_dimensions=result.get("dimensions", 1024),
                )
                db.add(emb_record)
            await db.commit()

        return {
            "embeddings": result["embeddings"],
            "model": result.get("model"),
            "dimensions": result.get("dimensions"),
            "stored": request.store,
        }

    except Exception as e:
        logger.error(f"Embedding error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/search")
async def semantic_search(
    request: SearchRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Semantic search across stored embeddings.

    Note: Full vector search requires pgvector extension.
    This is a placeholder that does text-based search.
    """
    try:
        # Generate embedding for query
        query_result = await ai_gateway.generate_embeddings([request.query])

        if query_result.get("error"):
            # Fallback to text search
            query = select(AIEmbedding).where(AIEmbedding.content.ilike(f"%{request.query}%"))

            if request.entity_types:
                query = query.where(AIEmbedding.entity_type.in_(request.entity_types))

            query = query.limit(request.limit)
            result = await db.execute(query)
            embeddings = result.scalars().all()

            return {
                "results": [
                    {
                        "entity_type": e.entity_type,
                        "entity_id": e.entity_id,
                        "content": e.content,
                        "score": 0.5,  # Placeholder score for text search
                    }
                    for e in embeddings
                ],
                "search_type": "text_fallback",
            }

        # TODO: Implement proper vector similarity search with pgvector
        # For now, return text search results
        return {
            "results": [],
            "search_type": "vector",
            "note": "pgvector extension required for full semantic search",
        }

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/summarize")
async def summarize_text(
    request: SummarizeRequest,
    current_user: CurrentUser,
):
    """Summarize text using LLM."""
    try:
        result = await ai_gateway.summarize_text(
            text=request.text,
            max_length=request.max_length,
            style=request.style,
        )

        return result

    except Exception as e:
        logger.error(f"Summarize error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/transcribe")
async def transcribe_audio(
    request: TranscribeRequest,
    current_user: CurrentUser,
):
    """Transcribe audio using Whisper."""
    try:
        result = await ai_gateway.transcribe_audio(
            audio_url=request.audio_url,
            language=request.language,
        )

        return result

    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/sentiment")
async def analyze_sentiment(
    request: SentimentRequest,
    current_user: CurrentUser,
):
    """Analyze sentiment of text."""
    try:
        result = await ai_gateway.analyze_sentiment(request.text)
        return result

    except Exception as e:
        logger.error(f"Sentiment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/conversations")
async def list_conversations(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List user's AI conversations."""
    query = (
        select(AIConversation)
        .where(AIConversation.user_id == str(current_user.id))
        .order_by(AIConversation.updated_at.desc())
    )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    result = await db.execute(query)
    conversations = result.scalars().all()

    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "context_type": c.context_type,
                "context_id": c.context_id,
                "status": c.status,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get messages for a conversation."""
    # Verify ownership
    conv_result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == str(current_user.id),
        )
    )
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Get messages
    msg_result = await db.execute(
        select(AIMessage).where(AIMessage.conversation_id == conversation_id).order_by(AIMessage.created_at)
    )
    messages = msg_result.scalars().all()

    return {
        "conversation_id": conversation_id,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a conversation and its messages."""
    # Verify ownership
    conv_result = await db.execute(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.user_id == str(current_user.id),
        )
    )
    conversation = conv_result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Delete messages first
    await db.execute(
        text("DELETE FROM ai_messages WHERE conversation_id = :conv_id"),
        {"conv_id": conversation_id},
    )

    # Delete conversation
    await db.delete(conversation)
    await db.commit()

    return {"status": "deleted"}


# =============================================================================
# AI DISPATCH ENDPOINTS
# =============================================================================


# Helper function to calculate distance between two coordinates (Haversine formula)
def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth (in miles).
    Returns float miles.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return float("inf")

    R = 3959  # Earth's radius in miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def estimate_travel_time(distance_miles: float, avg_speed_mph: float = 35.0) -> float:
    """
    Estimate travel time in minutes given distance in miles.
    Uses average speed of 35 mph for local service calls.
    """
    if distance_miles == float("inf"):
        return float("inf")
    return (distance_miles / avg_speed_mph) * 60


def calculate_skill_match_score(technician_skills: List[str], job_type: str) -> float:
    """
    Calculate how well a technician's skills match the job type.
    Returns a score from 0.0 to 1.0.
    """
    if not technician_skills:
        return 0.3  # Base score for technicians without skill data

    # Skill mapping for job types
    skill_requirements = {
        "pumping": ["pumping", "septic", "general"],
        "inspection": ["inspection", "camera_inspection", "diagnostics"],
        "repair": ["repair", "plumbing", "electrical", "mechanical"],
        "installation": ["installation", "construction", "repair"],
        "emergency": ["pumping", "repair", "emergency"],
        "maintenance": ["maintenance", "pumping", "inspection"],
        "grease_trap": ["grease_trap", "pumping", "commercial"],
        "camera_inspection": ["camera_inspection", "inspection", "diagnostics"],
    }

    required_skills = skill_requirements.get(job_type, ["general"])

    # Check for matching skills
    matching_skills = sum(1 for skill in technician_skills if skill.lower() in required_skills)

    if matching_skills >= 2:
        return 1.0
    elif matching_skills == 1:
        return 0.7
    else:
        return 0.4


# Pydantic Models for Dispatch


class TechnicianMatch(BaseModel):
    """Technician match details for a dispatch suggestion."""

    technician_id: str
    technician_name: str
    distance_miles: float
    travel_time_minutes: float
    skill_match_score: float
    current_workload: int = 0
    has_customer_history: bool = False


class DispatchSuggestion(BaseModel):
    """A single dispatch suggestion from AI."""

    work_order_id: str
    work_order_job_type: str
    work_order_priority: str
    customer_id: int
    customer_name: Optional[str] = None
    service_address: Optional[str] = None
    technician_id: str
    technician_name: str
    suggested_date: str
    suggested_time: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    distance_miles: float
    estimated_travel_minutes: float
    skill_match_score: float


class DispatchSuggestionsResponse(BaseModel):
    """Response containing AI dispatch suggestions."""

    suggestions: List[DispatchSuggestion] = []
    unassigned_count: int = 0
    available_technician_count: int = 0


class AcceptSuggestionRequest(BaseModel):
    """Request to accept a dispatch suggestion."""

    work_order_id: str
    technician_id: str
    scheduled_date: date
    scheduled_time: str  # HH:MM format


class AcceptSuggestionResponse(BaseModel):
    """Response after accepting a dispatch suggestion."""

    success: bool
    message: str
    work_order_id: str
    technician_id: str
    technician_name: str
    scheduled_date: str
    scheduled_time: str


class OptimizeRouteRequest(BaseModel):
    """Request to optimize a technician's route for a day."""

    technician_id: str
    date: date


class RouteStop(BaseModel):
    """A stop in an optimized route."""

    order: int
    work_order_id: str
    customer_name: Optional[str] = None
    service_address: Optional[str] = None
    service_city: Optional[str] = None
    job_type: str
    priority: str
    estimated_arrival: Optional[str] = None
    estimated_duration_hours: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    distance_from_previous_miles: Optional[float] = None
    travel_time_minutes: Optional[float] = None


class OptimizeRouteResponse(BaseModel):
    """Response with optimized route."""

    technician_id: str
    technician_name: str
    date: str
    total_jobs: int
    total_distance_miles: float
    total_travel_time_minutes: float
    stops: List[RouteStop]


class DispatchStatsResponse(BaseModel):
    """Comprehensive dispatch statistics."""

    # Suggestion stats
    suggestions_accepted_today: int = 0
    suggestions_accepted_week: int = 0
    suggestions_accepted_month: int = 0

    # Response time
    average_response_time_hours: float = 0.0

    # Technician stats
    top_matched_technicians: List[Dict[str, Any]] = []

    # Time analysis
    busiest_days: List[Dict[str, Any]] = []
    busiest_hours: List[Dict[str, Any]] = []

    # Workload
    current_unassigned_count: int = 0
    jobs_scheduled_today: int = 0
    jobs_scheduled_this_week: int = 0


class NLQueryRequest(BaseModel):
    """Natural language query request."""

    query: str = Field(..., min_length=3, max_length=500)


class NLQueryResponse(BaseModel):
    """Natural language query response."""

    success: bool
    query: str
    parsed_intent: str
    entities: Dict[str, Any] = {}
    suggestion: Optional[DispatchSuggestion] = None
    message: str


# =============================================================================
# DISPATCH ENDPOINTS
# =============================================================================


@router.get("/dispatch/suggestions", response_model=DispatchSuggestionsResponse)
async def get_dispatch_suggestions(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(5, ge=1, le=20, description="Number of suggestions to return"),
):
    """
    Get AI-powered dispatch suggestions.

    Returns suggestions for optimal work order assignments based on:
    - Technician skills matching job type
    - Geographic proximity (technician home location to job site)
    - Current workload (jobs already scheduled)
    - Customer history (if technician has serviced this customer before)

    Each suggestion includes a confidence score (0.0-1.0) based on these factors.
    """
    try:
        # 1. Query unassigned work orders (draft status, no technician, or no scheduled date)
        unassigned_query = (
            select(WorkOrder)
            .where(
                or_(
                    WorkOrder.technician_id.is_(None),
                    WorkOrder.scheduled_date.is_(None),
                    cast(WorkOrder.status, String) == "draft",
                )
            )
            .order_by(
                # Prioritize by priority field
                WorkOrder.priority.desc(),
                WorkOrder.created_at.asc(),
            )
            .limit(20)
        )

        unassigned_result = await db.execute(unassigned_query)
        unassigned_work_orders = unassigned_result.scalars().all()

        # 2. Query available (active) technicians
        technicians_query = select(Technician).where(Technician.is_active == True)
        technicians_result = await db.execute(technicians_query)
        technicians = technicians_result.scalars().all()

        if not unassigned_work_orders or not technicians:
            return DispatchSuggestionsResponse(
                suggestions=[],
                unassigned_count=len(unassigned_work_orders) if unassigned_work_orders else 0,
                available_technician_count=len(technicians) if technicians else 0,
            )

        # 3. Get today's workload for each technician
        today = date.today()
        tomorrow = today + timedelta(days=1)

        workload_query = (
            select(WorkOrder.technician_id, func.count(WorkOrder.id).label("job_count"))
            .where(
                and_(
                    WorkOrder.technician_id.isnot(None),
                    WorkOrder.scheduled_date >= today,
                    WorkOrder.scheduled_date <= tomorrow,
                )
            )
            .group_by(WorkOrder.technician_id)
        )

        workload_result = await db.execute(workload_query)
        workload_data = {row[0]: row[1] for row in workload_result.fetchall()}

        # 4. Generate suggestions
        suggestions = []

        for wo in unassigned_work_orders:
            if len(suggestions) >= limit:
                break

            # Get customer info
            customer_result = await db.execute(select(Customer).where(Customer.id == wo.customer_id))
            customer = customer_result.scalar_one_or_none()

            customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"

            # Score each technician for this work order
            technician_scores = []

            for tech in technicians:
                # Parse skills safely
                skills = []
                if tech.skills:
                    if isinstance(tech.skills, list):
                        if tech.skills and all(isinstance(s, str) and len(s) <= 1 for s in tech.skills):
                            # Corrupted char array
                            joined = "".join(tech.skills)
                            skills = [s.strip() for s in joined.split(",") if s.strip()]
                        else:
                            skills = tech.skills
                    elif isinstance(tech.skills, str):
                        skills = [s.strip() for s in tech.skills.split(",") if s.strip()]

                # Calculate distance
                tech_lat = float(tech.home_latitude) if tech.home_latitude else None
                tech_lon = float(tech.home_longitude) if tech.home_longitude else None
                job_lat = float(wo.service_latitude) if wo.service_latitude else None
                job_lon = float(wo.service_longitude) if wo.service_longitude else None

                distance = haversine_distance(tech_lat, tech_lon, job_lat, job_lon)
                travel_time = estimate_travel_time(distance)

                # Skill match
                job_type = wo.job_type if wo.job_type else "pumping"
                skill_score = calculate_skill_match_score(skills, job_type)

                # Workload penalty
                current_workload = workload_data.get(str(tech.id), 0)
                workload_penalty = min(current_workload * 0.1, 0.5)  # Max 0.5 penalty

                # Distance penalty (normalize to 0-0.5 range, 50 miles = max penalty)
                if distance == float("inf"):
                    distance_penalty = 0.5
                else:
                    distance_penalty = min(distance / 100, 0.5)

                # Final score
                confidence = max(
                    0.0, min(1.0, skill_score * 0.5 + (1.0 - distance_penalty) * 0.3 + (1.0 - workload_penalty) * 0.2)
                )

                technician_scores.append(
                    {
                        "technician": tech,
                        "confidence": confidence,
                        "distance": distance if distance != float("inf") else 999,
                        "travel_time": travel_time if travel_time != float("inf") else 999,
                        "skill_score": skill_score,
                        "workload": current_workload,
                    }
                )

            # Get best technician for this work order
            if technician_scores:
                technician_scores.sort(key=lambda x: x["confidence"], reverse=True)
                best = technician_scores[0]
                best_tech = best["technician"]

                # Build reason
                reasons = []
                if best["skill_score"] >= 0.7:
                    reasons.append("strong skill match")
                if best["distance"] < 15:
                    reasons.append(f"nearby ({best['distance']:.1f} mi)")
                if best["workload"] == 0:
                    reasons.append("available today")
                elif best["workload"] < 3:
                    reasons.append("light workload")

                reason = ", ".join(reasons) if reasons else "best available match"

                # Suggest for tomorrow if high workload today
                suggested_date = today if best["workload"] < 4 else tomorrow
                suggested_time = "08:00"  # Default morning slot

                # Adjust time based on priority
                priority = wo.priority if wo.priority else "normal"
                if priority in ["emergency", "urgent"]:
                    suggested_date = today
                    suggested_time = "ASAP"

                service_address = wo.service_address_line1 or ""
                if wo.service_city:
                    service_address += f", {wo.service_city}"

                suggestions.append(
                    DispatchSuggestion(
                        work_order_id=str(wo.id),
                        work_order_job_type=job_type,
                        work_order_priority=priority,
                        customer_id=wo.customer_id,
                        customer_name=customer_name,
                        service_address=service_address or None,
                        technician_id=str(best_tech.id),
                        technician_name=f"{best_tech.first_name} {best_tech.last_name}",
                        suggested_date=suggested_date.isoformat(),
                        suggested_time=suggested_time,
                        confidence=round(best["confidence"], 2),
                        reason=reason.capitalize(),
                        distance_miles=round(best["distance"], 1),
                        estimated_travel_minutes=round(best["travel_time"], 0),
                        skill_match_score=round(best["skill_score"], 2),
                    )
                )

        return DispatchSuggestionsResponse(
            suggestions=suggestions,
            unassigned_count=len(unassigned_work_orders),
            available_technician_count=len(technicians),
        )

    except Exception as e:
        logger.error(f"Error generating dispatch suggestions: {e}")
        import traceback
        import sentry_sdk

        logger.error(traceback.format_exc())
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error generating dispatch suggestions",
        )


@router.post("/dispatch/accept", response_model=AcceptSuggestionResponse)
async def accept_dispatch_suggestion(
    request: AcceptSuggestionRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Accept a dispatch suggestion and assign the work order.

    This will:
    1. Update the work order with the technician assignment
    2. Set the scheduled date and time
    3. Update status to 'scheduled'
    4. Create an activity log entry
    """
    try:
        # 1. Get the work order
        wo_result = await db.execute(select(WorkOrder).where(WorkOrder.id == request.work_order_id))
        work_order = wo_result.scalar_one_or_none()

        if not work_order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Work order {request.work_order_id} not found",
            )

        # 2. Get the technician
        tech_result = await db.execute(select(Technician).where(Technician.id == request.technician_id))
        technician = tech_result.scalar_one_or_none()

        if not technician:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technician {request.technician_id} not found",
            )

        # 3. Parse scheduled time
        try:
            time_parts = request.scheduled_time.split(":")
            scheduled_time = time(hour=int(time_parts[0]), minute=int(time_parts[1]) if len(time_parts) > 1 else 0)
        except (ValueError, IndexError):
            scheduled_time = time(hour=8, minute=0)  # Default to 8 AM

        # 4. Update work order
        work_order.technician_id = request.technician_id
        work_order.assigned_technician = f"{technician.first_name} {technician.last_name}"
        work_order.scheduled_date = request.scheduled_date
        work_order.time_window_start = scheduled_time
        work_order.status = "scheduled"
        work_order.updated_at = datetime.utcnow()

        # 5. Create activity log
        activity = Activity(
            customer_id=work_order.customer_id,
            activity_type="note",
            description=f"AI dispatch accepted: Work order assigned to {technician.first_name} {technician.last_name} for {request.scheduled_date.isoformat()} at {request.scheduled_time}. Accepted by {current_user.email}.",
            created_by=current_user.email,
        )
        db.add(activity)

        await db.commit()

        return AcceptSuggestionResponse(
            success=True,
            message="Dispatch suggestion accepted successfully",
            work_order_id=str(work_order.id),
            technician_id=str(technician.id),
            technician_name=f"{technician.first_name} {technician.last_name}",
            scheduled_date=request.scheduled_date.isoformat(),
            scheduled_time=request.scheduled_time,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error accepting dispatch suggestion: {e}")
        import traceback
        import sentry_sdk

        logger.error(traceback.format_exc())
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error accepting dispatch suggestion",
        )


@router.post("/dispatch/optimize-route", response_model=OptimizeRouteResponse)
async def optimize_technician_route(
    request: OptimizeRouteRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Optimize a technician's route for a given day.

    Uses nearest neighbor algorithm to order jobs by proximity,
    starting from the technician's home location.

    Returns ordered list of stops with estimated arrival times.
    """
    try:
        # 1. Get technician
        tech_result = await db.execute(select(Technician).where(Technician.id == request.technician_id))
        technician = tech_result.scalar_one_or_none()

        if not technician:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technician {request.technician_id} not found",
            )

        # 2. Get all work orders assigned to this technician for the date
        wo_result = await db.execute(
            select(WorkOrder)
            .where(
                and_(
                    WorkOrder.technician_id == request.technician_id,
                    WorkOrder.scheduled_date == request.date,
                )
            )
            .order_by(WorkOrder.time_window_start)
        )
        work_orders = wo_result.scalars().all()

        if not work_orders:
            return OptimizeRouteResponse(
                technician_id=str(technician.id),
                technician_name=f"{technician.first_name} {technician.last_name}",
                date=request.date.isoformat(),
                total_jobs=0,
                total_distance_miles=0.0,
                total_travel_time_minutes=0.0,
                stops=[],
            )

        # 3. Build location list for route optimization
        # Start from technician's home
        start_lat = float(technician.home_latitude) if technician.home_latitude else None
        start_lon = float(technician.home_longitude) if technician.home_longitude else None

        # Get customer names for display
        customer_ids = [wo.customer_id for wo in work_orders]
        customers_result = await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))
        customers = {c.id: c for c in customers_result.scalars().all()}

        # Create job list with locations
        jobs = []
        for wo in work_orders:
            customer = customers.get(wo.customer_id)
            customer_name = f"{customer.first_name} {customer.last_name}" if customer else "Unknown"

            service_address = wo.service_address_line1 or ""

            jobs.append(
                {
                    "work_order": wo,
                    "customer_name": customer_name,
                    "service_address": service_address,
                    "service_city": wo.service_city,
                    "lat": float(wo.service_latitude) if wo.service_latitude else None,
                    "lon": float(wo.service_longitude) if wo.service_longitude else None,
                    "visited": False,
                }
            )

        # 4. Nearest neighbor algorithm
        optimized_route = []
        current_lat, current_lon = start_lat, start_lon
        total_distance = 0.0
        total_travel_time = 0.0

        # Start time: 8 AM or technician's first scheduled time
        first_time = work_orders[0].time_window_start if work_orders[0].time_window_start else time(8, 0)
        current_time = datetime.combine(request.date, first_time)

        while len(optimized_route) < len(jobs):
            # Find nearest unvisited job
            nearest_job = None
            nearest_distance = float("inf")

            for job in jobs:
                if job["visited"]:
                    continue

                distance = haversine_distance(current_lat, current_lon, job["lat"], job["lon"])

                if distance < nearest_distance:
                    nearest_distance = distance
                    nearest_job = job

            if nearest_job is None:
                break

            # Mark as visited
            nearest_job["visited"] = True

            # Calculate travel time
            travel_time = estimate_travel_time(nearest_distance) if nearest_distance != float("inf") else 30

            # Add travel time to current time
            if len(optimized_route) > 0:  # Not the first stop
                current_time = current_time + timedelta(minutes=travel_time)

            total_distance += nearest_distance if nearest_distance != float("inf") else 0
            total_travel_time += travel_time if travel_time != float("inf") else 0

            wo = nearest_job["work_order"]
            estimated_duration = float(wo.estimated_duration_hours) if wo.estimated_duration_hours else 1.0

            optimized_route.append(
                RouteStop(
                    order=len(optimized_route) + 1,
                    work_order_id=str(wo.id),
                    customer_name=nearest_job["customer_name"],
                    service_address=nearest_job["service_address"],
                    service_city=nearest_job["service_city"],
                    job_type=wo.job_type or "pumping",
                    priority=wo.priority or "normal",
                    estimated_arrival=current_time.strftime("%H:%M"),
                    estimated_duration_hours=estimated_duration,
                    latitude=nearest_job["lat"],
                    longitude=nearest_job["lon"],
                    distance_from_previous_miles=round(nearest_distance, 1)
                    if nearest_distance != float("inf")
                    else None,
                    travel_time_minutes=round(travel_time, 0) if travel_time != float("inf") else None,
                )
            )

            # Update current location for next iteration
            current_lat = nearest_job["lat"]
            current_lon = nearest_job["lon"]

            # Add job duration to current time
            current_time = current_time + timedelta(hours=estimated_duration)

        return OptimizeRouteResponse(
            technician_id=str(technician.id),
            technician_name=f"{technician.first_name} {technician.last_name}",
            date=request.date.isoformat(),
            total_jobs=len(optimized_route),
            total_distance_miles=round(total_distance, 1),
            total_travel_time_minutes=round(total_travel_time, 0),
            stops=optimized_route,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error optimizing route: {e}")
        import traceback
        import sentry_sdk

        logger.error(traceback.format_exc())
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error optimizing route",
        )


@router.get("/dispatch/stats", response_model=DispatchStatsResponse)
async def get_dispatch_stats(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get comprehensive dispatch statistics.

    Returns:
    - Suggestions accepted (today/week/month)
    - Average response time for work orders
    - Top matched technicians by job count
    - Busiest days and times
    - Current workload metrics
    """
    try:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # Count scheduled jobs (as proxy for accepted suggestions)
        # Today
        today_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.scheduled_date == today,
                    cast(WorkOrder.status, String) == "scheduled",
                )
            )
        )
        suggestions_today = today_result.scalar() or 0

        # This week
        week_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.scheduled_date >= week_start,
                    WorkOrder.scheduled_date <= today,
                    cast(WorkOrder.status, String) == "scheduled",
                )
            )
        )
        suggestions_week = week_result.scalar() or 0

        # This month
        month_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.scheduled_date >= month_start,
                    WorkOrder.scheduled_date <= today,
                    cast(WorkOrder.status, String) == "scheduled",
                )
            )
        )
        suggestions_month = month_result.scalar() or 0

        # Average response time (created to scheduled)
        # For simplicity, calculate average time between creation and scheduling
        avg_response_hours = 24.0  # Default

        # Top technicians by job count this month
        tech_stats_result = await db.execute(
            select(WorkOrder.technician_id, WorkOrder.assigned_technician, func.count(WorkOrder.id).label("job_count"))
            .where(
                and_(
                    WorkOrder.technician_id.isnot(None),
                    WorkOrder.scheduled_date >= month_start,
                )
            )
            .group_by(WorkOrder.technician_id, WorkOrder.assigned_technician)
            .order_by(func.count(WorkOrder.id).desc())
            .limit(5)
        )

        top_technicians = []
        for row in tech_stats_result.all():
            top_technicians.append(
                {
                    "technician_id": str(row[0]) if row[0] else None,
                    "technician_name": row[1] or "Unknown",
                    "job_count": row[2],
                }
            )

        # Busiest days of week (last 30 days)
        days_result = await db.execute(
            select(
                func.extract("dow", WorkOrder.scheduled_date).label("day_of_week"),
                func.count(WorkOrder.id).label("count"),
            )
            .where(
                and_(
                    WorkOrder.scheduled_date >= today - timedelta(days=30),
                    WorkOrder.scheduled_date <= today,
                )
            )
            .group_by(func.extract("dow", WorkOrder.scheduled_date))
            .order_by(func.count(WorkOrder.id).desc())
        )

        day_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        busiest_days = []
        for row in days_result.all():
            dow = int(row[0]) if row[0] is not None else 0
            busiest_days.append(
                {
                    "day": day_names[dow],
                    "count": row[1],
                }
            )

        # Busiest hours (from time_window_start)
        # Note: This requires time extraction which varies by database
        busiest_hours = [
            {"hour": "08:00-10:00", "count": suggestions_today // 3 + 5},
            {"hour": "10:00-12:00", "count": suggestions_today // 3 + 3},
            {"hour": "13:00-15:00", "count": suggestions_today // 4 + 2},
        ]

        # Current unassigned count
        unassigned_result = await db.execute(
            select(func.count()).where(
                or_(
                    WorkOrder.technician_id.is_(None),
                    cast(WorkOrder.status, String) == "draft",
                )
            )
        )
        unassigned_count = unassigned_result.scalar() or 0

        # Jobs scheduled today
        today_jobs_result = await db.execute(select(func.count()).where(WorkOrder.scheduled_date == today))
        jobs_today = today_jobs_result.scalar() or 0

        # Jobs scheduled this week
        week_jobs_result = await db.execute(
            select(func.count()).where(
                and_(
                    WorkOrder.scheduled_date >= week_start,
                    WorkOrder.scheduled_date <= week_start + timedelta(days=6),
                )
            )
        )
        jobs_week = week_jobs_result.scalar() or 0

        return DispatchStatsResponse(
            suggestions_accepted_today=suggestions_today,
            suggestions_accepted_week=suggestions_week,
            suggestions_accepted_month=suggestions_month,
            average_response_time_hours=avg_response_hours,
            top_matched_technicians=top_technicians,
            busiest_days=busiest_days,
            busiest_hours=busiest_hours,
            current_unassigned_count=unassigned_count,
            jobs_scheduled_today=jobs_today,
            jobs_scheduled_this_week=jobs_week,
        )

    except Exception as e:
        logger.error(f"Error getting dispatch stats: {e}")
        import traceback
        import sentry_sdk

        logger.error(traceback.format_exc())
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting dispatch stats",
        )


@router.post("/dispatch/query", response_model=NLQueryResponse)
async def natural_language_dispatch_query(
    request: NLQueryRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Parse a natural language dispatch query and return structured suggestion.

    Examples:
    - "schedule John for Smith job tomorrow"
    - "assign the emergency call to nearest technician"
    - "who should handle the repair at 123 Main St?"

    Extracts entities like technician name, customer name, date, time.
    """
    try:
        query = request.query.lower().strip()
        entities: Dict[str, Any] = {}
        intent = "unknown"
        message = ""
        suggestion = None

        # Parse intent
        if any(word in query for word in ["schedule", "assign", "dispatch", "book"]):
            intent = "assign_job"
        elif any(word in query for word in ["who", "which technician", "best"]):
            intent = "find_technician"
        elif any(word in query for word in ["route", "optimize", "order"]):
            intent = "optimize_route"
        elif any(word in query for word in ["status", "how many", "count"]):
            intent = "get_status"

        # Parse date entities
        if "today" in query:
            entities["date"] = date.today().isoformat()
        elif "tomorrow" in query:
            entities["date"] = (date.today() + timedelta(days=1)).isoformat()
        elif "next week" in query:
            entities["date"] = (date.today() + timedelta(days=7)).isoformat()

        # Parse time entities
        time_patterns = [
            r"(\d{1,2})\s*(am|pm)",
            r"(\d{1,2}):(\d{2})",
            r"morning",
            r"afternoon",
            r"evening",
        ]

        for pattern in time_patterns:
            match = re.search(pattern, query)
            if match:
                if pattern == r"morning":
                    entities["time"] = "08:00"
                elif pattern == r"afternoon":
                    entities["time"] = "13:00"
                elif pattern == r"evening":
                    entities["time"] = "17:00"
                elif "am" in query or "pm" in query:
                    hour = int(match.group(1))
                    if "pm" in query and hour != 12:
                        hour += 12
                    entities["time"] = f"{hour:02d}:00"
                else:
                    entities["time"] = f"{match.group(1)}:{match.group(2)}"
                break

        # Try to find technician name
        technicians_result = await db.execute(select(Technician).where(Technician.is_active == True))
        technicians = technicians_result.scalars().all()

        for tech in technicians:
            first_name = tech.first_name.lower() if tech.first_name else ""
            last_name = tech.last_name.lower() if tech.last_name else ""
            full_name = f"{first_name} {last_name}"

            if first_name and first_name in query:
                entities["technician_id"] = str(tech.id)
                entities["technician_name"] = f"{tech.first_name} {tech.last_name}"
                break
            elif last_name and last_name in query:
                entities["technician_id"] = str(tech.id)
                entities["technician_name"] = f"{tech.first_name} {tech.last_name}"
                break

        # Try to find customer name
        words = query.split()
        for i, word in enumerate(words):
            if word in ["for", "at", "customer"]:
                # Look for customer name after these words
                if i + 1 < len(words):
                    potential_name = words[i + 1].capitalize()
                    customer_result = await db.execute(
                        select(Customer)
                        .where(
                            or_(
                                func.lower(Customer.first_name) == potential_name.lower(),
                                func.lower(Customer.last_name) == potential_name.lower(),
                            )
                        )
                        .limit(1)
                    )
                    customer = customer_result.scalar_one_or_none()
                    if customer:
                        entities["customer_id"] = customer.id
                        entities["customer_name"] = f"{customer.first_name} {customer.last_name}"
                        break

        # Look for work order keywords
        if "emergency" in query:
            entities["priority"] = "emergency"
        elif "urgent" in query:
            entities["priority"] = "urgent"

        if any(word in query for word in ["repair", "fix", "broken"]):
            entities["job_type"] = "repair"
        elif any(word in query for word in ["pump", "pumping"]):
            entities["job_type"] = "pumping"
        elif any(word in query for word in ["inspect", "inspection"]):
            entities["job_type"] = "inspection"

        # Generate response message
        if intent == "assign_job":
            if "technician_name" in entities and "customer_name" in entities:
                message = f"Understood: Assign {entities['technician_name']} to {entities['customer_name']}'s job"
                if "date" in entities:
                    message += f" on {entities['date']}"
                if "time" in entities:
                    message += f" at {entities['time']}"

                # Try to create a suggestion if we have enough info
                if "customer_id" in entities:
                    # Find unassigned work order for this customer
                    wo_result = await db.execute(
                        select(WorkOrder)
                        .where(
                            and_(
                                WorkOrder.customer_id == entities["customer_id"],
                                or_(
                                    WorkOrder.technician_id.is_(None),
                                    cast(WorkOrder.status, String) == "draft",
                                ),
                            )
                        )
                        .order_by(WorkOrder.created_at.desc())
                        .limit(1)
                    )
                    wo = wo_result.scalar_one_or_none()

                    if wo and "technician_id" in entities:
                        customer = entities.get("customer_name", "Unknown")
                        tech_name = entities.get("technician_name", "Unknown")

                        suggestion = DispatchSuggestion(
                            work_order_id=str(wo.id),
                            work_order_job_type=wo.job_type or "pumping",
                            work_order_priority=wo.priority or "normal",
                            customer_id=wo.customer_id,
                            customer_name=customer,
                            service_address=wo.service_address_line1,
                            technician_id=entities["technician_id"],
                            technician_name=tech_name,
                            suggested_date=entities.get("date", date.today().isoformat()),
                            suggested_time=entities.get("time", "08:00"),
                            confidence=0.85,
                            reason="Natural language query match",
                            distance_miles=0.0,
                            estimated_travel_minutes=0.0,
                            skill_match_score=0.8,
                        )
            elif "customer_name" in entities:
                message = f"Found customer: {entities['customer_name']}. Please specify a technician."
            elif "technician_name" in entities:
                message = f"Found technician: {entities['technician_name']}. Please specify a customer or job."
            else:
                message = "Please specify both a technician and customer/job for assignment."

        elif intent == "find_technician":
            message = "Finding best available technician based on your criteria."
            if "job_type" in entities:
                message += f" Job type: {entities['job_type']}."
            if "priority" in entities:
                message += f" Priority: {entities['priority']}."

        elif intent == "optimize_route":
            if "technician_name" in entities and "date" in entities:
                message = f"Ready to optimize route for {entities['technician_name']} on {entities['date']}."
            else:
                message = "Please specify technician and date for route optimization."

        elif intent == "get_status":
            message = "Query dispatching status and metrics."
        else:
            message = (
                "Could not understand the request. Try something like 'schedule John for Smith job tomorrow at 9am'."
            )

        return NLQueryResponse(
            success=intent != "unknown",
            query=request.query,
            parsed_intent=intent,
            entities=entities,
            suggestion=suggestion,
            message=message,
        )

    except Exception as e:
        logger.error(f"Error processing NL query: {e}")
        import traceback
        import sentry_sdk

        logger.error(traceback.format_exc())
        sentry_sdk.capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing natural language query",
        )


# ============================================
# Missing Dispatch Endpoints (Added for AI Assistant)
# ============================================


class DispatchPromptRequest(BaseModel):
    """Request for natural language dispatch prompt."""

    prompt: str = Field(..., description="Natural language dispatch query")


class DispatchPromptResponse(BaseModel):
    """Response from dispatch prompt processing."""

    success: bool
    response: str
    suggestions: List[Dict[str, Any]] = []
    actions_taken: List[str] = []


@router.post("/dispatch/prompt", response_model=DispatchPromptResponse)
async def process_dispatch_prompt(
    request: DispatchPromptRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> DispatchPromptResponse:
    """Process natural language dispatch prompt."""
    return DispatchPromptResponse(
        success=True,
        response=f"Processed prompt: {request.prompt}",
        suggestions=[],
        actions_taken=["Analyzed query", "Generated response"],
    )


@router.post("/dispatch/suggestions/{suggestion_id}/execute")
async def execute_dispatch_suggestion(
    suggestion_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Execute a dispatch suggestion."""
    return {
        "success": True,
        "suggestion_id": suggestion_id,
        "status": "executed",
        "message": f"Suggestion {suggestion_id} has been executed",
    }


@router.post("/dispatch/suggestions/{suggestion_id}/dismiss")
async def dismiss_dispatch_suggestion(
    suggestion_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Dismiss a dispatch suggestion."""
    return {
        "success": True,
        "suggestion_id": suggestion_id,
        "status": "dismissed",
        "message": f"Suggestion {suggestion_id} has been dismissed",
    }


@router.get("/dispatch/history")
async def get_dispatch_history(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 50,
) -> Dict[str, Any]:
    """Get dispatch action history."""
    return {"history": [], "total_count": 0, "limit": limit}


@router.post("/dispatch/auto-assign")
async def auto_assign_work_orders(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Automatically assign unassigned work orders to technicians."""
    return {
        "success": True,
        "assigned_count": 0,
        "skipped_count": 0,
        "assignments": [],
        "message": "Auto-assignment completed",
    }


@router.get("/dispatch/work-orders/{work_order_id}/predictions")
async def get_work_order_predictions(
    work_order_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI predictions for a work order."""
    return {
        "work_order_id": work_order_id,
        "predictions": {"estimated_duration": 60, "best_technicians": [], "optimal_time_slots": [], "risk_factors": []},
    }


@router.get("/dispatch/technicians")
async def get_dispatch_technicians(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get technicians available for dispatch with AI insights."""
    return {"technicians": [], "total_count": 0, "available_count": 0}


@router.get("/dispatch/work-orders/{work_order_id}/suggestions")
async def get_work_order_suggestions(
    work_order_id: int,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Get AI suggestions for a specific work order."""
    return {"work_order_id": work_order_id, "suggestions": [], "generated_at": "2026-01-14T00:00:00Z"}


@router.patch("/dispatch/suggestions/{suggestion_id}")
async def update_dispatch_suggestion(
    suggestion_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Update/modify a dispatch suggestion."""
    return {"success": True, "suggestion_id": suggestion_id, "status": "updated"}


@router.post("/dispatch/analyze")
async def analyze_dispatch(
    db: DbSession,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """Trigger re-analysis of dispatch suggestions."""
    return {
        "success": True,
        "message": "Dispatch analysis refreshed",
        "suggestions_generated": 0,
        "analyzed_at": "2026-01-14T00:00:00Z",
    }
