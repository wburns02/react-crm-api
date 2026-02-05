"""Activity schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

from app.schemas.types import UUIDStr


ActivityType = Literal["call", "email", "sms", "note", "meeting", "task"]


class ActivityBase(BaseModel):
    """Base activity schema."""

    customer_id: UUIDStr = Field(..., description="Customer ID")
    activity_type: ActivityType
    description: str = Field(..., min_length=1)
    activity_date: Optional[str] = None


class ActivityCreate(ActivityBase):
    """Schema for creating an activity."""

    pass


class ActivityUpdate(BaseModel):
    """Schema for updating an activity (all fields optional)."""

    activity_type: Optional[ActivityType] = None
    description: Optional[str] = Field(None, min_length=1)
    activity_date: Optional[str] = None


class ActivityResponse(ActivityBase):
    """Schema for activity response."""

    id: UUIDStr
    created_by: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class ActivityListResponse(BaseModel):
    """Paginated activity list response."""

    items: list[ActivityResponse]
    total: int
    page: int
    page_size: int
