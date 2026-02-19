"""
FastAPI Dependencies

Provides dependency injection for database sessions, authentication,
and authorization.

SECURITY NOTES:
- JWT payloads are never logged
- Bearer token is the primary auth method (SPA-friendly, no CSRF needed)
- Session cookies are supported but Bearer is preferred
"""

from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status, Cookie, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
import bcrypt
from datetime import datetime, timedelta
import logging

from app.database import get_db, async_session_maker
from app.config import settings
from app.models.user import User
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)


# HTTP Bearer for JWT - primary auth method
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str | None) -> bool:
    """Verify a password against a hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        # Handle invalid hash format gracefully
        return False


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    session_token: Annotated[str | None, Cookie(alias="session")] = None,
) -> User:
    """
    Get current user from JWT token or session cookie.

    SECURITY:
    - Bearer token is preferred (no CSRF vulnerability)
    - Session cookie supported for browser convenience
    - JWT payloads are NOT logged to prevent credential leakage
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None
    auth_method = None

    # Try Bearer token first (preferred for SPAs - no CSRF vulnerability)
    if credentials:
        token = credentials.credentials
        auth_method = "bearer"
    # Fall back to session cookie
    elif session_token:
        token = session_token
        auth_method = "cookie"

    if not token:
        # SECURITY: Don't reveal which auth methods are supported
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # SECURITY: Never log JWT payloads - they contain sensitive data
        sub = payload.get("sub")
        email: str = payload.get("email")
        if sub is None:
            raise credentials_exception
        user_id = int(sub)
        token_data = TokenData(user_id=user_id, email=email)
    except JWTError:
        # SECURITY: Don't log token decode errors with details
        logger.warning("JWT validation failed", extra={"auth_method": auth_method})
        raise credentials_exception
    except ValueError:
        logger.warning("Invalid token format", extra={"auth_method": auth_method})
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

    # Log successful auth without sensitive details
    logger.debug("User authenticated", extra={"user_id": user.id, "auth_method": auth_method})

    return user


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")
    return current_user


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]


# --- Multi-Entity (LLC) Support ---

from app.models.company_entity import CompanyEntity


async def get_entity_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> Optional[CompanyEntity]:
    """
    Extract entity context from X-Entity-ID header.
    Falls back to user's default entity, then system default.
    Returns None only if no entities exist yet.
    """
    entity_id = request.headers.get("X-Entity-ID")

    if entity_id:
        result = await db.execute(
            select(CompanyEntity).where(
                CompanyEntity.id == entity_id,
                CompanyEntity.is_active == True,
            )
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity

    # Fallback: user's default entity
    if current_user.default_entity_id:
        result = await db.execute(
            select(CompanyEntity).where(CompanyEntity.id == current_user.default_entity_id)
        )
        entity = result.scalar_one_or_none()
        if entity:
            return entity

    # Fallback: system default entity (is_default=True)
    result = await db.execute(
        select(CompanyEntity).where(CompanyEntity.is_default == True)
    )
    return result.scalar_one_or_none()


EntityCtx = Annotated[Optional[CompanyEntity], Depends(get_entity_context)]


async def get_current_user_ws(token: str | None, session_cookie: str | None = None) -> User | None:
    """
    Authenticate WebSocket connections using JWT token or session cookie.

    Tries query parameter token first, then falls back to session cookie.
    This handles the case where the localStorage JWT has expired but the
    session cookie is still valid.

    SECURITY:
    - Token is validated the same way as Bearer tokens
    - Returns None on failure instead of raising exception (WebSocket pattern)
    - JWT payloads are NOT logged

    Args:
        token: JWT access token from WebSocket query parameter
        session_cookie: Session cookie value (fallback auth)

    Returns:
        User object if authenticated, None otherwise
    """
    # Try token first, then fall back to session cookie
    auth_token = token or session_cookie
    if not auth_token:
        logger.warning("WebSocket auth failed: no token or session cookie provided")
        return None

    try:
        payload = jwt.decode(auth_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            logger.warning("WebSocket auth failed: no sub claim in token")
            return None

        user_id = int(sub)
    except JWTError:
        logger.warning("WebSocket auth failed: JWT validation error")
        return None
    except ValueError:
        logger.warning("WebSocket auth failed: invalid user_id format")
        return None

    # Get database session manually since we can't use dependency injection
    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            logger.warning(f"WebSocket auth failed: user {user_id} not found")
            return None

        if not user.is_active:
            logger.warning(f"WebSocket auth failed: user {user_id} is inactive")
            return None

        logger.debug(f"WebSocket authenticated: user_id={user_id}")
        return user
