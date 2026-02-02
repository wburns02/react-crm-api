"""
Role-Based Access Control (RBAC) Module

Provides authorization controls for high-risk endpoints.
"""

from enum import Enum
from typing import Set, Callable, Annotated, TYPE_CHECKING
from functools import wraps
from fastapi import HTTPException, status, Depends
import logging

if TYPE_CHECKING:
    from app.models.user import User

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """User roles."""

    USER = "user"
    ADMIN = "admin"
    SUPERUSER = "superuser"


class Permission(str, Enum):
    """Fine-grained permissions."""

    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    VIEW_CUSTOMERS = "view_customers"
    EDIT_CUSTOMERS = "edit_customers"
    DELETE_CUSTOMERS = "delete_customers"
    MANAGE_USERS = "manage_users"
    VIEW_ALL_COMMUNICATIONS = "view_all_communications"
    ADMIN_PANEL = "admin_panel"
    # Financial permissions
    MANAGE_PAYMENTS = "manage_payments"
    MANAGE_INVOICES = "manage_invoices"
    MANAGE_PAYROLL = "manage_payroll"
    APPROVE_PAYROLL = "approve_payroll"
    # Work order permissions
    MANAGE_WORK_ORDERS = "manage_work_orders"


# Role-to-permissions mapping
ROLE_PERMISSIONS: dict[Role, Set[Permission]] = {
    Role.USER: {
        Permission.SEND_SMS,
        Permission.SEND_EMAIL,
        Permission.VIEW_CUSTOMERS,
        Permission.EDIT_CUSTOMERS,
        Permission.MANAGE_WORK_ORDERS,
    },
    Role.ADMIN: {
        Permission.SEND_SMS,
        Permission.SEND_EMAIL,
        Permission.VIEW_CUSTOMERS,
        Permission.EDIT_CUSTOMERS,
        Permission.DELETE_CUSTOMERS,
        Permission.VIEW_ALL_COMMUNICATIONS,
        Permission.ADMIN_PANEL,
        Permission.MANAGE_PAYMENTS,
        Permission.MANAGE_INVOICES,
        Permission.MANAGE_PAYROLL,
        Permission.MANAGE_WORK_ORDERS,
    },
    Role.SUPERUSER: set(Permission),  # All permissions
}


def get_user_role(user: "User") -> Role:
    """Determine user's role from database flags."""
    if user.is_superuser:
        return Role.SUPERUSER
    # Check for admin flag if added to model, otherwise default to USER
    if getattr(user, "is_admin", False):
        return Role.ADMIN
    return Role.USER


def get_user_permissions(user: "User") -> Set[Permission]:
    """Get all permissions for a user based on their role."""
    role = get_user_role(user)
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(user: "User", permission: Permission) -> bool:
    """Check if user has a specific permission."""
    return permission in get_user_permissions(user)


def require_permission(permission: Permission):
    """
    Dependency factory for requiring a specific permission.

    Usage:
        @router.post("/admin/action")
        async def admin_action(
            current_user: CurrentUser,
            _: None = Depends(require_permission(Permission.ADMIN_PANEL))
        ):
            ...
    """
    from app.api.deps import get_current_active_user

    async def checker(current_user = Depends(get_current_active_user)) -> None:
        if not has_permission(current_user, permission):
            logger.warning(
                f"Permission denied: user {current_user.id} lacks {permission.value}",
                extra={"user_id": current_user.id, "permission": permission.value},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Permission denied: requires {permission.value}"
            )

    return checker


def get_require_admin():
    """Get the require_admin dependency (avoids circular import)."""
    from app.api.deps import get_current_active_user

    async def require_admin_check(current_user = Depends(get_current_active_user)) -> None:
        """Dependency for requiring admin or superuser role."""
        role = get_user_role(current_user)
        if role not in (Role.ADMIN, Role.SUPERUSER):
            logger.warning(
                f"Admin access denied for user {current_user.id}",
                extra={"user_id": current_user.id, "role": role.value}
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return require_admin_check


def get_require_superuser():
    """Get the require_superuser dependency (avoids circular import)."""
    from app.api.deps import get_current_active_user

    async def require_superuser_check(current_user = Depends(get_current_active_user)) -> None:
        """Dependency for requiring superuser role."""
        if not current_user.is_superuser:
            logger.warning(f"Superuser access denied for user {current_user.id}", extra={"user_id": current_user.id})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser access required")

    return require_superuser_check


# Pre-built dependencies for common use
require_admin = get_require_admin()
require_superuser = get_require_superuser()


class RBACChecker:
    """
    Class-based RBAC checker for more complex scenarios.

    Usage:
        rbac = RBACChecker(required_permissions=[Permission.SEND_SMS, Permission.VIEW_CUSTOMERS])

        @router.post("/endpoint")
        async def endpoint(current_user: CurrentUser, _: None = Depends(rbac)):
            ...
    """

    def __init__(
        self,
        required_permissions: list[Permission] = None,
        required_role: Role = None,
        any_permission: bool = False,  # True = OR logic, False = AND logic
    ):
        self.required_permissions = required_permissions or []
        self.required_role = required_role
        self.any_permission = any_permission

    async def __call__(self, current_user = Depends("app.api.deps.get_current_active_user")) -> None:
        from app.api.deps import get_current_active_user
        # Check role if specified
        if self.required_role:
            user_role = get_user_role(current_user)
            role_order = [Role.USER, Role.ADMIN, Role.SUPERUSER]
            if role_order.index(user_role) < role_order.index(self.required_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {self.required_role.value} role or higher"
                )

        # Check permissions if specified
        if self.required_permissions:
            user_perms = get_user_permissions(current_user)

            if self.any_permission:
                # OR logic: user needs at least one permission
                if not any(p in user_perms for p in self.required_permissions):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
            else:
                # AND logic: user needs all permissions
                missing = [p for p in self.required_permissions if p not in user_perms]
                if missing:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Missing permissions: {', '.join(p.value for p in missing)}",
                    )
