"""
Yelp Fusion API Service

Integrates with Yelp Fusion API for:
- Business information lookup
- Review fetching

Note: Yelp API does NOT support responding to reviews programmatically.
Reviews are read-only through the API.
"""

import httpx
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class YelpConfig(BaseModel):
    """Yelp API configuration."""
    api_key: str = ""
    base_url: str = "https://api.yelp.com/v3"


class YelpService:
    """Service for Yelp Fusion API integration."""

    def __init__(self):
        self.config = YelpConfig(
            api_key=settings.YELP_API_KEY or "",
        )
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if Yelp is configured."""
        return bool(self.config.api_key)

    async def get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with auth headers."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Accept": "application/json",
                }
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_status(self) -> Dict[str, Any]:
        """Get Yelp connection status."""
        if not self.is_configured:
            return {
                "connected": False,
                "configured": False,
                "message": "Yelp API key not configured",
            }

        # Test API connection by searching for a business
        try:
            client = await self.get_client()
            response = await client.get(
                "/businesses/search",
                params={"term": "test", "location": "San Francisco", "limit": 1}
            )
            response.raise_for_status()
            return {
                "connected": True,
                "configured": True,
                "message": "Connected to Yelp Fusion API",
            }
        except httpx.HTTPStatusError as e:
            logger.error(f"Yelp API status check failed: {e.response.status_code}")
            return {
                "connected": False,
                "configured": True,
                "message": f"Yelp API error: {e.response.status_code}",
            }
        except Exception as e:
            logger.error(f"Yelp API connection error: {e}")
            return {
                "connected": False,
                "configured": True,
                "message": f"Connection error: {str(e)}",
            }

    async def search_business(
        self,
        name: str,
        location: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """Search for a business by name and location.

        Args:
            name: Business name to search for
            location: City, state, or address
            limit: Maximum number of results (default 5)

        Returns:
            Search results with businesses array
        """
        if not self.is_configured:
            return {"error": "Yelp not configured", "businesses": []}

        try:
            client = await self.get_client()
            response = await client.get(
                "/businesses/search",
                params={
                    "term": name,
                    "location": location,
                    "limit": limit
                }
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yelp business search error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}", "businesses": []}
        except Exception as e:
            logger.error(f"Yelp business search error: {e}")
            return {"error": str(e), "businesses": []}

    async def get_business(self, business_id: str) -> Dict[str, Any]:
        """Get business details by Yelp business ID.

        Args:
            business_id: Yelp's unique business identifier

        Returns:
            Business details including name, rating, location, hours, etc.
        """
        if not self.is_configured:
            return {"error": "Yelp not configured"}

        try:
            client = await self.get_client()
            response = await client.get(f"/businesses/{business_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yelp get business error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Yelp get business error: {e}")
            return {"error": str(e)}

    async def get_reviews(
        self,
        business_id: str,
        locale: str = "en_US"
    ) -> Dict[str, Any]:
        """Get reviews for a business.

        Note: Yelp Fusion API returns up to 3 reviews with the free tier.
        The reviews endpoint provides review excerpts, not full reviews.

        Args:
            business_id: Yelp's unique business identifier
            locale: Language locale (default en_US)

        Returns:
            Reviews array with rating, text, time_created, user info
        """
        if not self.is_configured:
            return {"error": "Yelp not configured", "reviews": []}

        try:
            client = await self.get_client()
            response = await client.get(
                f"/businesses/{business_id}/reviews",
                params={"locale": locale}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Yelp get reviews error: {e.response.status_code}")
            return {"error": f"API error: {e.response.status_code}", "reviews": []}
        except Exception as e:
            logger.error(f"Yelp get reviews error: {e}")
            return {"error": str(e), "reviews": []}


# Singleton instance
yelp_service = YelpService()


async def get_yelp_service() -> YelpService:
    """Dependency injection for Yelp service."""
    return yelp_service
