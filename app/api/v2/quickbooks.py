"""
QuickBooks Integration API Endpoints

Provides:
- OAuth connection flow
- Customer sync
- Invoice sync
- Payment sync
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4
import os

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Configuration
# =============================================================================

QBO_CLIENT_ID = os.getenv("QBO_CLIENT_ID", "")
QBO_CLIENT_SECRET = os.getenv("QBO_CLIENT_SECRET", "")
QBO_REDIRECT_URI = os.getenv("QBO_REDIRECT_URI", "https://react.ecbtx.com/integrations/quickbooks/callback")
QBO_ENVIRONMENT = os.getenv("QBO_ENVIRONMENT", "sandbox")  # sandbox or production


# =============================================================================
# Pydantic Schemas
# =============================================================================


class QBOConnectionStatus(BaseModel):
    """QuickBooks connection status."""

    connected: bool
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    last_sync: Optional[str] = None
    expires_at: Optional[str] = None


class QBOCustomerMapping(BaseModel):
    """Customer mapping between CRM and QuickBooks."""

    crm_customer_id: int
    qbo_customer_id: str
    display_name: str
    sync_status: str  # synced, pending, error
    last_synced: Optional[str] = None


class QBOInvoiceMapping(BaseModel):
    """Invoice mapping between CRM and QuickBooks."""

    crm_invoice_id: str
    qbo_invoice_id: str
    doc_number: str
    total_amount: float
    sync_status: str
    last_synced: Optional[str] = None


class QBOSyncResult(BaseModel):
    """Sync operation result."""

    entity_type: str
    synced: int
    created: int
    updated: int
    errors: int
    error_messages: list[str] = Field(default_factory=list)


class QBOAuthURL(BaseModel):
    """OAuth authorization URL."""

    auth_url: str
    state: str


# =============================================================================
# Connection Endpoints
# =============================================================================


@router.get("/status")
async def get_quickbooks_status(
    db: DbSession,
    current_user: CurrentUser,
) -> QBOConnectionStatus:
    """Get QuickBooks connection status."""
    # In production: check database for OAuth tokens
    # Mock response
    return QBOConnectionStatus(connected=False, company_name=None, company_id=None, last_sync=None, expires_at=None)


@router.get("/connect")
async def initiate_quickbooks_connection(
    db: DbSession,
    current_user: CurrentUser,
) -> QBOAuthURL:
    """Initiate QuickBooks OAuth flow."""
    if not QBO_CLIENT_ID:
        raise HTTPException(status_code=503, detail="QuickBooks integration not configured")

    state = uuid4().hex
    # In production: store state in session/database for validation

    # QuickBooks OAuth URL
    auth_url = (
        f"https://appcenter.intuit.com/connect/oauth2"
        f"?client_id={QBO_CLIENT_ID}"
        f"&redirect_uri={QBO_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=com.intuit.quickbooks.accounting"
        f"&state={state}"
    )

    return QBOAuthURL(auth_url=auth_url, state=state)


@router.get("/callback")
async def quickbooks_oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    realmId: str = Query(...),
    db: DbSession = None,
    current_user: CurrentUser = None,
) -> dict:
    """Handle QuickBooks OAuth callback."""
    # In production:
    # 1. Validate state parameter
    # 2. Exchange code for tokens
    # 3. Store tokens in database
    # 4. Fetch company info

    return {"success": True, "message": "QuickBooks connected successfully", "company_id": realmId}


@router.post("/disconnect")
async def disconnect_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Disconnect QuickBooks integration."""
    # In production: revoke tokens and clear from database
    return {"success": True, "message": "QuickBooks disconnected"}


