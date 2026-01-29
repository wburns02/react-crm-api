"""
Role Switching API Endpoints

Provides endpoints for the role-switching demo feature.
Only accessible to the demo user (will@macseptic.com).
"""

from fastapi import APIRouter, HTTPException, status
from datetime import datetime
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.schemas.role_view import (
    RoleViewResponse,
    RoleViewListResponse,
    RoleSwitchRequest,
    RoleSwitchResponse,
    CurrentRoleResponse,
    DemoModeStatusResponse,
)
from app.services.role_view_service import RoleViewService
from app.models.role_view import DEMO_USER_EMAIL

router = APIRouter()


@router.get("", response_model=RoleViewListResponse)
async def list_roles(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    List all available roles for role switching.

    Only returns roles if the user is the demo user (will@macseptic.com).
    Non-demo users get an empty list.
    """
    service = RoleViewService(db)
    is_demo = await service.is_demo_user(current_user)

    if not is_demo:
        return RoleViewListResponse(roles=[], current_role=None, is_demo_user=False)

    # Initialize demo mode (creates default roles if needed)
    await service.initialize_demo_mode(current_user)

    # Get all roles
    roles = await service.get_all_roles()

    # Get current role
    current_role = await service.get_current_role(current_user)
    current_role_key = current_role.role_key if current_role else "admin"

    return RoleViewListResponse(
        roles=[RoleViewResponse.model_validate(r) for r in roles], current_role=current_role_key, is_demo_user=True
    )


@router.post("/switch", response_model=RoleSwitchResponse)
async def switch_role(
    request: RoleSwitchRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Switch the current user's active role.

    Only available to demo users. Returns the new role configuration.
    """
    service = RoleViewService(db)

    # Verify demo user
    if not await service.is_demo_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Role switching is only available for demo users"
        )

    # Switch role
    success, message, role = await service.switch_role(current_user, request.role_key)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return RoleSwitchResponse(
        success=True, message=message, current_role=RoleViewResponse.model_validate(role), switched_at=datetime.utcnow()
    )


@router.get("/current", response_model=CurrentRoleResponse)
async def get_current_role(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Get the current user's active role configuration.

    Returns the role details including visible modules, quick actions, etc.
    """
    service = RoleViewService(db)
    is_demo = await service.is_demo_user(current_user)

    if not is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Role information is only available for demo users"
        )

    # Get current role
    role = await service.get_current_role(current_user)
    if not role:
        # Initialize and get default role
        role = await service.initialize_demo_mode(current_user)

    # Get session for switched_at timestamp
    session = await service.get_current_role_session(current_user.id)

    return CurrentRoleResponse(
        role=RoleViewResponse.model_validate(role),
        is_demo_user=True,
        user_email=current_user.email,
        switched_at=session.switched_at if session else None,
    )


@router.get("/status", response_model=DemoModeStatusResponse)
async def get_demo_status(
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Check if the current user is in demo mode.

    Returns demo mode status and available roles if applicable.
    """
    service = RoleViewService(db)
    is_demo = await service.is_demo_user(current_user)

    if not is_demo:
        return DemoModeStatusResponse(is_demo_mode=False, demo_user_email=None, available_roles=None, current_role=None)

    # Get roles and current role
    roles = await service.get_all_roles()
    current_role = await service.get_current_role(current_user)

    return DemoModeStatusResponse(
        is_demo_mode=True,
        demo_user_email=DEMO_USER_EMAIL,
        available_roles=[r.role_key for r in roles],
        current_role=current_role.role_key if current_role else "admin",
    )
