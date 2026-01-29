"""Email Template Schemas

Pydantic schemas for email template API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class EmailTemplateBase(BaseModel):
    """Base schema for email templates."""

    name: str = Field(..., min_length=1, max_length=255, description="Template name")
    category: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Template category (scheduling, billing, service, marketing, general)",
    )
    subject: str = Field(..., min_length=1, max_length=255, description="Email subject with merge fields")
    body_html: str = Field(..., min_length=1, description="HTML body with merge fields")
    body_text: Optional[str] = Field(None, description="Plain text body with merge fields")
    variables: Optional[List[str]] = Field(
        default_factory=list, description="List of available merge field names"
    )
    is_active: bool = Field(default=True, description="Whether template is available for use")


class EmailTemplateCreate(EmailTemplateBase):
    """Schema for creating an email template."""

    pass


class EmailTemplateUpdate(BaseModel):
    """Schema for updating an email template."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    subject: Optional[str] = Field(None, min_length=1, max_length=255)
    body_html: Optional[str] = Field(None, min_length=1)
    body_text: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None


class EmailTemplateResponse(EmailTemplateBase):
    """Schema for email template response."""

    id: UUID
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmailTemplateListResponse(BaseModel):
    """Schema for paginated email template list."""

    items: List[EmailTemplateResponse]
    total: int
    page: int
    page_size: int


class EmailTemplatePreview(BaseModel):
    """Schema for template preview with rendered content."""

    subject: str
    body_html: str
    body_text: str


class EmailTemplateRenderRequest(BaseModel):
    """Schema for rendering a template with context data."""

    context: dict = Field(
        ...,
        description="Dictionary of merge field values",
        example={
            "customer_name": "John Smith",
            "scheduled_date": "2026-01-30",
            "scheduled_time": "10:00 AM",
        },
    )
