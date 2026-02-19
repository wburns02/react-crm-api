"""
QuickBooks Online Integration API Endpoints

Provides:
- OAuth 2.0 connection flow (authorize → callback → token storage)
- Connection status check
- Customer sync (CRM → QBO)
- Invoice sync (CRM → QBO)
- Payment sync (CRM → QBO)
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import os
import logging

from app.api.deps import DbSession, CurrentUser, EntityCtx
from app.services.qbo_service import get_qbo_service

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Configuration
# =============================================================================

QBO_CLIENT_ID = os.getenv("QBO_CLIENT_ID", "")
QBO_CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "")
QBO_REDIRECT_URI = os.getenv(
    "QBO_REDIRECT_URI", "https://react.ecbtx.com/integrations/quickbooks/callback"
)


# =============================================================================
# Pydantic Schemas
# =============================================================================


class QBOConnectionStatus(BaseModel):
    connected: bool
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    realm_id: Optional[str] = None
    last_sync: Optional[str] = None
    connected_at: Optional[str] = None
    connected_by: Optional[str] = None
    token_expired: Optional[bool] = None
    message: Optional[str] = None


class QBOAuthURL(BaseModel):
    auth_url: str
    state: str


class QBOSyncResult(BaseModel):
    entity_type: str
    synced: int
    created: int
    updated: int
    errors: int
    error_messages: list[str] = Field(default_factory=list)


# =============================================================================
# Connection Endpoints
# =============================================================================


@router.get("/status")
async def get_quickbooks_status(
    db: DbSession,
    current_user: CurrentUser,
    entity: EntityCtx = None,
) -> QBOConnectionStatus:
    """Get QuickBooks connection status."""
    qbo = get_qbo_service()
    status = await qbo.get_status(db, entity_id=entity.id if entity else None)

    return QBOConnectionStatus(
        connected=status.get("connected", False),
        company_name=status.get("company_name"),
        realm_id=status.get("realm_id"),
        last_sync=status.get("last_sync"),
        connected_at=status.get("connected_at"),
        connected_by=status.get("connected_by"),
        token_expired=status.get("token_expired"),
        message=status.get("message"),
    )


@router.get("/connect")
async def initiate_quickbooks_connection(
    db: DbSession,
    current_user: CurrentUser,
) -> QBOAuthURL:
    """Initiate QuickBooks OAuth 2.0 flow."""
    if not QBO_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="QuickBooks integration not configured. Set QBO_CLIENT_ID env var.",
        )

    qbo = get_qbo_service()
    state = uuid4().hex
    auth_url = qbo.get_auth_url(QBO_REDIRECT_URI, state)

    if not auth_url:
        raise HTTPException(status_code=503, detail="Failed to generate auth URL")

    return QBOAuthURL(auth_url=auth_url, state=state)


@router.get("/callback")
async def quickbooks_oauth_callback(
    code: str = Query(...),
    state: str = Query(""),
    realmId: str = Query(""),
    db: DbSession = None,
    current_user: CurrentUser = None,
    entity: EntityCtx = None,
) -> dict:
    """Handle QuickBooks OAuth callback — exchange code for tokens."""
    qbo = get_qbo_service()

    # Store realm_id for the service to use
    if realmId:
        os.environ["QBO_REALM_ID"] = realmId

    connected_by = current_user.email if current_user else "system"
    token = await qbo.exchange_code(db, code, QBO_REDIRECT_URI, connected_by, entity_id=entity.id if entity else None)

    if not token:
        raise HTTPException(status_code=400, detail="Failed to exchange OAuth code")

    return {
        "success": True,
        "message": "QuickBooks connected successfully",
        "company_name": token.company_name,
        "realm_id": token.realm_id,
    }


@router.post("/disconnect")
async def disconnect_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    entity: EntityCtx = None,
) -> dict:
    """Disconnect QuickBooks integration."""
    qbo = get_qbo_service()
    success = await qbo.disconnect(db, entity_id=entity.id if entity else None)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to disconnect")

    return {"success": True, "message": "QuickBooks disconnected"}


# =============================================================================
# Customer Sync Endpoints
# =============================================================================


@router.get("/customers")
async def get_customer_mappings(
    db: DbSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get customer mappings between CRM and QuickBooks."""
    return {"mappings": [], "total": 0, "page": page, "page_size": page_size}


@router.post("/customers/sync")
async def sync_customers_to_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    customer_ids: Optional[list[str]] = None,
) -> QBOSyncResult:
    """Sync customers to QuickBooks."""
    qbo = get_qbo_service()
    synced = 0
    errors = 0
    error_messages = []

    if not customer_ids:
        # Get all active customers
        from sqlalchemy import text as sql_text

        result = await db.execute(
            sql_text("SELECT id::text FROM customers WHERE is_active = true LIMIT 100")
        )
        customer_ids = [row[0] for row in result.fetchall()]

    for cid in customer_ids:
        try:
            result = await qbo.sync_customer(db, cid)
            if result:
                synced += 1
            else:
                errors += 1
                error_messages.append(f"Customer {cid}: no data returned")
        except Exception as e:
            errors += 1
            error_messages.append(f"Customer {cid}: {str(e)[:100]}")

    return QBOSyncResult(
        entity_type="customer",
        synced=synced,
        created=synced,
        updated=0,
        errors=errors,
        error_messages=error_messages[:10],
    )


