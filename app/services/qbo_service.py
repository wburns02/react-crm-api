"""
QuickBooks Online API service.

Handles OAuth 2.0 token management, customer sync, invoice sync, and payment sync.
Follows same pattern as clover_service.py (dynamic token resolution: DB → env fallback).
"""
import logging
import httpx
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.qbo_oauth import QBOOAuthToken

logger = logging.getLogger(__name__)

# QBO API base URLs
QBO_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
QBO_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
QBO_API_BASE = "https://quickbooks.api.intuit.com/v3"
QBO_SANDBOX_API_BASE = "https://sandbox-quickbooks.api.intuit.com/v3"


class QBOService:
    """QuickBooks Online API client with automatic token refresh."""

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=30.0)

    async def _get_token(self, db: AsyncSession, entity_id=None) -> Optional[QBOOAuthToken]:
        """Get active QBO OAuth token from DB, optionally scoped by entity_id."""
        try:
            query = select(QBOOAuthToken).where(QBOOAuthToken.is_active == True)
            if entity_id:
                query = query.where(QBOOAuthToken.entity_id == entity_id)
            result = await db.execute(
                query.order_by(QBOOAuthToken.created_at.desc()).limit(1)
            )
            return result.scalar_one_or_none()
        except Exception:
            logger.debug("QBO token table may not exist yet", exc_info=True)
            return None

    async def _get_access_token(self, db: AsyncSession, entity_id=None) -> tuple[Optional[str], Optional[str]]:
        """Get access token and realm_id. Refreshes if expired."""
        token = await self._get_token(db, entity_id=entity_id)
        if token:
            # Check if token needs refresh (expires within 5 min)
            if token.expires_at and token.expires_at < datetime.utcnow() + timedelta(minutes=5):
                refreshed = await self._refresh_token(db, token)
                if refreshed:
                    return refreshed.access_token, refreshed.realm_id
            return token.access_token, token.realm_id

        # Fallback to env vars
        access_token = getattr(settings, "QBO_ACCESS_TOKEN", None)
        realm_id = getattr(settings, "QBO_REALM_ID", None)
        if access_token and realm_id:
            return access_token, realm_id

        return None, None

    async def _refresh_token(self, db: AsyncSession, token: QBOOAuthToken) -> Optional[QBOOAuthToken]:
        """Refresh an expired access token using refresh_token."""
        client_id = getattr(settings, "QBO_CLIENT_ID", None)
        client_secret = getattr(settings, "QBO_CLIENT_SECRET", None)
        if not client_id or not client_secret:
            logger.warning("QBO_CLIENT_ID or QBO_CLIENT_SECRET not set, cannot refresh")
            return None

        try:
            response = await self._client.post(
                QBO_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            token.access_token = data["access_token"]
            token.refresh_token = data.get("refresh_token", token.refresh_token)
            token.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))
            token.refresh_token_expires_at = datetime.utcnow() + timedelta(
                seconds=data.get("x_refresh_token_expires_in", 8726400)
            )
            await db.commit()
            await db.refresh(token)
            logger.info("QBO token refreshed successfully")
            return token
        except Exception:
            logger.error("Failed to refresh QBO token", exc_info=True)
            return None

    async def _api_request(
        self, db: AsyncSession, method: str, endpoint: str, json_data: dict = None
    ) -> Optional[dict]:
        """Make authenticated QBO API request."""
        access_token, realm_id = await self._get_access_token(db)
        if not access_token or not realm_id:
            return None

        use_sandbox = getattr(settings, "QBO_SANDBOX", False)
        base_url = QBO_SANDBOX_API_BASE if use_sandbox else QBO_API_BASE
        url = f"{base_url}/company/{realm_id}/{endpoint}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            response = await self._client.request(
                method, url, headers=headers, json=json_data
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"QBO API error {e.response.status_code}: {e.response.text[:200]}")
            raise
        except Exception:
            logger.error("QBO API request failed", exc_info=True)
            raise

    # ── OAuth Flow ──────────────────────────────────────────────

    def get_auth_url(self, redirect_uri: str, state: str = "") -> Optional[str]:
        """Generate QBO OAuth authorization URL."""
        client_id = getattr(settings, "QBO_CLIENT_ID", None)
        if not client_id:
            return None

        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": "com.intuit.quickbooks.accounting",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{QBO_AUTH_URL}?{query}"

    async def exchange_code(
        self, db: AsyncSession, code: str, redirect_uri: str, connected_by: str = "", entity_id=None
    ) -> Optional[QBOOAuthToken]:
        """Exchange authorization code for tokens."""
        client_id = getattr(settings, "QBO_CLIENT_ID", None)
        client_secret = getattr(settings, "QBO_CLIENT_SECRET", None)
        realm_id = getattr(settings, "QBO_REALM_ID", None)

        if not client_id or not client_secret:
            logger.error("QBO_CLIENT_ID/SECRET not configured")
            return None

        try:
            response = await self._client.post(
                QBO_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            # Deactivate any existing tokens for this entity
            if entity_id:
                await db.execute(
                    text("UPDATE qbo_oauth_tokens SET is_active = false WHERE is_active = true AND entity_id = :eid"),
                    {"eid": str(entity_id)},
                )
            else:
                await db.execute(
                    text("UPDATE qbo_oauth_tokens SET is_active = false WHERE is_active = true AND entity_id IS NULL")
                )

            import uuid as uuid_module
            token = QBOOAuthToken(
                id=uuid_module.uuid4(),
                realm_id=realm_id or "unknown",
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600)),
                refresh_token_expires_at=datetime.utcnow() + timedelta(
                    seconds=data.get("x_refresh_token_expires_in", 8726400)
                ),
                is_active=True,
                connected_by=connected_by,
                entity_id=entity_id,
            )
            db.add(token)
            await db.commit()
            await db.refresh(token)

            # Fetch company info
            try:
                info = await self._api_request(db, "GET", "companyinfo/" + token.realm_id)
                if info and "CompanyInfo" in info:
                    token.company_name = info["CompanyInfo"].get("CompanyName")
                    await db.commit()
            except Exception:
                pass

            return token
        except Exception:
            logger.error("QBO code exchange failed", exc_info=True)
            return None

    async def disconnect(self, db: AsyncSession, entity_id=None) -> bool:
        """Deactivate QBO tokens, optionally scoped by entity."""
        try:
            if entity_id:
                await db.execute(
                    text("UPDATE qbo_oauth_tokens SET is_active = false WHERE is_active = true AND entity_id = :eid"),
                    {"eid": str(entity_id)},
                )
            else:
                await db.execute(
                    text("UPDATE qbo_oauth_tokens SET is_active = false WHERE is_active = true AND entity_id IS NULL")
                )
            await db.commit()
            return True
        except Exception:
            logger.error("Failed to disconnect QBO", exc_info=True)
            return False

    # ── Status ──────────────────────────────────────────────────

    async def get_status(self, db: AsyncSession, entity_id=None) -> dict:
        """Get QBO connection status."""
        token = await self._get_token(db, entity_id=entity_id)
        if not token:
            return {
                "connected": False,
                "message": "Not connected to QuickBooks",
            }

        is_expired = token.expires_at and token.expires_at < datetime.utcnow()
        return {
            "connected": True,
            "realm_id": token.realm_id,
            "company_name": token.company_name,
            "connected_by": token.connected_by,
            "connected_at": token.created_at.isoformat() if token.created_at else None,
            "last_sync": token.last_sync_at.isoformat() if token.last_sync_at else None,
            "token_expired": is_expired,
        }

    # ── Customer Sync ───────────────────────────────────────────

    async def sync_customer(self, db: AsyncSession, customer_id: str) -> Optional[dict]:
        """Sync a CRM customer to QBO."""
        # Fetch customer from DB
        result = await db.execute(
            text("""
                SELECT id::text, first_name, last_name, email, phone,
                       address_line1, city, state, postal_code
                FROM customers WHERE id = :id
            """),
            {"id": customer_id},
        )
        row = result.fetchone()
        if not row:
            return None

        display_name = f"{row[1] or ''} {row[2] or ''}".strip()

        qbo_customer = {
            "DisplayName": display_name,
            "GivenName": row[1] or "",
            "FamilyName": row[2] or "",
            "PrimaryEmailAddr": {"Address": row[3]} if row[3] else None,
            "PrimaryPhone": {"FreeFormNumber": row[4]} if row[4] else None,
        }

        if row[5]:  # address
            qbo_customer["BillAddr"] = {
                "Line1": row[5],
                "City": row[6] or "",
                "CountrySubDivisionCode": row[7] or "TX",
                "PostalCode": row[8] or "",
            }

        # Remove None values
        qbo_customer = {k: v for k, v in qbo_customer.items() if v is not None}

        try:
            result = await self._api_request(db, "POST", "customer", qbo_customer)
            return result
        except Exception:
            logger.error(f"Failed to sync customer {customer_id}", exc_info=True)
            return None

    # ── Invoice Sync ────────────────────────────────────────────

    async def sync_invoice(self, db: AsyncSession, invoice_id: str) -> Optional[dict]:
        """Sync a CRM invoice to QBO."""
        result = await db.execute(
            text("""
                SELECT i.id::text, i.invoice_number, i.amount, i.status,
                       i.due_date, i.line_items, i.notes,
                       c.first_name, c.last_name
                FROM invoices i
                LEFT JOIN customers c ON i.customer_id = c.id
                WHERE i.id = :id
            """),
            {"id": invoice_id},
        )
        row = result.fetchone()
        if not row:
            return None

        # Build QBO invoice (simplified - uses SalesItemLineDetail)
        line_items = []
        if row[5]:  # line_items JSON
            import json
            items = json.loads(row[5]) if isinstance(row[5], str) else row[5]
            for item in items:
                line_items.append({
                    "DetailType": "SalesItemLineDetail",
                    "Amount": float(item.get("total", item.get("amount", 0))),
                    "Description": item.get("description", item.get("service", "")),
                    "SalesItemLineDetail": {
                        "Qty": float(item.get("quantity", 1)),
                        "UnitPrice": float(item.get("rate", item.get("unit_price", 0))),
                    },
                })

        if not line_items:
            line_items.append({
                "DetailType": "SalesItemLineDetail",
                "Amount": float(row[2] or 0),
                "Description": f"Invoice {row[1]}",
                "SalesItemLineDetail": {"Qty": 1, "UnitPrice": float(row[2] or 0)},
            })

        qbo_invoice = {
            "Line": line_items,
            "DocNumber": row[1],
        }

        if row[4]:  # due_date
            qbo_invoice["DueDate"] = str(row[4])

        if row[6]:  # notes
            qbo_invoice["CustomerMemo"] = {"value": str(row[6])[:1000]}

        try:
            result = await self._api_request(db, "POST", "invoice", qbo_invoice)
            return result
        except Exception:
            logger.error(f"Failed to sync invoice {invoice_id}", exc_info=True)
            return None

    # ── Payment Sync ────────────────────────────────────────────

    async def sync_payment(self, db: AsyncSession, payment_id: str) -> Optional[dict]:
        """Sync a CRM payment to QBO."""
        result = await db.execute(
            text("""
                SELECT id::text, amount, payment_method, payment_date, notes
                FROM payments WHERE id = :id
            """),
            {"id": payment_id},
        )
        row = result.fetchone()
        if not row:
            return None

        qbo_payment = {
            "TotalAmt": float(row[1] or 0),
            "PaymentMethodRef": {"value": row[2] or "Cash"},
        }

        if row[3]:
            qbo_payment["TxnDate"] = str(row[3])

        try:
            result = await self._api_request(db, "POST", "payment", qbo_payment)
            return result
        except Exception:
            logger.error(f"Failed to sync payment {payment_id}", exc_info=True)
            return None


# Singleton
_qbo_service: Optional[QBOService] = None


def get_qbo_service() -> QBOService:
    global _qbo_service
    if _qbo_service is None:
        _qbo_service = QBOService()
    return _qbo_service
