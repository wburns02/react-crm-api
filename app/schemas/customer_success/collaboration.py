"""
Collaboration Hub Schemas for Enterprise Customer Success Platform
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class ResourceType(str, Enum):
    DOCUMENT = "document"
    VIDEO = "video"
    TEMPLATE = "template"
    CHECKLIST = "checklist"
    GUIDE = "guide"
    SCRIPT = "script"
    LINK = "link"


class ResourceCategory(str, Enum):
    ONBOARDING = "onboarding"
    TRAINING = "training"
    PLAYBOOKS = "playbooks"
    PROCESSES = "processes"
    BEST_PRACTICES = "best_practices"
    TEMPLATES = "templates"
    GENERAL = "general"


class Visibility(str, Enum):
    ALL = "all"
    TEAM = "team"
    MANAGERS = "managers"
    ADMINS = "admins"
    PRIVATE = "private"


# Resource Comment Schemas


class ResourceCommentBase(BaseModel):
    """Base resource comment schema."""

    content: str = Field(..., min_length=1)
    parent_comment_id: Optional[int] = None


class ResourceCommentCreate(ResourceCommentBase):
    """Schema for creating a comment."""

    pass


class ResourceCommentResponse(ResourceCommentBase):
    """Resource comment response."""

    id: int
    resource_id: int
    user_id: int
    user_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    replies: list["ResourceCommentResponse"] = []

    class Config:
        from_attributes = True


# Resource Schemas


class ResourceBase(BaseModel):
    """Base resource schema."""

    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    resource_type: ResourceType
    category: ResourceCategory = ResourceCategory.GENERAL
    content: Optional[str] = None
    content_html: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_featured: bool = False
    is_pinned: bool = False
    visibility: Visibility = Visibility.ALL
    version: str = "1.0"


class ResourceCreate(ResourceBase):
    """Schema for creating a resource."""

    pass


class ResourceUpdate(BaseModel):
    """Schema for updating a resource."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    category: Optional[ResourceCategory] = None
    content: Optional[str] = None
    content_html: Optional[str] = None
    url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_featured: Optional[bool] = None
    is_pinned: Optional[bool] = None
    is_active: Optional[bool] = None
    is_archived: Optional[bool] = None
    visibility: Optional[Visibility] = None
    version: Optional[str] = None


class ResourceResponse(ResourceBase):
    """Resource response schema."""

    id: int
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    views_count: int = 0
    likes_count: int = 0
    downloads_count: int = 0
    is_active: bool = True
    is_archived: bool = False
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None
    parent_resource_id: Optional[int] = None
    comments: list[ResourceCommentResponse] = []
    is_liked_by_current_user: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_viewed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResourceListResponse(BaseModel):
    """Paginated resource list response."""

    items: list[ResourceResponse]
    total: int
    page: int
    page_size: int


# Team Note Comment Schemas


class TeamNoteCommentBase(BaseModel):
    """Base team note comment schema."""

    content: str = Field(..., min_length=1)


class TeamNoteCommentCreate(TeamNoteCommentBase):
    """Schema for creating a note comment."""

    pass


class TeamNoteCommentResponse(TeamNoteCommentBase):
    """Team note comment response."""

    id: int
    note_id: int
    user_id: int
    user_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Team Note Schemas


class TeamNoteBase(BaseModel):
    """Base team note schema."""

    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    content_html: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    is_pinned: bool = False
    visibility: Visibility = Visibility.TEAM


class TeamNoteCreate(TeamNoteBase):
    """Schema for creating a note."""

    customer_id: Optional[str] = None


class TeamNoteUpdate(BaseModel):
    """Schema for updating a note."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[str] = None
    content_html: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    is_pinned: Optional[bool] = None
    visibility: Optional[Visibility] = None


class TeamNoteResponse(TeamNoteBase):
    """Team note response schema."""

    id: int
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    created_by_user_id: int
    created_by_name: Optional[str] = None
    comments: list[TeamNoteCommentResponse] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TeamNoteListResponse(BaseModel):
    """Paginated team note list response."""

    items: list[TeamNoteResponse]
    total: int
    page: int
    page_size: int


# Activity Schemas


class ActivityCreate(BaseModel):
    """Schema for creating an activity."""

    activity_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    activity_data: Optional[dict] = None
    customer_id: Optional[str] = None


class ActivityResponse(BaseModel):
    """Activity response schema."""

    id: int
    activity_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    activity_data: Optional[dict] = None
    user_id: int
    user_name: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ActivityListResponse(BaseModel):
    """Paginated activity list response."""

    items: list[ActivityResponse]
    total: int
    page: int
    page_size: int