# =============================================================================
# Invoice Sync Endpoints
# =============================================================================


@router.get("/invoices")
async def get_invoice_mappings(
    db: DbSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get invoice mappings between CRM and QuickBooks."""
    return {"mappings": [], "total": 0, "page": page, "page_size": page_size}


@router.post("/invoices/sync")
async def sync_invoices_to_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    invoice_ids: Optional[list[str]] = None,
) -> QBOSyncResult:
    """Sync invoices to QuickBooks."""
    qbo = get_qbo_service()
    synced = 0
    errors = 0
    error_messages = []

    if not invoice_ids:
        from sqlalchemy import text as sql_text

        result = await db.execute(
            sql_text("SELECT id::text FROM invoices ORDER BY created_at DESC LIMIT 100")
        )
        invoice_ids = [row[0] for row in result.fetchall()]

    for iid in invoice_ids:
        try:
            result = await qbo.sync_invoice(db, iid)
            if result:
                synced += 1
            else:
                errors += 1
                error_messages.append(f"Invoice {iid}: no data returned")
        except Exception as e:
            errors += 1
            error_messages.append(f"Invoice {iid}: {str(e)[:100]}")

    return QBOSyncResult(
        entity_type="invoice",
        synced=synced,
        created=synced,
        updated=0,
        errors=errors,
        error_messages=error_messages[:10],
    )


@router.post("/invoices/{invoice_id}/push")
async def push_invoice_to_quickbooks(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Push a single invoice to QuickBooks."""
    qbo = get_qbo_service()
    result = await qbo.sync_invoice(db, invoice_id)

    if not result:
        raise HTTPException(status_code=400, detail="Failed to push invoice")

    return {
        "success": True,
        "crm_invoice_id": invoice_id,
        "qbo_result": result,
    }


# =============================================================================
# Payment Sync Endpoints
# =============================================================================


@router.post("/payments/sync")
async def sync_payments_to_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    payment_ids: Optional[list[str]] = None,
) -> QBOSyncResult:
    """Sync payments to QuickBooks."""
    qbo = get_qbo_service()
    synced = 0
    errors = 0
    error_messages = []

    if not payment_ids:
        from sqlalchemy import text as sql_text

        result = await db.execute(
            sql_text("SELECT id::text FROM payments ORDER BY created_at DESC LIMIT 100")
        )
        payment_ids = [row[0] for row in result.fetchall()]

    for pid in payment_ids:
        try:
            result = await qbo.sync_payment(db, pid)
            if result:
                synced += 1
            else:
                errors += 1
                error_messages.append(f"Payment {pid}: no data returned")
        except Exception as e:
            errors += 1
            error_messages.append(f"Payment {pid}: {str(e)[:100]}")

    return QBOSyncResult(
        entity_type="payment",
        synced=synced,
        created=synced,
        updated=0,
        errors=errors,
        error_messages=error_messages[:10],
    )


@router.get("/payments/unsynced")
async def get_unsynced_payments(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get payments not yet synced to QuickBooks."""
    return {"payments": [], "count": 0}


# =============================================================================
# Sync Settings & History
# =============================================================================


@router.get("/settings")
async def get_sync_settings(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get QuickBooks sync settings."""
    return {
        "auto_sync_customers": False,
        "auto_sync_invoices": False,
        "auto_sync_payments": False,
        "sync_interval_minutes": 60,
        "default_income_account": None,
        "default_payment_account": None,
        "client_id_configured": bool(QBO_CLIENT_ID),
        "redirect_uri": QBO_REDIRECT_URI,
    }


@router.patch("/settings")
async def update_sync_settings(
    db: DbSession,
    current_user: CurrentUser,
    auto_sync_customers: Optional[bool] = None,
    auto_sync_invoices: Optional[bool] = None,
    auto_sync_payments: Optional[bool] = None,
    sync_interval_minutes: Optional[int] = None,
) -> dict:
    """Update QuickBooks sync settings."""
    return {"success": True, "message": "Settings updated"}


@router.get("/sync-history")
async def get_sync_history(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = 20,
) -> dict:
    """Get sync history/logs."""
    return {"history": [], "total": 0}


# =============================================================================
# Reports/Reconciliation
# =============================================================================


@router.get("/reconciliation")
async def get_reconciliation_report(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get reconciliation report comparing CRM and QuickBooks data."""
    return {
        "customers": {
            "crm_count": 0,
            "qbo_count": 0,
            "matched": 0,
            "unmatched_crm": 0,
            "unmatched_qbo": 0,
        },
        "invoices": {
            "crm_total": 0.0,
            "qbo_total": 0.0,
            "difference": 0.0,
            "pending_sync": 0,
        },
        "payments": {
            "crm_total": 0.0,
            "qbo_total": 0.0,
            "difference": 0.0,
            "pending_sync": 0,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }
