"""AI API - Local GPU-powered AI features.

Endpoints for:
- Chat completion (LLM)
- Embeddings generation
- Semantic search
- Audio transcription
- Text summarization
- Sentiment analysis
"""
from fastapi import APIRouter, HTTPException, status, Query, Body
from sqlalchemy import select, func, text
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

from app.api.deps import DbSession, CurrentUser
from app.services.ai_gateway import ai_gateway, AIGateway
from app.models.ai_embedding import AIEmbedding, AIConversation, AIMessage

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
            conv_result = await db.execute(
                select(AIConversation).where(AIConversation.id == request.conversation_id)
            )
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
            query = select(AIEmbedding).where(
                AIEmbedding.content.ilike(f"%{request.query}%")
            )

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
    query = select(AIConversation).where(
        AIConversation.user_id == str(current_user.id)
    ).order_by(AIConversation.updated_at.desc())

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
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation_id)
        .order_by(AIMessage.created_at)
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


# AI Dispatch Stats endpoint
class DispatchStats(BaseModel):
    total_dispatches: int = 0
    ai_assisted: int = 0
    manual: int = 0
    optimization_score: float = 0.0


@router.get("/dispatch/stats")
async def get_dispatch_stats(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get AI dispatch statistics."""
    # TODO: Implement with actual dispatch data
    # For now return placeholder to prevent 404
    return DispatchStats(
        total_dispatches=0,
        ai_assisted=0,
        manual=0,
        optimization_score=0.0,
    )
