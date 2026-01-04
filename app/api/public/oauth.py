"""
OAuth2 Endpoints

Implements OAuth2 client credentials flow for public API authentication.
Follows RFC 6749 OAuth 2.0 specification.
"""

import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import APIRouter, HTTPException, status, Request, Depends, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.oauth import APIClient, APIToken
from app.schemas.oauth import (
    TokenRequest,
    TokenResponse,
    TokenErrorResponse,
    APIClientCreate,
    APIClientResponse,
    APIClientWithSecretResponse,
    APIClientUpdate,
    TokenIntrospectionRequest,
    TokenIntrospectionResponse,
    validate_scopes,
)
from app.core.rate_limit import rate_limit_by_ip
from app.api.deps import CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth2"])

# Token configuration
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_DAYS = 30


def generate_client_id() -> str:
    """Generate a unique client ID."""
    return f"client_{secrets.token_hex(16)}"


def generate_client_secret() -> str:
    """Generate a secure client secret."""
    return secrets.token_urlsafe(32)


def generate_access_token() -> str:
    """Generate a secure access token."""
    return secrets.token_urlsafe(48)


def generate_refresh_token() -> str:
    """Generate a secure refresh token."""
    return secrets.token_urlsafe(64)


def hash_secret(secret: str) -> str:
    """Hash a client secret using bcrypt."""
    return bcrypt.hashpw(secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_secret(plain_secret: str, hashed_secret: str) -> bool:
    """Verify a client secret against its hash."""
    return bcrypt.checkpw(plain_secret.encode("utf-8"), hashed_secret.encode("utf-8"))


def hash_token(token: str) -> str:
    """Hash an access/refresh token using SHA-256."""
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================================================
# OAuth2 Token Endpoints
# ============================================================================

@router.post(
    "/oauth/token",
    response_model=TokenResponse,
    responses={
        400: {"model": TokenErrorResponse, "description": "Invalid request"},
        401: {"model": TokenErrorResponse, "description": "Invalid client credentials"},
    },
    summary="Get Access Token",
    description="""
    OAuth2 token endpoint for client credentials flow.

    **Grant Types:**
    - `client_credentials`: Exchange client ID and secret for access token
    - `refresh_token`: Exchange refresh token for new access token

    **Rate Limiting:** 30 requests per minute per IP address.
    """,
)
async def get_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(default=None),
    refresh_token: str = Form(default=None),
):
    """
    OAuth2 token endpoint.

    Supports:
    - client_credentials: Get new access token
    - refresh_token: Refresh an existing token
    """
    # Rate limit by IP to prevent brute force
    rate_limit_by_ip(request, requests_per_minute=30)

    # Validate grant type
    if grant_type not in ("client_credentials", "refresh_token"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unsupported_grant_type",
                "error_description": "Grant type must be 'client_credentials' or 'refresh_token'",
            },
        )

    # Find the client
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        logger.warning(f"Token request with invalid client_id: {client_id[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Invalid client credentials",
            },
        )

    # Verify client secret
    if not verify_secret(client_secret, client.client_secret_hash):
        logger.warning(f"Token request with invalid secret for client: {client_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Invalid client credentials",
            },
        )

    # Check if client is active
    if not client.is_active:
        logger.warning(f"Token request for inactive client: {client_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_client",
                "error_description": "Client is disabled",
            },
        )

    # Handle grant types
    if grant_type == "client_credentials":
        return await _handle_client_credentials(db, client, scope)
    elif grant_type == "refresh_token":
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "invalid_request",
                    "error_description": "refresh_token is required for refresh_token grant",
                },
            )
        return await _handle_refresh_token(db, client, refresh_token, scope)


async def _handle_client_credentials(
    db: AsyncSession,
    client: APIClient,
    requested_scope: str | None,
) -> TokenResponse:
    """Handle client credentials grant type."""
    # Validate requested scopes
    try:
        granted_scopes = validate_scopes(
            requested_scope or client.scopes,
            client.scopes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_scope",
                "error_description": str(e),
            },
        )

    # Generate tokens
    access_token = generate_access_token()
    refresh_token = generate_refresh_token()

    # Calculate expiration
    expires_at = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Store token in database
    api_token = APIToken(
        token_hash=hash_token(access_token),
        client_id=client.id,
        scopes=granted_scopes,
        expires_at=expires_at,
        refresh_token_hash=hash_token(refresh_token),
        refresh_expires_at=refresh_expires_at,
    )
    db.add(api_token)

    # Update client last used
    client.last_used_at = datetime.utcnow()

    await db.commit()

    logger.info(
        f"Access token issued for client: {client.client_id}",
        extra={"client_id": client.client_id, "scopes": granted_scopes}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=refresh_token,
        scope=granted_scopes,
    )


