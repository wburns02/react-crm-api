"""
Facebook Graph API Service

Integrates with Facebook Graph API for:
- OAuth2 authorization flow for Business Pages
- Fetching page reviews/recommendations
- Posting review replies
- Fetching page insights
"""

import httpx
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime, timedelta
from urllib.parse import urlencode

from app.config import settings

logger = logging.getLogger(__name__)


class FacebookConfig(BaseModel):
    """Facebook App configuration."""
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    graph_url: str = "https://graph.facebook.com/v18.0"


class FacebookService:
    """Service for Facebook Graph API integration."""

    # Required permissions for page review management
    REQUIRED_SCOPES = [
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_engagement",  # For responding to reviews
        "pages_read_user_content",  # For reading reviews
        "read_insights",  # For page analytics
    ]

    def __init__(self):
        self.config = FacebookConfig(
            app_id=settings.FACEBOOK_APP_ID or "",
            app_secret=settings.FACEBOOK_APP_SECRET or "",
            redirect_uri=settings.FACEBOOK_REDIRECT_URI or "",
        )
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if Facebook is configured."""
        return bool(self.config.app_id and self.config.app_secret)

    async def get_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.graph_url,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def get_authorization_url(self, state: str) -> str:
        """Generate Facebook OAuth authorization URL.

        Args:
            state: CSRF protection state parameter

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.config.app_id,
            "redirect_uri": self.config.redirect_uri,
            "state": state,
            "scope": ",".join(self.REQUIRED_SCOPES),
            "response_type": "code",
        }
        return f"https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response with access_token, expires_in
        """
        try:
            client = await self.get_client()
            response = await client.get(
                "/oauth/access_token",
                params={
                    "client_id": self.config.app_id,
                    "client_secret": self.config.app_secret,
                    "redirect_uri": self.config.redirect_uri,
                    "code": code,
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(f"Facebook token exchange error: {e.response.status_code} - {error_body}")
            return {"error": f"Token exchange failed: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Facebook token exchange error: {e}")
            return {"error": str(e)}

    async def get_long_lived_token(self, short_token: str) -> Dict[str, Any]:
        """Exchange short-lived token for long-lived token (60 days).

        Args:
            short_token: Short-lived access token

        Returns:
            Long-lived token response
        """
        try:
            client = await self.get_client()
            response = await client.get(
                "/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": self.config.app_id,
                    "client_secret": self.config.app_secret,
                    "fb_exchange_token": short_token,
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook long-lived token error: {e.response.status_code}")
            return {"error": f"Token exchange failed: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Facebook long-lived token error: {e}")
            return {"error": str(e)}

    async def get_user_pages(self, user_access_token: str) -> Dict[str, Any]:
        """Get list of pages the user manages.

        Args:
            user_access_token: User's access token

        Returns:
            Pages data with id, name, access_token for each page
        """
        try:
            client = await self.get_client()
            response = await client.get(
                "/me/accounts",
                params={
                    "access_token": user_access_token,
                    "fields": "id,name,access_token,category,picture",
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook get pages error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}", "data": []}
        except Exception as e:
            logger.error(f"Facebook get pages error: {e}")
            return {"error": str(e), "data": []}

    async def get_page_reviews(
        self,
        page_id: str,
        page_access_token: str,
        limit: int = 25
    ) -> Dict[str, Any]:
        """Get reviews/recommendations for a Facebook page.

        Note: Facebook calls these "ratings" in their API.

        Args:
            page_id: Facebook page ID
            page_access_token: Page access token
            limit: Maximum reviews to fetch

        Returns:
            Reviews data with reviewer info, rating, review_text, created_time
        """
        try:
            client = await self.get_client()
            response = await client.get(
                f"/{page_id}/ratings",
                params={
                    "access_token": page_access_token,
                    "fields": "reviewer{id,name,picture},rating,review_text,created_time,has_review,recommendation_type",
                    "limit": limit,
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook get reviews error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}", "data": []}
        except Exception as e:
            logger.error(f"Facebook get reviews error: {e}")
            return {"error": str(e), "data": []}

    async def reply_to_review(
        self,
        review_id: str,
        page_access_token: str,
        message: str,
    ) -> Dict[str, Any]:
        """Reply to a review/recommendation.

        Note: This posts a comment on the review.

        Args:
            review_id: Review ID to reply to
            page_access_token: Page access token
            message: Reply message

        Returns:
            Success status and comment ID
        """
        try:
            client = await self.get_client()
            response = await client.post(
                f"/{review_id}/comments",
                params={"access_token": page_access_token},
                data={"message": message}
            )
            response.raise_for_status()
            return {"success": True, **response.json()}
        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(f"Facebook reply to review error: {e.response.status_code} - {error_body}")
            return {"success": False, "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Facebook reply to review error: {e}")
            return {"success": False, "error": str(e)}

    async def get_page_insights(
        self,
        page_id: str,
        page_access_token: str,
        metrics: Optional[List[str]] = None,
        period: str = "day",
    ) -> Dict[str, Any]:
        """Get page insights/analytics.

        Args:
            page_id: Facebook page ID
            page_access_token: Page access token
            metrics: List of metrics to fetch (default: common engagement metrics)
            period: 'day', 'week', 'days_28'

        Returns:
            Insights data array
        """
        if metrics is None:
            metrics = [
                "page_impressions",
                "page_engaged_users",
                "page_fans",
                "page_fan_adds",
            ]

        try:
            client = await self.get_client()
            response = await client.get(
                f"/{page_id}/insights",
                params={
                    "access_token": page_access_token,
                    "metric": ",".join(metrics),
                    "period": period,
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook get insights error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}", "data": []}
        except Exception as e:
            logger.error(f"Facebook get insights error: {e}")
            return {"error": str(e), "data": []}

    async def get_status(self, page_access_token: Optional[str] = None) -> Dict[str, Any]:
        """Get Facebook connection status.

        Args:
            page_access_token: Optional page token to test connection

        Returns:
            Connection status dict
        """
        if not self.is_configured:
            return {
                "connected": False,
                "configured": False,
                "message": "Facebook App credentials not configured",
            }

        if not page_access_token:
            return {
                "connected": False,
                "configured": True,
                "message": "No Facebook page connected. Please authorize a page.",
            }

        # Test API connection
        try:
            client = await self.get_client()
            response = await client.get(
                "/me",
                params={"access_token": page_access_token, "fields": "id,name"}
            )
            response.raise_for_status()
            data = response.json()
            return {
                "connected": True,
                "configured": True,
                "page_id": data.get("id"),
                "page_name": data.get("name"),
                "message": f"Connected to {data.get('name')}",
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Facebook status check error: {e.response.status_code}")
            return {
                "connected": False,
                "configured": True,
                "message": f"Facebook API error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"Facebook status check error: {e}")
            return {
                "connected": False,
                "configured": True,
                "message": f"Connection error: {str(e)}",
            }


# Singleton instance
facebook_service = FacebookService()


async def get_facebook_service() -> FacebookService:
    """Dependency injection for Facebook service."""
    return facebook_service
