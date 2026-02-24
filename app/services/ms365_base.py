"""
Microsoft 365 Base Service

Provides shared token acquisition (client_credentials flow) for all MS Graph API calls.
"""

import httpx
import time
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level token cache
_token_cache: dict = {"access_token": None, "expires_at": 0}


class MS365BaseService:
    """Base service for Microsoft Graph API interactions."""

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    @classmethod
    def is_configured(cls) -> bool:
        return bool(settings.MS365_CLIENT_ID and settings.MS365_CLIENT_SECRET and settings.MS365_TENANT_ID)

    @classmethod
    async def get_app_token(cls) -> str:
        """Get an application-level access token using client_credentials flow (cached)."""
        if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
            return _token_cache["access_token"]

        token_url = cls.TOKEN_URL_TEMPLATE.format(tenant_id=settings.MS365_TENANT_ID)
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data={
                "client_id": settings.MS365_CLIENT_ID,
                "client_secret": settings.MS365_CLIENT_SECRET,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            })
            resp.raise_for_status()
            data = resp.json()

        _token_cache["access_token"] = data["access_token"]
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
        logger.info("MS365 app token acquired (expires in %ds)", data.get("expires_in", 3600))
        return data["access_token"]

    @classmethod
    async def graph_get(cls, path: str, token: str | None = None) -> dict:
        """Make an authenticated GET request to MS Graph."""
        if not token:
            token = await cls.get_app_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{cls.GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @classmethod
    async def graph_post(cls, path: str, json_data: dict, token: str | None = None) -> dict:
        """Make an authenticated POST request to MS Graph."""
        if not token:
            token = await cls.get_app_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{cls.GRAPH_BASE}{path}",
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @classmethod
    async def graph_patch(cls, path: str, json_data: dict, token: str | None = None) -> dict:
        """Make an authenticated PATCH request to MS Graph."""
        if not token:
            token = await cls.get_app_token()
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"{cls.GRAPH_BASE}{path}",
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @classmethod
    async def graph_delete(cls, path: str, token: str | None = None) -> None:
        """Make an authenticated DELETE request to MS Graph."""
        if not token:
            token = await cls.get_app_token()
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{cls.GRAPH_BASE}{path}",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
