"""AI Embedding model for vector storage and semantic search.

Uses pgvector extension for PostgreSQL to store and search embeddings.
"""
from sqlalchemy import Column, String, DateTime, Text, Integer, Index, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.database import Base


class AIEmbedding(Base):
    """Store embeddings for semantic search across CRM entities."""

    __tablename__ = "ai_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Source entity reference
    entity_type = Column(String(50), nullable=False, index=True)  # customer, work_order, ticket, note, etc.
    entity_id = Column(String(36), nullable=False, index=True)  # UUID or int as string

    # Content that was embedded
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default="text")  # text, call_transcript, email, note

    # Embedding vector (stored as JSON for SQLite test compatibility - pgvector for production)
    embedding = Column(JSON, nullable=True)  # Placeholder - real impl uses pgvector
    embedding_model = Column(String(100), default="bge-large-en-v1.5")
    embedding_dimensions = Column(Integer, default=1024)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Composite index for entity lookups
    __table_args__ = (
        Index('ix_ai_embeddings_entity', 'entity_type', 'entity_id'),
    )

    def __repr__(self):
        return f"<AIEmbedding {self.entity_type}:{self.entity_id}>"


class AIConversation(Base):
    """Store AI chat conversations for context and history."""

    __tablename__ = "ai_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # User who initiated the conversation
    user_id = Column(String(36), nullable=False, index=True)

    # Conversation context
    context_type = Column(String(50), nullable=True)  # customer, work_order, general
    context_id = Column(String(36), nullable=True)  # Related entity ID

    # Conversation title (auto-generated or user-set)
    title = Column(String(255), nullable=True)

    # Status
    status = Column(String(20), default="active")  # active, archived

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<AIConversation {self.id}>"


class AIMessage(Base):
    """Store individual messages in AI conversations."""

    __tablename__ = "ai_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Parent conversation
    conversation_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Token usage tracking
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AIMessage {self.role}:{self.id}>"
