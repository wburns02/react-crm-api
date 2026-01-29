"""
OAuth2 Schemas

Pydantic schemas for OAuth2 request/response validation.
Follows RFC 6749 OAuth 2.0 specification.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


# ============================================================================
# Token Request/Response Schemas (RFC 6749)
# ============================================================================


class TokenRequest(BaseModel):
    """
    OAuth2 Token Request for client credentials flow.

    Follows RFC 6749 Section 4.4 - Client Credentials Grant.
    """

    grant_type: str = Field(..., description="Grant type, must be 'client_credentials' or 'refresh_token'")
    client_id: str = Field(..., description="Client ID")
    client_secret: str = Field(..., description="Client secret")
    scope: Optional[str] = Field(None, description="Space-separated list of requested scopes")


class RefreshTokenRequest(BaseModel):
    """
    OAuth2 Refresh Token Request.

    Follows RFC 6749 Section 6 - Refreshing an Access Token.
    """

    grant_type: str = Field(default="refresh_token", description="Must be 'refresh_token'")
    refresh_token: str = Field(..., description="The refresh token")
    client_id: str = Field(..., description="Client ID")
    client_secret: str = Field(..., description="Client secret")
    scope: Optional[str] = Field(
        None, description="Space-separated list of requested scopes (must be subset of original)"
    )


class TokenResponse(BaseModel):
    """
    OAuth2 Token Response.

    Follows RFC 6749 Section 5.1 - Successful Response.
    """

    access_token: str = Field(..., description="The access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token for obtaining new access tokens")
    scope: str = Field(..., description="Space-separated list of granted scopes")


class TokenErrorResponse(BaseModel):
    """
    OAuth2 Error Response.

    Follows RFC 6749 Section 5.2 - Error Response.
    """

    error: str = Field(
        ...,
        description="Error code: invalid_request, invalid_client, invalid_grant, "
        "unauthorized_client, unsupported_grant_type, invalid_scope",
    )
    error_description: Optional[str] = Field(None, description="Human-readable error description")
    error_uri: Optional[str] = Field(None, description="URI for more information about the error")


# ============================================================================
# Client Management Schemas
# ============================================================================


class APIClientCreate(BaseModel):
    """Schema for creating a new API client."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: str = Field(
        default="read", description="Space-separated scopes: read, write, customers, work_orders, admin"
    )
    rate_limit_per_minute: int = Field(default=100, ge=1, le=10000)
    rate_limit_per_hour: int = Field(default=1000, ge=1, le=100000)


class APIClientResponse(BaseModel):
    """Schema for API client response (excludes secret)."""

    id: int
    client_id: str
    name: str
    description: Optional[str] = None
    scopes: str
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class APIClientWithSecretResponse(APIClientResponse):
    """
    API client response including the secret.

    Only returned on client creation - secret cannot be retrieved later.
    """

    client_secret: str = Field(..., description="Client secret - SAVE THIS! Cannot be retrieved later.")


class APIClientUpdate(BaseModel):
    """Schema for updating an API client."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    scopes: Optional[str] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_per_hour: Optional[int] = Field(None, ge=1, le=100000)
    is_active: Optional[bool] = None


# ============================================================================
# Token Introspection Schemas (RFC 7662)
# ============================================================================


class TokenIntrospectionRequest(BaseModel):
    """Token introspection request."""

    token: str = Field(..., description="The token to introspect")
    token_type_hint: Optional[str] = Field(None, description="Hint about token type: access_token or refresh_token")


class TokenIntrospectionResponse(BaseModel):
    """Token introspection response."""

    active: bool = Field(..., description="Whether the token is active")
    scope: Optional[str] = Field(None, description="Token scopes")
    client_id: Optional[str] = Field(None, description="Client that owns the token")
    token_type: Optional[str] = Field(None, description="Token type")
    exp: Optional[int] = Field(None, description="Expiration timestamp")
    iat: Optional[int] = Field(None, description="Issued at timestamp")
    sub: Optional[str] = Field(None, description="Subject (client_id)")


# ============================================================================
# Public API Error Schemas
# ============================================================================


class PublicAPIError(BaseModel):
    """Standard error response for public API."""

    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")


# ============================================================================
# Available Scopes
# ============================================================================

AVAILABLE_SCOPES = {
    "read": "Read access to resources",
    "write": "Write access to resources",
    "customers": "Access to customer resources",
    "customers:read": "Read-only access to customers",
    "customers:write": "Write access to customers",
    "work_orders": "Access to work order resources",
    "work_orders:read": "Read-only access to work orders",
    "work_orders:write": "Write access to work orders",
    "admin": "Full administrative access",
}


def validate_scopes(requested_scopes: str, allowed_scopes: str) -> str:
    """
    Validate and filter requested scopes against allowed scopes.

    Args:
        requested_scopes: Space-separated requested scopes
        allowed_scopes: Space-separated allowed scopes (from client)

    Returns:
        Space-separated validated scopes

    Raises:
        ValueError: If requested scope is not allowed
    """
    if not requested_scopes:
        return allowed_scopes

    requested = set(requested_scopes.split())
    allowed = set(allowed_scopes.split())

    # Admin scope allows everything
    if "admin" in allowed:
        return requested_scopes

    invalid = requested - allowed
    if invalid:
        raise ValueError(f"Invalid scopes: {', '.join(invalid)}")

    return " ".join(requested)
