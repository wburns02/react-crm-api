"""
Public API Dependencies

Provides dependency injection for OAuth2 authentication and rate limiting
in public API endpoints.
"""

import hashlib
import secrets
import logging
from typing import Annotated, Optional
from datetime import datetime

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.oauth import APIClient, APIToken
from app.core.rate_limit import get_public_api_rate_limiter, rate_limit_by_ip

logger = logging.getLogger(__name__)

# Bearer token security scheme
oauth2_bearer = HTTPBearer(auto_error=True)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for storage/lookup."""
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_api_client(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(oauth2_bearer)],
) -> APIClient:
    """
    Validate OAuth2 bearer token and return the associated API client.

    This is the main authentication dependency for public API endpoints.
    It validates the token, checks rate limits, and returns the client.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": "invalid_token",
            "message": "Invalid or expired access token",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    if not token:
        raise credentials_exception

    # Hash the token for lookup
    token_hash = hash_token(token)

    # Find the token in database
    result = await db.execute(select(APIToken).where(APIToken.token_hash == token_hash))
    api_token = result.scalar_one_or_none()

    if not api_token:
        logger.warning("Invalid token attempted")
        raise credentials_exception

    # Check if token is valid
    if not api_token.is_valid:
        if api_token.is_expired:
            logger.info(f"Expired token used for client {api_token.client_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "token_expired",
                    "message": "Access token has expired",
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise credentials_exception

    # Get the client
    result = await db.execute(select(APIClient).where(APIClient.id == api_token.client_id))
    client = result.scalar_one_or_none()

    if not client or not client.is_active:
        logger.warning(f"Token used for inactive/missing client {api_token.client_id}")
        raise credentials_exception

    # Apply rate limiting
    rate_limiter = get_public_api_rate_limiter()
    rate_limiter.check_rate_limit(
        client_id=client.client_id,
        rate_limit_per_minute=client.rate_limit_per_minute,
        rate_limit_per_hour=client.rate_limit_per_hour,
    )

    # Update last used timestamps
    api_token.last_used_at = datetime.utcnow()
    client.last_used_at = datetime.utcnow()
    await db.commit()

    # Store token scopes in request state for scope checking
    request.state.token_scopes = api_token.scope_list
    request.state.api_client = client

    logger.debug(
        f"API client authenticated: {client.name} ({client.client_id})",
        extra={"client_id": client.client_id, "scopes": api_token.scopes},
    )

    return client


def require_scope(required_scope: str):
    """
    Dependency factory to require a specific scope.

    Usage:
        @router.get("/resource", dependencies=[Depends(require_scope("read"))])
    """

    async def scope_checker(
        request: Request,
        client: Annotated[APIClient, Depends(get_current_api_client)],
    ) -> None:
        token_scopes = getattr(request.state, "token_scopes", [])

        # Admin scope has access to everything
        if "admin" in token_scopes:
            return

        # Check for specific scope
        if required_scope not in token_scopes:
            # Also check for parent scope (e.g., "customers" covers "customers:read")
            parent_scope = required_scope.split(":")[0]
            if parent_scope not in token_scopes:
                logger.warning(
                    f"Scope {required_scope} denied for client {client.client_id}",
                    extra={"client_id": client.client_id, "required": required_scope},
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "error": "insufficient_scope",
                        "message": f"This endpoint requires the '{required_scope}' scope",
                        "required_scope": required_scope,
                    },
                )

    return scope_checker


# Type aliases for cleaner dependency injection
PublicAPIClient = Annotated[APIClient, Depends(get_current_api_client)]
DbSession = Annotated[AsyncSession, Depends(get_db)]
