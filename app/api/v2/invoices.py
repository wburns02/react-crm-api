from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_
from typing import Optional
from datetime import datetime, date
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.invoice import Invoice, InvoiceStatus
from app.models.customer import Customer
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def generate_invoice_number() -> str:
    """Generate a unique invoice number."""
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = uuid.uuid4().hex[:4].upper()
    return f"INV-{date_part}-{random_part}"


# Namespace for deterministic customer UUID generation
# This allows converting integer customer IDs to UUIDs consistently
CUSTOMER_UUID_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def customer_id_to_uuid(customer_id: int) -> uuid.UUID:
    """Convert integer customer ID to deterministic UUID.

    Since invoices.customer_id is UUID but customers.id is Integer,
    we generate a deterministic UUID from the integer.
    """
    return uuid.uuid5(CUSTOMER_UUID_NAMESPACE, str(customer_id))


async def find_customer_by_invoice_uuid(db, invoice_customer_id: uuid.UUID) -> Optional[Customer]:
    """Find the Customer by their customer_uuid (indexed lookup).

    OPTIMIZED: Uses the indexed customer_uuid column for O(1) lookup
    instead of loading all customers.

    Args:
        db: Database session
        invoice_customer_id: The UUID stored in invoice.customer_id

    Returns:
        Customer instance if found, None otherwise
    """
    if not invoice_customer_id:
        return None

    try:
        # Direct indexed lookup - O(1) instead of O(n)
        result = await db.execute(
            select(Customer).where(Customer.customer_uuid == invoice_customer_id)
        )
        return result.scalar_one_or_none()
    except Exception as e:
        logger.warning(f"Error finding customer for invoice UUID: {e}")
        return None


async def build_customer_uuid_map(db, invoice_customer_ids: set) -> dict:
    """Build a mapping of invoice customer UUIDs to Customer objects.

    OPTIMIZED: Uses indexed customer_uuid column with IN clause
    for efficient batch lookup.

    Args:
        db: Database session
        invoice_customer_ids: Set of customer UUIDs from invoices

    Returns:
        Dict mapping invoice customer UUID to Customer instance
    """
    if not invoice_customer_ids:
        return {}

    try:
        # Batch lookup using indexed column - O(log n) per lookup
        result = await db.execute(
            select(Customer).where(Customer.customer_uuid.in_(list(invoice_customer_ids)))
        )
        customers = result.scalars().all()

        # Build map: invoice_uuid -> customer
        uuid_map = {customer.customer_uuid: customer for customer in customers if customer.customer_uuid}

        return uuid_map
    except Exception as e:
        logger.warning(f"Error building customer UUID map: {e}")
        return {}


