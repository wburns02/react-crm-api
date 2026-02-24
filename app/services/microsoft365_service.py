"""
Microsoft 365 OAuth Service

Handles delegated OAuth flow for SSO login and account linking.
"""

import httpx
import logging
from urllib.parse import urlencode

from app.config import settings
from app.services.ms365_base import MS365BaseService

logger = logging.getLogger(__name__)


class Microsoft365Service(MS365BaseService):
    """Service for Microsoft SSO and user-delegated Graph API calls."""

    AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"

    @classmethod
    def get_auth_url(cls, state: str | None = None) -> str:
        """Generate Microsoft OAuth authorization URL for SSO."""
        params = {
            "client_id": settings.MS365_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": settings.MS365_REDIRECT_URI,
            "scope": "openid profile email User.Read",
            "response_mode": "query",
        }
        if state:
            params["state"] = state
        base = cls.AUTHORIZE_URL.format(tenant_id=settings.MS365_TENANT_ID)
        return f"{base}?{urlencode(params)}"

    @classmethod
    async def exchange_code(cls, code: str) -> dict:
        """Exchange authorization code for tokens."""
        token_url = cls.TOKEN_URL_TEMPLATE.format(tenant_id=settings.MS365_TENANT_ID)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data={
                "client_id": settings.MS365_CLIENT_ID,
                "client_secret": settings.MS365_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.MS365_REDIRECT_URI,
                "grant_type": "authorization_code",
                "scope": "openid profile email User.Read",
            })
            resp.raise_for_status()
            return resp.json()

    @classmethod
    async def get_user_profile(cls, access_token: str) -> dict:
        """Get user profile from MS Graph using delegated token."""
        return await cls.graph_get("/me", token=access_token)
