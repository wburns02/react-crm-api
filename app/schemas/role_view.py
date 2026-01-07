"""
Pydantic Schemas for Role View / Demo Mode

Defines the API request/response schemas for role switching functionality.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime


RoleKey = Literal[
    "admin",
    "executive",
    "manager",
    "technician",
    "phone_agent",
    "dispatcher",
    "billing"
]


class RoleViewBase(BaseModel):
    """Base schema for role view."""
    role_key: RoleKey
    display_name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class RoleViewResponse(RoleViewBase):
    """Response schema for a role view."""
    id: int
    visible_modules: List[str] = []
    default_route: str = "/"
    dashboard_widgets: List[str] = []
    quick_actions: List[str] = []
    features: Dict[str, Any] = {}
    is_active: bool = True
    sort_order: int = 0

    class Config:
        from_attributes = True


class RoleViewListResponse(BaseModel):
    """Response schema for list of available roles."""
    roles: List[RoleViewResponse]
    current_role: Optional[RoleKey] = None
    is_demo_user: bool = False


class RoleSwitchRequest(BaseModel):
    """Request schema for switching roles."""
    role_key: RoleKey = Field(..., description="The role key to switch to")


class RoleSwitchResponse(BaseModel):
    """Response schema after switching roles."""
    success: bool = True
    message: str
    current_role: RoleViewResponse
    switched_at: datetime


class CurrentRoleResponse(BaseModel):
    """Response schema for current role info."""
    role: RoleViewResponse
    is_demo_user: bool
    user_email: str
    switched_at: Optional[datetime] = None


class DemoModeStatusResponse(BaseModel):
    """Response schema for demo mode status check."""
    is_demo_mode: bool
    demo_user_email: Optional[str] = None
    available_roles: Optional[List[str]] = None
    current_role: Optional[str] = None
