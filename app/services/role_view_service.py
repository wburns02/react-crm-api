"""
Role View Service

Business logic for role switching functionality in demo mode.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import Optional, List
import logging

from app.models.role_view import RoleView, UserRoleSession, DEMO_USER_EMAIL, DEFAULT_ROLES
from app.models.user import User

logger = logging.getLogger(__name__)


class RoleViewService:
    """Service class for role view operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_demo_user(self, user: User) -> bool:
        """Check if the user is the demo user."""
        return user.email.lower() == DEMO_USER_EMAIL.lower()

    async def ensure_default_roles_exist(self) -> None:
        """Ensure all default roles exist in the database."""
        for role_data in DEFAULT_ROLES:
            result = await self.db.execute(
                select(RoleView).where(RoleView.role_key == role_data["role_key"])
            )
            existing = result.scalar_one_or_none()

            if not existing:
                role = RoleView(**role_data)
                self.db.add(role)
                logger.info(f"Created default role: {role_data['role_key']}")

        await self.db.commit()

    async def get_all_roles(self) -> List[RoleView]:
        """Get all active roles ordered by sort_order."""
        result = await self.db.execute(
            select(RoleView)
            .where(RoleView.is_active == True)
            .order_by(RoleView.sort_order)
        )
        return list(result.scalars().all())

    async def get_role_by_key(self, role_key: str) -> Optional[RoleView]:
        """Get a specific role by its key."""
        result = await self.db.execute(
            select(RoleView).where(RoleView.role_key == role_key)
        )
        return result.scalar_one_or_none()

    async def get_current_role_session(self, user_id: int) -> Optional[UserRoleSession]:
        """Get the current role session for a user."""
        result = await self.db.execute(
            select(UserRoleSession)
            .where(UserRoleSession.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_current_role(self, user: User) -> Optional[RoleView]:
        """Get the current role for a user, defaulting to admin for demo users."""
        if not await self.is_demo_user(user):
            return None

        session = await self.get_current_role_session(user.id)
        if session:
            return await self.get_role_by_key(session.current_role_key)

        # Default to admin for demo user
        return await self.get_role_by_key("admin")

    async def switch_role(self, user: User, role_key: str) -> tuple[bool, str, Optional[RoleView]]:
        """
        Switch the user's current role.

        Returns:
            Tuple of (success, message, role)
        """
        # Verify user is demo user
        if not await self.is_demo_user(user):
            return False, "Role switching is only available for demo users", None

        # Verify role exists
        role = await self.get_role_by_key(role_key)
        if not role:
            return False, f"Role '{role_key}' not found", None

        if not role.is_active:
            return False, f"Role '{role_key}' is not active", None

        # Get or create session
        session = await self.get_current_role_session(user.id)

        if session:
            # Update existing session
            session.current_role_key = role_key
            from datetime import datetime
            session.switched_at = datetime.utcnow()
        else:
            # Create new session
            session = UserRoleSession(
                user_id=user.id,
                current_role_key=role_key
            )
            self.db.add(session)

        await self.db.commit()

        logger.info(f"User {user.email} switched to role: {role_key}")
        return True, f"Switched to {role.display_name}", role

    async def initialize_demo_mode(self, user: User) -> Optional[RoleView]:
        """
        Initialize demo mode for a user.
        Creates default roles if needed and sets up initial role session.
        """
        if not await self.is_demo_user(user):
            return None

        # Ensure default roles exist
        await self.ensure_default_roles_exist()

        # Get or create session with default admin role
        session = await self.get_current_role_session(user.id)
        if not session:
            session = UserRoleSession(
                user_id=user.id,
                current_role_key="admin"
            )
            self.db.add(session)
            await self.db.commit()

        return await self.get_role_by_key(session.current_role_key)
