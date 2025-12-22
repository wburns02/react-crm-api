from typing import Annotated
from fastapi import Depends, HTTPException, status, Cookie, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
import bcrypt
from datetime import datetime, timedelta
import logging

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)


# HTTP Bearer for JWT
security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')


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
    """Get current user from JWT token or session cookie."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = None

    # Try Bearer token first
    if credentials:
        token = credentials.credentials
        logger.info(f"Got token from Bearer header")
    # Fall back to session cookie
    elif session_token:
        token = session_token
        logger.info(f"Got token from session cookie")

    if not token:
        logger.warning("No token found in request")
        raise credentials_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        logger.info(f"JWT payload: {payload}")
        sub = payload.get("sub")
        email: str = payload.get("email")
        if sub is None:
            logger.warning("sub is None from token")
            raise credentials_exception
        user_id = int(sub)  # Convert string back to int
        logger.info(f"Extracted user_id={user_id}, email={email}")
        token_data = TokenData(user_id=user_id, email=email)
    except JWTError as e:
        logger.error(f"JWT decode error: {e}")
        raise credentials_exception
    except ValueError as e:
        logger.error(f"Invalid user_id format: {e}")
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == token_data.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Type aliases for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_active_user)]