async def _handle_refresh_token(
    db: AsyncSession,
    client: APIClient,
    refresh_token: str,
    requested_scope: str | None,
) -> TokenResponse:
    """Handle refresh token grant type."""
    # Find the token by refresh token hash
    result = await db.execute(
        select(APIToken).where(
            APIToken.refresh_token_hash == hash_token(refresh_token),
            APIToken.client_id == client.id,
        )
    )
    old_token = result.scalar_one_or_none()

    if not old_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": "Invalid refresh token",
            },
        )

    # Check if refresh token is expired
    if old_token.refresh_expires_at and datetime.utcnow() > old_token.refresh_expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": "Refresh token has expired",
            },
        )

    # Check if token is revoked
    if old_token.is_revoked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_grant",
                "error_description": "Token has been revoked",
            },
        )

    # Validate requested scopes (must be subset of original)
    try:
        granted_scopes = validate_scopes(
            requested_scope or old_token.scopes,
            old_token.scopes,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_scope",
                "error_description": str(e),
            },
        )

    # Revoke old token
    old_token.is_revoked = True

    # Generate new tokens
    access_token = generate_access_token()
    new_refresh_token = generate_refresh_token()

    # Calculate expiration
    expires_at = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_expires_at = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Store new token
    api_token = APIToken(
        token_hash=hash_token(access_token),
        client_id=client.id,
        scopes=granted_scopes,
        expires_at=expires_at,
        refresh_token_hash=hash_token(new_refresh_token),
        refresh_expires_at=refresh_expires_at,
    )
    db.add(api_token)

    await db.commit()

    logger.info(
        f"Token refreshed for client: {client.client_id}",
        extra={"client_id": client.client_id}
    )

    return TokenResponse(
        access_token=access_token,
        token_type="Bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=new_refresh_token,
        scope=granted_scopes,
    )


@router.post(
    "/oauth/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke Token",
    description="Revoke an access token or refresh token.",
)
async def revoke_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Form(...),
    token_type_hint: str = Form(default=None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    """
    Revoke an access token or refresh token.

    Per RFC 7009, always return 200 OK even if token is invalid.
    """
    # Rate limit
    rate_limit_by_ip(request, requests_per_minute=30)

    # Verify client credentials
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client or not verify_secret(client_secret, client.client_secret_hash):
        # Per RFC 7009, return 200 even for invalid client
        return {"status": "ok"}

    # Try to find and revoke the token
    token_hash = hash_token(token)

    # Check access token
    result = await db.execute(
        select(APIToken).where(
            APIToken.token_hash == token_hash,
            APIToken.client_id == client.id,
        )
    )
    api_token = result.scalar_one_or_none()

    if api_token:
        api_token.is_revoked = True
        await db.commit()
        logger.info(f"Token revoked for client: {client.client_id}")
        return {"status": "ok"}

    # Check refresh token
    result = await db.execute(
        select(APIToken).where(
            APIToken.refresh_token_hash == token_hash,
            APIToken.client_id == client.id,
        )
    )
    api_token = result.scalar_one_or_none()

    if api_token:
        api_token.is_revoked = True
        await db.commit()
        logger.info(f"Refresh token revoked for client: {client.client_id}")

    return {"status": "ok"}


@router.post(
    "/oauth/introspect",
    response_model=TokenIntrospectionResponse,
    summary="Introspect Token",
    description="Get information about an access token (RFC 7662).",
)
async def introspect_token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: str = Form(...),
    token_type_hint: str = Form(default=None),
    client_id: str = Form(...),
    client_secret: str = Form(...),
):
    """
    Token introspection endpoint (RFC 7662).

    Returns information about a token including whether it's active.
    """
    # Rate limit
    rate_limit_by_ip(request, requests_per_minute=60)

    # Verify client credentials
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client or not verify_secret(client_secret, client.client_secret_hash):
        return TokenIntrospectionResponse(active=False)

    # Find the token
    token_hash = hash_token(token)
    result = await db.execute(
        select(APIToken).where(APIToken.token_hash == token_hash)
    )
    api_token = result.scalar_one_or_none()

    if not api_token:
        return TokenIntrospectionResponse(active=False)

    # Check if token belongs to this client (or client has admin scope)
    if api_token.client_id != client.id and "admin" not in client.scope_list:
        return TokenIntrospectionResponse(active=False)

    # Return token info
    return TokenIntrospectionResponse(
        active=api_token.is_valid,
        scope=api_token.scopes,
        client_id=client.client_id,
        token_type="Bearer",
        exp=int(api_token.expires_at.timestamp()) if api_token.expires_at else None,
        iat=int(api_token.created_at.timestamp()) if api_token.created_at else None,
        sub=client.client_id,
    )


