"""
Tests for the RBAC (Role-Based Access Control) module.
"""
import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException

from app.security.rbac import (
    Role, Permission, ROLE_PERMISSIONS,
    get_user_role, get_user_permissions, has_permission,
    require_permission, require_admin, require_superuser,
    RBACChecker
)


class TestRole:
    """Test Role enum."""

    def test_role_values(self):
        """Test role enum values."""
        assert Role.USER == "user"
        assert Role.ADMIN == "admin"
        assert Role.SUPERUSER == "superuser"


class TestPermission:
    """Test Permission enum."""

    def test_permission_values(self):
        """Test permission enum values."""
        assert Permission.SEND_SMS == "send_sms"
        assert Permission.MANAGE_USERS == "manage_users"
        assert Permission.ADMIN_PANEL == "admin_panel"


class TestRolePermissions:
    """Test role-to-permissions mapping."""

    def test_user_has_basic_permissions(self):
        """Test that USER role has basic permissions."""
        user_perms = ROLE_PERMISSIONS[Role.USER]
        assert Permission.SEND_SMS in user_perms
        assert Permission.VIEW_CUSTOMERS in user_perms
        assert Permission.ADMIN_PANEL not in user_perms

    def test_admin_has_elevated_permissions(self):
        """Test that ADMIN role has elevated permissions."""
        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
        assert Permission.ADMIN_PANEL in admin_perms
        assert Permission.DELETE_CUSTOMERS in admin_perms

    def test_superuser_has_all_permissions(self):
        """Test that SUPERUSER role has all permissions."""
        superuser_perms = ROLE_PERMISSIONS[Role.SUPERUSER]
        assert superuser_perms == set(Permission)


class TestGetUserRole:
    """Test get_user_role function."""

    def test_superuser_role(self):
        """Test superuser is recognized."""
        user = MagicMock()
        user.is_superuser = True
        assert get_user_role(user) == Role.SUPERUSER

    def test_admin_role(self):
        """Test admin is recognized."""
        user = MagicMock()
        user.is_superuser = False
        user.is_admin = True
        assert get_user_role(user) == Role.ADMIN

    def test_regular_user_role(self):
        """Test regular user is recognized."""
        user = MagicMock(spec=["is_superuser", "id", "email"])
        user.is_superuser = False
        assert get_user_role(user) == Role.USER

    def test_user_without_admin_flag(self):
        """Test user without is_admin attribute defaults to USER."""
        user = MagicMock(spec=["is_superuser", "id", "email"])
        user.is_superuser = False
        assert get_user_role(user) == Role.USER


class TestGetUserPermissions:
    """Test get_user_permissions function."""

    def test_regular_user_permissions(self):
        """Test regular user gets USER permissions."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        perms = get_user_permissions(user)
        assert Permission.SEND_SMS in perms
        assert Permission.ADMIN_PANEL not in perms

    def test_superuser_permissions(self):
        """Test superuser gets all permissions."""
        user = MagicMock()
        user.is_superuser = True
        perms = get_user_permissions(user)
        assert perms == set(Permission)


class TestHasPermission:
    """Test has_permission function."""

    def test_user_has_allowed_permission(self):
        """Test user has an allowed permission."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        assert has_permission(user, Permission.SEND_SMS) is True

    def test_user_lacks_forbidden_permission(self):
        """Test user lacks a forbidden permission."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        assert has_permission(user, Permission.ADMIN_PANEL) is False


class TestRequirePermission:
    """Test require_permission dependency."""

    @pytest.mark.asyncio
    async def test_permission_granted(self):
        """Test no exception when permission is granted."""
        user = MagicMock()
        user.is_superuser = True
        checker = require_permission(Permission.ADMIN_PANEL)
        await checker(user)

    @pytest.mark.asyncio
    async def test_permission_denied(self):
        """Test exception when permission is denied."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        user.id = 1
        checker = require_permission(Permission.ADMIN_PANEL)
        with pytest.raises(HTTPException) as exc:
            await checker(user)
        assert exc.value.status_code == 403
        assert "Permission denied" in exc.value.detail


class TestRequireAdmin:
    """Test require_admin dependency."""

    @pytest.mark.asyncio
    async def test_admin_allowed(self):
        """Test admin is allowed."""
        user = MagicMock()
        user.is_superuser = False
        user.is_admin = True
        await require_admin(user)

    @pytest.mark.asyncio
    async def test_superuser_allowed(self):
        """Test superuser is allowed."""
        user = MagicMock()
        user.is_superuser = True
        await require_admin(user)

    @pytest.mark.asyncio
    async def test_regular_user_denied(self):
        """Test regular user is denied."""
        user = MagicMock(spec=["is_superuser", "is_admin", "id"])
        user.is_superuser = False
        user.is_admin = False
        user.id = 1
        with pytest.raises(HTTPException) as exc:
            await require_admin(user)
        assert exc.value.status_code == 403
        assert "Admin access required" in exc.value.detail


class TestRequireSuperuser:
    """Test require_superuser dependency."""

    @pytest.mark.asyncio
    async def test_superuser_allowed(self):
        """Test superuser is allowed."""
        user = MagicMock()
        user.is_superuser = True
        await require_superuser(user)

    @pytest.mark.asyncio
    async def test_admin_denied(self):
        """Test admin is denied."""
        user = MagicMock()
        user.is_superuser = False
        user.id = 1
        with pytest.raises(HTTPException) as exc:
            await require_superuser(user)
        assert exc.value.status_code == 403
        assert "Superuser access required" in exc.value.detail


class TestRBACChecker:
    """Test RBACChecker class."""

    @pytest.mark.asyncio
    async def test_role_check_passes(self):
        """Test role check passes for sufficient role."""
        user = MagicMock()
        user.is_superuser = True
        checker = RBACChecker(required_role=Role.ADMIN)
        await checker(user)

    @pytest.mark.asyncio
    async def test_role_check_fails(self):
        """Test role check fails for insufficient role."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        checker = RBACChecker(required_role=Role.ADMIN)
        with pytest.raises(HTTPException) as exc:
            await checker(user)
        assert exc.value.status_code == 403
        assert "role" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_permission_and_logic(self):
        """Test AND logic for multiple permissions (all required)."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        checker = RBACChecker(
            required_permissions=[Permission.SEND_SMS, Permission.ADMIN_PANEL],
            any_permission=False
        )
        with pytest.raises(HTTPException) as exc:
            await checker(user)
        assert exc.value.status_code == 403
        assert "Missing permissions" in exc.value.detail

    @pytest.mark.asyncio
    async def test_permission_or_logic_passes(self):
        """Test OR logic for multiple permissions (any one is sufficient)."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        checker = RBACChecker(
            required_permissions=[Permission.SEND_SMS, Permission.ADMIN_PANEL],
            any_permission=True
        )
        await checker(user)

    @pytest.mark.asyncio
    async def test_permission_or_logic_fails(self):
        """Test OR logic fails when user has none of the permissions."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        checker = RBACChecker(
            required_permissions=[Permission.ADMIN_PANEL, Permission.MANAGE_USERS],
            any_permission=True
        )
        with pytest.raises(HTTPException) as exc:
            await checker(user)
        assert exc.value.status_code == 403
        assert "Insufficient permissions" in exc.value.detail

    @pytest.mark.asyncio
    async def test_no_requirements(self):
        """Test checker with no requirements passes."""
        user = MagicMock(spec=["is_superuser", "id"])
        user.is_superuser = False
        checker = RBACChecker()
        await checker(user)
