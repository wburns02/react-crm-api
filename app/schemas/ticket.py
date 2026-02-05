"""Ticket schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal


TicketStatus = Literal["open", "in_progress", "pending", "resolved", "closed"]
TicketPriority = Literal["low", "normal", "high", "urgent"]
TicketCategory = Literal["complaint", "request", "inquiry", "feedback", "other"]


class TicketBase(BaseModel):
    """Base ticket schema."""

    customer_id: str = Field(..., description="Customer ID")
    work_order_id: Optional[str] = None
    subject: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    category: Optional[TicketCategory] = None
    status: Optional[TicketStatus] = "open"
    priority: Optional[TicketPriority] = "normal"
    assigned_to: Optional[str] = None


class TicketCreate(TicketBase):
    """Schema for creating a ticket."""

    pass


class TicketUpdate(BaseModel):
    """Schema for updating a ticket (all fields optional)."""

    subject: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    category: Optional[TicketCategory] = None
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None


class TicketResponse(BaseModel):
    """Schema for ticket response."""

    id: str
    customer_id: str
    work_order_id: Optional[str] = None
    subject: str
    description: str
    category: Optional[str] = None
    status: str
    priority: str
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
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