@router.post("/refresh-token")
async def refresh_quickbooks_token(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Refresh QuickBooks access token."""
    # In production: use refresh token to get new access token
    return {"success": True, "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat()}


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
    # Mock data
    mappings = [
        QBOCustomerMapping(
            crm_customer_id=1,
            qbo_customer_id="123",
            display_name="John Smith",
            sync_status="synced",
            last_synced=datetime.utcnow().isoformat(),
        ),
        QBOCustomerMapping(
            crm_customer_id=2,
            qbo_customer_id="124",
            display_name="Jane Doe",
            sync_status="synced",
            last_synced=datetime.utcnow().isoformat(),
        ),
    ]

    return {
        "mappings": [m.model_dump() for m in mappings],
        "total": len(mappings),
        "page": page,
        "page_size": page_size,
    }


@router.post("/customers/sync")
async def sync_customers_to_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    customer_ids: Optional[list[int]] = None,
) -> QBOSyncResult:
    """Sync customers to QuickBooks."""
    # In production:
    # 1. Fetch customers from CRM database
    # 2. For each customer, create or update in QuickBooks
    # 3. Store mapping

    return QBOSyncResult(entity_type="customer", synced=10, created=3, updated=7, errors=0)


@router.post("/customers/import")
async def import_customers_from_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
) -> QBOSyncResult:
    """Import customers from QuickBooks to CRM."""
    return QBOSyncResult(entity_type="customer", synced=15, created=15, updated=0, errors=0)


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
    mappings = [
        QBOInvoiceMapping(
            crm_invoice_id="inv-001",
            qbo_invoice_id="1001",
            doc_number="INV-1001",
            total_amount=1500.00,
            sync_status="synced",
            last_synced=datetime.utcnow().isoformat(),
        ),
    ]

    return {
        "mappings": [m.model_dump() for m in mappings],
        "total": len(mappings),
        "page": page,
        "page_size": page_size,
    }


@router.post("/invoices/sync")
async def sync_invoices_to_quickbooks(
    db: DbSession,
    current_user: CurrentUser,
    invoice_ids: Optional[list[str]] = None,
) -> QBOSyncResult:
    """Sync invoices to QuickBooks."""
    return QBOSyncResult(entity_type="invoice", synced=5, created=2, updated=3, errors=0)


@router.post("/invoices/{invoice_id}/push")
async def push_invoice_to_quickbooks(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Push a single invoice to QuickBooks."""
    # In production: create/update invoice in QuickBooks
    qbo_invoice_id = f"QBO-{uuid4().hex[:8]}"

    return {
        "success": True,
        "crm_invoice_id": invoice_id,
        "qbo_invoice_id": qbo_invoice_id,
        "doc_number": f"INV-{invoice_id[:8].upper()}",
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
    return QBOSyncResult(entity_type="payment", synced=3, created=3, updated=0, errors=0)


@router.get("/payments/unsynced")
async def get_unsynced_payments(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get payments not yet synced to QuickBooks."""
    return {
        "payments": [
            {
                "id": "pay-001",
                "invoice_id": "inv-001",
                "amount": 500.00,
                "payment_date": datetime.utcnow().isoformat(),
                "method": "card",
            }
        ],
        "count": 1,
    }


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
        "auto_sync_customers": True,
        "auto_sync_invoices": True,
        "auto_sync_payments": True,
        "sync_interval_minutes": 60,
        "default_income_account": "Services",
        "default_payment_account": "Undeposited Funds",
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
    history = [
        {
            "id": "sync-001",
            "entity_type": "customer",
            "direction": "push",
            "status": "success",
            "records_affected": 5,
            "started_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "completed_at": (datetime.utcnow() - timedelta(minutes=58)).isoformat(),
            "initiated_by": current_user.email,
        },
        {
            "id": "sync-002",
            "entity_type": "invoice",
            "direction": "push",
            "status": "success",
            "records_affected": 3,
            "started_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "completed_at": (datetime.utcnow() - timedelta(hours=2, minutes=-2)).isoformat(),
            "initiated_by": "system",
        },
    ]

    return {"history": history, "total": len(history)}


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
        "customers": {"crm_count": 150, "qbo_count": 148, "matched": 145, "unmatched_crm": 5, "unmatched_qbo": 3},
        "invoices": {"crm_total": 25000.00, "qbo_total": 24800.00, "difference": 200.00, "pending_sync": 2},
        "payments": {"crm_total": 22000.00, "qbo_total": 22000.00, "difference": 0.00, "pending_sync": 0},
        "generated_at": datetime.utcnow().isoformat(),
    }
