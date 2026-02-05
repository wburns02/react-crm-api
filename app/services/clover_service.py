"""
Clover payment service for handling pre-authorizations, captures,
and REST API data access (merchant info, orders, payments, items).

Supports both live Clover API and test mode for development.
"""

import logging
import uuid
from decimal import Decimal
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
    """Service for Clover payment processing and REST API data access."""

    # Ecommerce API endpoints (for charges/refunds - requires ecommerce key)
    SANDBOX_URL = "https://scl-sandbox.dev.clover.com"
    PRODUCTION_URL = "https://scl.clover.com"

    # REST API endpoints (for reading merchant data - works with any API key)
    REST_SANDBOX_URL = "https://apisandbox.dev.clover.com"
    REST_PRODUCTION_URL = "https://api.clover.com"

    def __init__(self):
        self.merchant_id = getattr(settings, "CLOVER_MERCHANT_ID", None)
        self.api_key = getattr(settings, "CLOVER_API_KEY", None)
        self.environment = getattr(settings, "CLOVER_ENVIRONMENT", "sandbox")

        self.base_url = self.PRODUCTION_URL if self.environment == "production" else self.SANDBOX_URL
        self.rest_url = self.REST_PRODUCTION_URL if self.environment == "production" else self.REST_SANDBOX_URL

    def _get_headers(self) -> dict:
        """Get headers for Clover API requests."""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        """Check if Clover is properly configured."""
        return bool(self.merchant_id and self.api_key)

    # =========================================================================
    # REST API Methods (read-only, works with current token)
    # =========================================================================

    async def get_merchant(self) -> dict | None:
        """Get merchant profile from Clover REST API."""
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/current",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/payments",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/payments/{payment_id}",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/orders",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/orders/{order_id}",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/items",
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
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.rest_url}/v3/merchants/{self.merchant_id}/customers",
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
                    f"{self.base_url}/v1/charges",
                    headers=self._get_headers(),
                    timeout=10.0,
                )
                # 405 = method not allowed (GET on POST endpoint) means we have access
                # 401 = unauthorized means no ecommerce access
                return resp.status_code != 401
        except Exception:
            return False

    async def preauthorize(
        self, amount_cents: int, token: str, description: str = "Service pre-authorization", test_mode: bool = False
    ) -> PaymentResult:
        """
        Pre-authorize a payment (hold funds without capturing).

        Args:
            amount_cents: Amount in cents (e.g., 77500 for $775.00)
            token: Clover card token from frontend
            description: Description for the charge
            test_mode: If True, simulate without calling Clover

        Returns:
            PaymentResult with charge_id if successful
        """
        if test_mode:
            # Simulate successful pre-auth for testing
            fake_charge_id = f"test_ch_{uuid.uuid4().hex[:16]}"
            logger.info(f"TEST MODE: Simulated pre-auth of ${amount_cents / 100:.2f}, charge_id={fake_charge_id}")
            return PaymentResult(success=True, charge_id=fake_charge_id, is_test=True)

        if not self.is_configured():
            logger.error("Clover not configured - missing merchant_id or api_key")
            return PaymentResult(success=False, error_message="Payment system not configured")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/charges",
                    headers=self._get_headers(),
                    json={
                        "amount": amount_cents,
                        "currency": "usd",
                        "capture": False,  # Pre-auth only, don't capture yet
                        "source": token,
                        "description": description,
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Pre-auth successful: ${amount_cents / 100:.2f}, charge_id={data.get('id')}")
                    return PaymentResult(success=True, charge_id=data.get("id"), is_test=False)
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Payment failed")
                    logger.error(f"Pre-auth failed: {error_msg}")
                    return PaymentResult(success=False, error_message=error_msg)

        except Exception as e:
            logger.error(f"Pre-auth exception: {e}")
            return PaymentResult(success=False, error_message=str(e))

    async def capture(self, charge_id: str, amount_cents: int, test_mode: bool = False) -> PaymentResult:
        """
        Capture a pre-authorized payment.

        Args:
            charge_id: The charge ID from pre-authorization
            amount_cents: Final amount to capture (can be less than pre-auth)
            test_mode: If True, simulate without calling Clover

        Returns:
            PaymentResult indicating success or failure
        """
        if test_mode or charge_id.startswith("test_"):
            logger.info(f"TEST MODE: Simulated capture of ${amount_cents / 100:.2f} for charge {charge_id}")
            return PaymentResult(success=True, charge_id=charge_id, is_test=True)

        if not self.is_configured():
            return PaymentResult(success=False, error_message="Payment system not configured")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v1/charges/{charge_id}/capture",
                    headers=self._get_headers(),
                    json={
                        "amount": amount_cents,
                    },
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
        """
        Refund a captured payment.

        Args:
            charge_id: The charge ID to refund
            amount_cents: Amount to refund (None for full refund)
            test_mode: If True, simulate without calling Clover

        Returns:
            PaymentResult indicating success or failure
        """
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
                    f"{self.base_url}/v1/refunds", headers=self._get_headers(), json=payload, timeout=30.0
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