def invoice_to_response(invoice: Invoice, customer: Optional[Customer] = None) -> dict:
    """Convert Invoice model to response dict.

    Frontend expects subtotal, tax, total, tax_rate fields.
    We calculate these from line_items or use amount as total.

    Args:
        invoice: The Invoice model instance
        customer: Optional Customer model instance for enrichment
    """
    line_items = invoice.line_items or []

    # Calculate subtotal from line items
    subtotal = 0.0
    for item in line_items:
        if isinstance(item, dict):
            subtotal += float(item.get("amount", 0) or 0)

    # Total from amount field, or calculated subtotal
    total = float(invoice.amount) if invoice.amount else subtotal

    # Estimate tax (difference between total and subtotal)
    tax = max(0, total - subtotal)

    # Estimate tax_rate
    tax_rate = (tax / subtotal * 100) if subtotal > 0 else 0

    # Build customer data if available
    customer_name = None
    customer_data = None
    if customer:
        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or None
        # CustomerSummary schema expects: id as str, first_name/last_name as required str
        customer_data = {
            "id": str(customer.id),  # Convert int to string for schema
            "first_name": customer.first_name or "",  # Required, default to empty
            "last_name": customer.last_name or "",  # Required, default to empty
            "email": customer.email,
            "phone": customer.phone,
        }

    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "customer_id": str(invoice.customer_id) if invoice.customer_id else None,
        "customer_name": customer_name,
        "customer": customer_data,
        "work_order_id": str(invoice.work_order_id) if invoice.work_order_id else None,
        "status": invoice.status or "draft",
        "line_items": line_items,
        # Frontend expects these fields:
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax": tax,
        "total": total,
        # Legacy fields
        "amount": float(invoice.amount) if invoice.amount else 0,
        "paid_amount": float(invoice.paid_amount) if invoice.paid_amount else 0,
        "currency": invoice.currency or "USD",
        "issue_date": invoice.issue_date,
        "due_date": invoice.due_date,
        "paid_date": invoice.paid_date,
        "external_payment_link": invoice.external_payment_link,
        "pdf_url": invoice.pdf_url,
        "notes": invoice.notes,
        "terms": None,  # Not stored in DB, but frontend expects it
        "created_at": invoice.created_at,
        "updated_at": invoice.updated_at,
    }


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    customer_id: Optional[str] = None,
    search: Optional[str] = Query(None, description="Search invoice number, customer name, email, phone, address"),
    date_from: Optional[str] = Query(None, description="Filter invoices from this date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Filter invoices until this date (YYYY-MM-DD)"),
):
    """List invoices with pagination, filtering, and search."""
    try:
        # Base query
        query = select(Invoice)

        # Apply status filter
        if status_filter:
            query = query.where(Invoice.status == status_filter)

        if customer_id:
            query = query.where(Invoice.customer_id == uuid.UUID(customer_id))

        # Handle search - requires finding matching customer UUIDs first
        if search:
            search_term = search.strip()
            if search_term:
                # 1. Find customers matching the search term
                customer_query = select(Customer.id).where(
                    or_(
                        Customer.first_name.ilike(f"%{search_term}%"),
                        Customer.last_name.ilike(f"%{search_term}%"),
                        Customer.phone.ilike(f"%{search_term}%"),
                        Customer.email.ilike(f"%{search_term}%"),
                        Customer.address_line1.ilike(f"%{search_term}%"),
                    )
                )
                customer_result = await db.execute(customer_query)
                matching_customer_ids = [row[0] for row in customer_result.fetchall()]

                # Convert matching customer IDs to UUIDs
                matching_customer_uuids = [customer_id_to_uuid(cid) for cid in matching_customer_ids]

                # Apply search filter: invoice_number OR matching customer
                invoice_number_filter = Invoice.invoice_number.ilike(f"%{search_term}%")
                if matching_customer_uuids:
                    query = query.where(or_(invoice_number_filter, Invoice.customer_id.in_(matching_customer_uuids)))
                else:
                    # No customer matches, only search invoice number
                    query = query.where(invoice_number_filter)

        # Apply date range filters (filter by due_date)
        if date_from:
            try:
                from_date = datetime.strptime(date_from, "%Y-%m-%d").date()
                query = query.where(Invoice.due_date >= from_date)
            except ValueError:
                pass  # Invalid date format, skip filter

        if date_to:
            try:
                to_date = datetime.strptime(date_to, "%Y-%m-%d").date()
                query = query.where(Invoice.due_date <= to_date)
            except ValueError:
                pass  # Invalid date format, skip filter

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Invoice.created_at.desc())

        # Execute query
        result = await db.execute(query)
        invoices = result.scalars().all()

        # Build customer UUID map for efficient enrichment (ONE query for all invoices)
        invoice_customer_ids = {inv.customer_id for inv in invoices if inv.customer_id}
        customer_map = await build_customer_uuid_map(db, invoice_customer_ids)

        # Build response items with customer enrichment
        items = []
        for inv in invoices:
            customer = customer_map.get(inv.customer_id) if inv.customer_id else None
            items.append(invoice_to_response(inv, customer))

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing invoices: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single invoice by ID with customer data."""
    try:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        # Fetch customer data to enrich response
        customer = None
        if invoice.customer_id:
            customer = await find_customer_by_invoice_uuid(db, invoice.customer_id)

        return invoice_to_response(invoice, customer)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting invoice: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new invoice."""
    try:
        data = invoice_data.model_dump(exclude_unset=True)

        # Convert integer customer_id to UUID (database column is UUID type)
        data["customer_id"] = customer_id_to_uuid(data["customer_id"])

        # Convert work_order_id string to UUID if provided
        if data.get("work_order_id"):
            data["work_order_id"] = uuid.UUID(data["work_order_id"])

        # Set status to 'draft' using lowercase string for PostgreSQL ENUM type
        # Note: PostgreSQL ENUM expects lowercase values, not Python enum names
        data["status"] = "draft"

        # Remove None values to let DB use defaults
        data = {k: v for k, v in data.items() if v is not None}

        # Generate invoice number if not provided
        if not data.get("invoice_number"):
            data["invoice_number"] = generate_invoice_number()

        # Set issue date if not provided
        if not data.get("issue_date"):
            data["issue_date"] = date.today()

        # Calculate total amount from line items if not provided
        if not data.get("amount"):
            line_items = data.get("line_items", [])
            total = sum(item.get("amount", 0) for item in line_items if isinstance(item, dict))
            data["amount"] = total if total > 0 else 0

        invoice = Invoice(**data)
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)
        return invoice_to_response(invoice)
    except Exception as e:
        logger.error(f"Error creating invoice: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: str,
    invoice_data: InvoiceUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an invoice."""
    try:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        # Update only provided fields
        update_data = invoice_data.model_dump(exclude_unset=True)

        # Convert integer customer_id to UUID if provided
        if "customer_id" in update_data and update_data["customer_id"]:
            update_data["customer_id"] = customer_id_to_uuid(update_data["customer_id"])

        # Convert work_order_id string to UUID if provided
        if "work_order_id" in update_data and update_data["work_order_id"]:
            update_data["work_order_id"] = uuid.UUID(update_data["work_order_id"])

        for field, value in update_data.items():
            setattr(invoice, field, value)

        await db.commit()
        await db.refresh(invoice)
        return invoice_to_response(invoice)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating invoice: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an invoice."""
    try:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        await db.delete(invoice)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting invoice: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
async def send_invoice(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark invoice as sent."""
    try:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        invoice.status = "sent"
        invoice.last_sent_at = datetime.utcnow()
        invoice.sent_count = (invoice.sent_count or 0) + 1

        await db.commit()
        await db.refresh(invoice)
        return invoice_to_response(invoice)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending invoice: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
async def mark_invoice_paid(
    invoice_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark invoice as paid."""
    try:
        result = await db.execute(select(Invoice).where(Invoice.id == uuid.UUID(invoice_id)))
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invoice not found",
            )

        invoice.status = "paid"
        invoice.paid_date = date.today()
        invoice.paid_amount = invoice.amount

        await db.commit()
        await db.refresh(invoice)
        return invoice_to_response(invoice)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking invoice paid: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {type(e).__name__}: {str(e)}"
        )
