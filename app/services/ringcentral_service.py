"""RingCentral Service - VoIP integration for click-to-call and call tracking.

Features:
- Click-to-call from CRM
- Incoming call popup (via webhook)
- Call recording management
- Call log synchronization
- AI transcription integration
"""
import httpx
import logging
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from datetime import datetime, timedelta
import json

from app.config import settings

logger = logging.getLogger(__name__)


class RingCentralConfig(BaseModel):
    """RingCentral API configuration."""
    client_id: str = ""
    client_secret: str = ""
    server_url: str = "https://platform.ringcentral.com"
    jwt_token: str = ""  # For server-to-server auth
    webhook_url: str = ""


class RingCentralService:
    """Service for RingCentral API integration."""

    def __init__(self):
        self.config = RingCentralConfig(
            client_id=settings.RINGCENTRAL_CLIENT_ID or '',
            client_secret=settings.RINGCENTRAL_CLIENT_SECRET or '',
            server_url=settings.RINGCENTRAL_SERVER_URL or 'https://platform.ringcentral.com',
            jwt_token=settings.RINGCENTRAL_JWT_TOKEN or '',
        )
        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """Check if RingCentral is configured."""
        return bool(self.config.client_id and self.config.client_secret)

    async def get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with auth headers."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.config.server_url,
                timeout=30.0,
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def get_access_token(self) -> Optional[str]:
        """Get or refresh OAuth access token."""
        if not self.is_configured:
            return None

        # Return cached token if still valid
        if self._access_token and self._token_expires and datetime.utcnow() < self._token_expires:
            return self._access_token

        try:
            client = await self.get_client()

            # Use JWT authentication (server-to-server)
            if self.config.jwt_token:
                response = await client.post(
                    "/restapi/oauth/token",
                    data={
                        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                        "assertion": self.config.jwt_token,
                    },
                    auth=(self.config.client_id, self.config.client_secret),
                )
            else:
                # Client credentials flow
                response = await client.post(
                    "/restapi/oauth/token",
                    data={"grant_type": "client_credentials"},
                    auth=(self.config.client_id, self.config.client_secret),
                )

            response.raise_for_status()
            data = response.json()

            self._access_token = data["access_token"]
            self._token_expires = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600) - 60)

            return self._access_token

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else "No response body"
            logger.error(f"RingCentral auth failed: {e.response.status_code} - {error_detail}")
            self._last_auth_error = f"{e.response.status_code}: {error_detail}"
            return None
        except Exception as e:
            logger.error(f"Failed to get RingCentral access token: {e}")
            self._last_auth_error = str(e)
            return None

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make authenticated API request."""
        token = await self.get_access_token()
        if not token:
            return {"error": "Not authenticated", "configured": False}

        try:
            client = await self.get_client()
            headers = {"Authorization": f"Bearer {token}"}

            if method == "GET":
                response = await client.get(endpoint, headers=headers, params=params)
            elif method == "POST":
                response = await client.post(endpoint, headers=headers, json=data)
            elif method == "DELETE":
                response = await client.delete(endpoint, headers=headers)
            else:
                return {"error": f"Unsupported method: {method}"}

            response.raise_for_status()
            return response.json() if response.content else {"status": "success"}

        except httpx.HTTPStatusError as e:
            error_body = e.response.text
            logger.error(f"RingCentral API error: {e.response.status_code} - {error_body}")
            return {"error": str(e), "error_body": error_body, "status_code": e.response.status_code}
        except Exception as e:
            logger.error(f"RingCentral request error: {e}")
            return {"error": str(e)}

    async def get_status(self) -> Dict[str, Any]:
        """Get RingCentral connection status."""
        if not self.is_configured:
            return {
                "connected": False,
                "configured": False,
                "message": "RingCentral credentials not configured",
            }

        token = await self.get_access_token()
        if not token:
            return {
                "connected": False,
                "configured": True,
                "message": "Failed to authenticate with RingCentral",
                "auth_error": getattr(self, '_last_auth_error', None),
            }

        # Test API connection
        result = await self._api_request("GET", "/restapi/v1.0/account/~")
        if result.get("error"):
            return {
                "connected": False,
                "configured": True,
                "message": f"API error: {result.get('error')}",
            }

        return {
            "connected": True,
            "configured": True,
            "account_id": result.get("id"),
            "account_name": result.get("name"),
            "message": "Connected to RingCentral",
        }

    async def make_call(
        self,
        from_number: str,
        to_number: str,
        caller_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Initiate an outbound call (RingOut).

        Args:
            from_number: Extension or phone number to call from
            to_number: Phone number to call
            caller_id: Optional caller ID to display

        Returns:
            Call session information
        """
        # Normalize from_number - extract digits only
        from_digits = ''.join(c for c in from_number if c.isdigit())

        # Detect extension (1-5 digits) vs phone number (6+ digits)
        if len(from_digits) <= 5:
            # It's an extension number - use extensionNumber field
            from_field = {"extensionNumber": from_digits}
        else:
            # It's a phone number - format with +1 country code
            if len(from_digits) == 10:
                from_field = {"phoneNumber": f"+1{from_digits}"}
            elif len(from_digits) == 11 and from_digits.startswith('1'):
                from_field = {"phoneNumber": f"+{from_digits}"}
            else:
                from_field = {"phoneNumber": from_digits}

        # Format to_number with country code
        to_digits = ''.join(c for c in to_number if c.isdigit())
        if len(to_digits) == 10:
            to_formatted = f"+1{to_digits}"
        elif len(to_digits) == 11 and to_digits.startswith('1'):
            to_formatted = f"+{to_digits}"
        else:
            to_formatted = to_digits

        data = {
            "from": from_field,
            "to": {"phoneNumber": to_formatted},
            "playPrompt": False,
        }
        if caller_id:
            data["callerId"] = {"phoneNumber": caller_id}

        logger.info(f"RingOut request data: {data}")

        result = await self._api_request(
            "POST",
            "/restapi/v1.0/account/~/extension/~/ring-out",
            data=data,
        )

        return result

    async def get_call_log(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        direction: Optional[str] = None,
        call_type: Optional[str] = None,
        per_page: int = 100,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Get call log from RingCentral.

        Args:
            date_from: Start date for log query
            date_to: End date for log query
            direction: Filter by direction (Inbound, Outbound)
            call_type: Filter by type (Voice, Fax, SMS)
            per_page: Results per page
            page: Page number

        Returns:
            Call log records
        """
        params = {
            "perPage": per_page,
            "page": page,
            "view": "Detailed",  # Include recordings
        }

        if date_from:
            params["dateFrom"] = date_from.isoformat()
        if date_to:
            params["dateTo"] = date_to.isoformat()
        if direction:
            params["direction"] = direction
        if call_type:
            params["type"] = call_type

        result = await self._api_request(
            "GET",
            "/restapi/v1.0/account/~/extension/~/call-log",
            params=params,
        )

        return result

    async def get_recording(self, recording_id: str) -> Dict[str, Any]:
        """Get recording metadata and content URL."""
        result = await self._api_request(
            "GET",
            f"/restapi/v1.0/account/~/recording/{recording_id}",
        )
        return result

    async def get_recording_content(self, recording_id: str) -> Optional[bytes]:
        """Download recording content."""
        token = await self.get_access_token()
        if not token:
            return None

        try:
            client = await self.get_client()
            response = await client.get(
                f"/restapi/v1.0/account/~/recording/{recording_id}/content",
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"Failed to download recording: {e}")
            return None

    async def get_extensions(self) -> Dict[str, Any]:
        """Get list of extensions (users) in the account."""
        result = await self._api_request(
            "GET",
            "/restapi/v1.0/account/~/extension",
            params={"perPage": 1000},
        )
        return result

    async def get_presence(self, extension_id: str = "~") -> Dict[str, Any]:
        """Get user presence/availability status."""
        result = await self._api_request(
            "GET",
            f"/restapi/v1.0/account/~/extension/{extension_id}/presence",
        )
        return result

    async def set_presence(
        self,
        status: str,
        extension_id: str = "~",
    ) -> Dict[str, Any]:
        """Set user presence status.

        Args:
            status: Availability status (Available, Busy, DoNotDisturb, Offline)
            extension_id: Extension ID or ~ for current user
        """
        result = await self._api_request(
            "POST",
            f"/restapi/v1.0/account/~/extension/{extension_id}/presence",
            data={"userStatus": status},
        )
        return result

    async def create_webhook(
        self,
        event_filters: List[str],
        delivery_url: str,
    ) -> Dict[str, Any]:
        """Create webhook subscription for real-time events.

        Args:
            event_filters: List of event types to subscribe to
            delivery_url: URL to receive webhook notifications

        Event filter examples:
            - /restapi/v1.0/account/~/extension/~/presence
            - /restapi/v1.0/account/~/extension/~/telephony/sessions
            - /restapi/v1.0/account/~/extension/~/message-store
        """
        result = await self._api_request(
            "POST",
            "/restapi/v1.0/subscription",
            data={
                "eventFilters": event_filters,
                "deliveryMode": {
                    "transportType": "WebHook",
                    "address": delivery_url,
                },
                "expiresIn": 604800,  # 7 days
            },
        )
        return result

    async def lookup_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """Look up phone number information."""
        result = await self._api_request(
            "GET",
            "/restapi/v1.0/number-parser/parse",
            params={"phoneNumber": phone_number},
        )
        return result


# Singleton instance
ringcentral_service = RingCentralService()


async def get_ringcentral_service() -> RingCentralService:
    """Dependency injection for RingCentral service."""
    return ringcentral_service