# ============================================================================
# Client Management Endpoints (Admin Only)
# ============================================================================

@router.post(
    "/clients",
    response_model=APIClientWithSecretResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API Client",
    description="Create a new API client. Requires admin authentication.",
)
async def create_client(
    client_data: APIClientCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """
    Create a new API client.

    The client secret is only returned once - save it securely!
    """
    # Generate credentials
    new_client_id = generate_client_id()
    new_client_secret = generate_client_secret()

    # Create client
    client = APIClient(
        client_id=new_client_id,
        client_secret_hash=hash_secret(new_client_secret),
        name=client_data.name,
        description=client_data.description,
        scopes=client_data.scopes,
        rate_limit_per_minute=client_data.rate_limit_per_minute,
        rate_limit_per_hour=client_data.rate_limit_per_hour,
        owner_user_id=current_user.id,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)

    logger.info(
        f"API client created: {client.name} ({client.client_id}) by user {current_user.id}"
    )

    # Return with secret (only time it's visible)
    return APIClientWithSecretResponse(
        id=client.id,
        client_id=client.client_id,
        client_secret=new_client_secret,
        name=client.name,
        description=client.description,
        scopes=client.scopes,
        rate_limit_per_minute=client.rate_limit_per_minute,
        rate_limit_per_hour=client.rate_limit_per_hour,
        is_active=client.is_active,
        created_at=client.created_at,
        last_used_at=client.last_used_at,
    )


@router.get(
    "/clients",
    response_model=list[APIClientResponse],
    summary="List API Clients",
    description="List all API clients. Requires admin authentication.",
)
async def list_clients(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """List all API clients."""
    result = await db.execute(select(APIClient).order_by(APIClient.created_at.desc()))
    clients = result.scalars().all()
    return clients


@router.get(
    "/clients/{client_id}",
    response_model=APIClientResponse,
    summary="Get API Client",
    description="Get details of a specific API client.",
)
async def get_client(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """Get a specific API client by client_id."""
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API client not found",
        )

    return client


@router.patch(
    "/clients/{client_id}",
    response_model=APIClientResponse,
    summary="Update API Client",
    description="Update an API client's settings.",
)
async def update_client(
    client_id: str,
    client_data: APIClientUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """Update an API client."""
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API client not found",
        )

    # Update fields
    update_data = client_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)

    client.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(client)

    logger.info(f"API client updated: {client.client_id} by user {current_user.id}")

    return client


@router.delete(
    "/clients/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete API Client",
    description="Delete an API client and revoke all its tokens.",
)
async def delete_client(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """Delete an API client."""
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API client not found",
        )

    await db.delete(client)  # Cascades to tokens
    await db.commit()

    logger.info(f"API client deleted: {client_id} by user {current_user.id}")


@router.post(
    "/clients/{client_id}/rotate-secret",
    response_model=APIClientWithSecretResponse,
    summary="Rotate Client Secret",
    description="Generate a new client secret. The old secret becomes invalid immediately.",
)
async def rotate_client_secret(
    client_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
):
    """Rotate the client secret."""
    result = await db.execute(
        select(APIClient).where(APIClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API client not found",
        )

    # Generate new secret
    new_secret = generate_client_secret()
    client.client_secret_hash = hash_secret(new_secret)
    client.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(client)

    logger.info(f"Client secret rotated: {client_id} by user {current_user.id}")

    return APIClientWithSecretResponse(
        id=client.id,
        client_id=client.client_id,
        client_secret=new_secret,
        name=client.name,
        description=client.description,
        scopes=client.scopes,
        rate_limit_per_minute=client.rate_limit_per_minute,
        rate_limit_per_hour=client.rate_limit_per_hour,
        is_active=client.is_active,
        created_at=client.created_at,
        last_used_at=client.last_used_at,
    )
