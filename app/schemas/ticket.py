"""Ticket schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal

from app.schemas.types import UUIDStr


TicketStatus = Literal["open", "in_progress", "resolved", "closed"]
TicketPriority = Literal["low", "medium", "high", "urgent"]
TicketType = Literal["bug", "feature", "support", "task"]


class TicketCreate(BaseModel):
    """Schema for creating a ticket."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    type: TicketType = "feature"
    status: Optional[TicketStatus] = "open"
    priority: Optional[TicketPriority] = "medium"
    assigned_to: Optional[str] = None

    # RICE scoring (optional)
    reach: Optional[float] = Field(None, ge=0, le=10)
    impact: Optional[float] = Field(None, ge=0, le=10)
    confidence: Optional[float] = Field(None, ge=0, le=100)
    effort: Optional[float] = Field(None, ge=0.1)

    # Optional links
    customer_id: Optional[UUIDStr] = None
    work_order_id: Optional[UUIDStr] = None


class TicketUpdate(BaseModel):
    """Schema for updating a ticket (all fields optional)."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    type: Optional[TicketType] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None

    # RICE scoring
    reach: Optional[float] = Field(None, ge=0, le=10)
    impact: Optional[float] = Field(None, ge=0, le=10)
    confidence: Optional[float] = Field(None, ge=0, le=100)
    effort: Optional[float] = Field(None, ge=0.1)


class TicketResponse(BaseModel):
    """Schema for ticket response."""

    id: UUIDStr
    title: str
    description: str
    type: Optional[str] = None
    status: str
    priority: str
    rice_score: Optional[float] = None
    reach: Optional[float] = None
    impact: Optional[float] = None
    confidence: Optional[float] = None
    effort: Optional[float] = None
    assigned_to: Optional[str] = None
    resolved_at: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class TicketListResponse(BaseModel):
    """Paginated ticket list response."""

    items: list[TicketResponse]
    total: int
    page: int
    page_size: int
