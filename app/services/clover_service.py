"""
Clover payment service for handling OAuth 2.0, pre-authorizations, captures,
refunds, and REST API data access (merchant info, orders, payments, items).

Supports:
- OAuth 2.0 authorization code grant flow
- Dynamic token resolution: DB OAuth token → env var fallback
- Both live Clover API and test mode for development
- Ecommerce API (charges/refunds) with OAuth tokens
- Webhook signature verification
"""

import logging
import uuid
import hmac
import hashlib
from typing import Optional
from dataclasses import dataclass
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PaymentResult:
    """Result of a payment operation."""

    success: bool
    charge_id: Optional[str] = None
    error_message: Optional[str] = None
    is_test: bool = False


class CloverService:
    """Service for Clover payment processing and REST API data access.

    Token resolution order:
    1. OAuth token from database (if available)
    2. Static API key from CLOVER_API_KEY env var (fallback)
    """

    # Ecommerce API endpoints (for charges/refunds)
    SANDBOX_ECOMMERCE_URL = "https://scl-sandbox.dev.clover.com"
    PRODUCTION_ECOMMERCE_URL = "https://scl.clover.com"

    # REST API endpoints (for reading merchant data)
    REST_SANDBOX_URL = "https://apisandbox.dev.clover.com"
    REST_PRODUCTION_URL = "https://api.clover.com"

    # OAuth endpoints
    SANDBOX_AUTH_URL = "https://sandbox.dev.clover.com/oauth/v2/authorize"
    PRODUCTION_AUTH_URL = "https://www.clover.com/oauth/v2/authorize"
    SANDBOX_TOKEN_URL = "https://sandbox.dev.clover.com/oauth/v2/token"
    PRODUCTION_TOKEN_URL = "https://api.clover.com/oauth/v2/token"

    def __init__(self):
        self.merchant_id = getattr(settings, "CLOVER_MERCHANT_ID", None)
        self.api_key = getattr(settings, "CLOVER_API_KEY", None)
        self.environment = getattr(settings, "CLOVER_ENVIRONMENT", "sandbox")
        self.client_id = getattr(settings, "CLOVER_CLIENT_ID", None)
        self.client_secret = getattr(settings, "CLOVER_CLIENT_SECRET", None)
        self.redirect_uri = getattr(settings, "CLOVER_REDIRECT_URI", None)

        # Set URLs based on environment
        is_prod = self.environment == "production"
        self.ecommerce_url = self.PRODUCTION_ECOMMERCE_URL if is_prod else self.SANDBOX_ECOMMERCE_URL
        self.rest_url = self.REST_PRODUCTION_URL if is_prod else self.REST_SANDBOX_URL
        self.auth_url = self.PRODUCTION_AUTH_URL if is_prod else self.SANDBOX_AUTH_URL
        self.token_url = self.PRODUCTION_TOKEN_URL if is_prod else self.SANDBOX_TOKEN_URL

        # Cache for OAuth token (loaded from DB on first use)
        self._oauth_token: Optional[str] = None
        self._oauth_merchant_id: Optional[str] = None

    def _get_active_token(self) -> Optional[str]:
        """Get the active API token (OAuth token or env var fallback)."""
        if self._oauth_token:
            return self._oauth_token
        return self.api_key

    def _get_active_merchant_id(self) -> Optional[str]:
        """Get the active merchant ID (from OAuth or env var)."""
        if self._oauth_merchant_id:
            return self._oauth_merchant_id
        return self.merchant_id

    def set_oauth_token(self, token: str, merchant_id: Optional[str] = None):
        """Set OAuth token from database lookup (called by API endpoints)."""
        self._oauth_token = token
        if merchant_id:
            self._oauth_merchant_id = merchant_id

    def clear_oauth_token(self):
        """Clear cached OAuth token."""
        self._oauth_token = None
        self._oauth_merchant_id = None

    def _get_headers(self) -> dict:
        """Get headers for Clover API requests."""
        token = self._get_active_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        """Check if Clover is properly configured (via OAuth or env var)."""
        has_token = bool(self._get_active_token())
        has_merchant = bool(self._get_active_merchant_id())
        return has_token and has_merchant

    def is_oauth_configured(self) -> bool:
        """Check if OAuth 2.0 flow is configured."""
        return bool(self.client_id and self.client_secret)

    def has_oauth_token(self) -> bool:
        """Check if an OAuth token is currently set."""
        return bool(self._oauth_token)

    # =========================================================================
    # OAuth 2.0 Flow
    # =========================================================================

    def get_authorization_url(self, state: Optional[str] = None) -> Optional[str]:
        """Generate Clover OAuth2 authorization URL."""
        if not self.client_id:
            return None

        redirect = self.redirect_uri
        if not redirect:
            # Default to backend callback
            frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
            redirect = f"{frontend_url}/integrations?clover=callback"

        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect,
            "response_type": "code",
        }
        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.auth_url}?{query}"

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for access token.

        Returns dict with: access_token, merchant_id (if available), error (if failed)
        """
        if not self.client_id or not self.client_secret:
            return {"error": "OAuth not configured (missing client_id or client_secret)"}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.token_url,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code": code,
                    },
                    timeout=30.0,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    logger.info(f"OAuth token exchange successful")
                    return {
                        "access_token": data.get("access_token"),
                        "merchant_id": data.get("merchant_id"),
                    }
                else:
                    error_text = resp.text
                    logger.error(f"OAuth token exchange failed: {resp.status_code} - {error_text}")
                    return {"error": f"Token exchange failed: {error_text}"}

        except Exception as e:
            logger.error(f"OAuth token exchange exception: {e}")
            return {"error": str(e)}

    # =========================================================================
    # Webhook Verification
    # =========================================================================

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Clover webhook signature using client_secret as HMAC key."""
        if not self.client_secret:
            logger.warning("Cannot verify webhook: no client_secret configured")
            return False

        expected = hmac.new(
            self.client_secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    # =========================================================================
    # REST API Methods (read-only, works with any valid token)
    # =========================================================================

    async def get_merchant(self) -> dict | None:
        """Get merchant profile from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}",
                    headers=self._get_headers(),
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"get_merchant failed: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"get_merchant exception: {e}")
            return None

    async def list_payments(self, limit: int = 50, offset: int = 0) -> dict | None:
        """List payments from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/payments",
                    headers=self._get_headers(),
                    params={"limit": limit, "offset": offset, "expand": "tender"},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"list_payments failed: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"list_payments exception: {e}")
            return None

    async def get_payment(self, payment_id: str) -> dict | None:
        """Get a single payment from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/payments/{payment_id}",
                    headers=self._get_headers(),
                    params={"expand": "tender,order"},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.error(f"get_payment exception: {e}")
            return None

    async def list_orders(self, limit: int = 50, offset: int = 0) -> dict | None:
        """List orders from Clover REST API with line items."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/orders",
                    headers=self._get_headers(),
                    params={"limit": limit, "offset": offset, "expand": "lineItems"},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"list_orders failed: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"list_orders exception: {e}")
            return None

    async def get_order(self, order_id: str) -> dict | None:
        """Get a single order from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/orders/{order_id}",
                    headers=self._get_headers(),
                    params={"expand": "lineItems,payments"},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.error(f"get_order exception: {e}")
            return None

    async def list_items(self) -> dict | None:
        """List inventory items (service catalog) from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/items",
                    headers=self._get_headers(),
                    params={"limit": 100},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"list_items failed: {resp.status_code}")
                return None
        except Exception as e:
            logger.error(f"list_items exception: {e}")
            return None

    async def list_customers(self, limit: int = 100) -> dict | None:
        """List customers from Clover REST API."""
        if not self.is_configured():
            return None
        merchant_id = self._get_active_merchant_id()
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{merchant_id}/customers",
                    headers=self._get_headers(),
                    params={"limit": limit},
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception as e:
            logger.error(f"list_customers exception: {e}")
            return None

    async def check_ecommerce_access(self) -> bool:
        """Test if ecommerce API (scl.clover.com) is accessible with current key."""
        if not self.is_configured():
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.ecommerce_url}/v1/charges",
                    headers=self._get_headers(),
                    timeout=10.0,
                )
                # 405 = method not allowed (GET on POST endpoint) means we have access
                # 401 = unauthorized means no ecommerce access
                return resp.status_code != 401
        except Exception:
            return False

    # =========================================================================
    # Ecommerce API Methods (charges, captures, refunds)
    # =========================================================================

    async def create_charge(
        self,
        amount_cents: int,
        token: str,
        description: str = "Service payment",
        capture: bool = True,
        test_mode: bool = False,
    ) -> PaymentResult:
        """Create a charge (with optional immediate capture).

        Args:
            amount_cents: Amount in cents (e.g., 77500 for $775.00)
            token: Clover card token from frontend SDK
            description: Description for the charge
            capture: True = charge immediately, False = pre-auth only
            test_mode: If True, simulate without calling Clover
        """
        if test_mode:
            fake_charge_id = f"test_ch_{uuid.uuid4().hex[:16]}"
            logger.info(f"TEST MODE: Simulated charge of ${amount_cents / 100:.2f}, charge_id={fake_charge_id}")
            return PaymentResult(success=True, charge_id=fake_charge_id, is_test=True)

        if not self.is_configured():
            logger.error("Clover not configured - missing merchant_id or api_key")
            return PaymentResult(success=False, error_message="Payment system not configured")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ecommerce_url}/v1/charges",
                    headers=self._get_headers(),
                    json={
                        "amount": amount_cents,
                        "currency": "usd",
                        "capture": capture,
                        "source": token,
                        "description": description,
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    action = "Charge" if capture else "Pre-auth"
                    logger.info(f"{action} successful: ${amount_cents / 100:.2f}, charge_id={data.get('id')}")
                    return PaymentResult(success=True, charge_id=data.get("id"), is_test=False)
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Payment failed")
                    logger.error(f"Charge failed: {error_msg}")
                    return PaymentResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Charge exception: {e}")
            return PaymentResult(success=False, error_message=str(e))

    async def preauthorize(
        self, amount_cents: int, token: str, description: str = "Service pre-authorization", test_mode: bool = False
    ) -> PaymentResult:
        """Pre-authorize a payment (hold funds without capturing)."""
        return await self.create_charge(
            amount_cents=amount_cents,
            token=token,
            description=description,
            capture=False,
            test_mode=test_mode,
        )

    async def capture(self, charge_id: str, amount_cents: int, test_mode: bool = False) -> PaymentResult:
        """Capture a pre-authorized payment."""
        if test_mode or charge_id.startswith("test_"):
            logger.info(f"TEST MODE: Simulated capture of ${amount_cents / 100:.2f} for charge {charge_id}")
            return PaymentResult(success=True, charge_id=charge_id, is_test=True)

        if not self.is_configured():
            return PaymentResult(success=False, error_message="Payment system not configured")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ecommerce_url}/v1/charges/{charge_id}/capture",
                    headers=self._get_headers(),
                    json={"amount": amount_cents},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info(f"Capture successful: ${amount_cents / 100:.2f} for charge {charge_id}")
                    return PaymentResult(success=True, charge_id=charge_id, is_test=False)
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Capture failed")
                    logger.error(f"Capture failed: {error_msg}")
                    return PaymentResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Capture exception: {e}")
            return PaymentResult(success=False, error_message=str(e))

    async def refund(
        self, charge_id: str, amount_cents: Optional[int] = None, test_mode: bool = False
    ) -> PaymentResult:
        """Refund a captured payment (full or partial)."""
        if test_mode or charge_id.startswith("test_"):
            logger.info(f"TEST MODE: Simulated refund for charge {charge_id}")
            return PaymentResult(success=True, charge_id=charge_id, is_test=True)

        if not self.is_configured():
            return PaymentResult(success=False, error_message="Payment system not configured")

        try:
            async with httpx.AsyncClient() as client:
                payload = {"charge": charge_id}
                if amount_cents:
                    payload["amount"] = amount_cents

                response = await client.post(
                    f"{self.ecommerce_url}/v1/refunds",
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30.0,
                )

                if response.status_code == 200:
                    logger.info(f"Refund successful for charge {charge_id}")
                    return PaymentResult(success=True, charge_id=charge_id, is_test=False)
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Refund failed")
                    logger.error(f"Refund failed: {error_msg}")
                    return PaymentResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Refund exception: {e}")
            return PaymentResult(success=False, error_message=str(e))


# Singleton instance
clover_service = CloverService()


def get_clover_service() -> CloverService:
    """Get the Clover service instance."""
    return clover_service
