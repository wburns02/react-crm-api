from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.invoice import Invoice
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
    # Format: INV-YYYYMMDD-XXXX (random suffix)
    date_part = datetime.now().strftime("%Y%m%d")
    random_part = uuid.uuid4().hex[:4].upper()
    return f"INV-{date_part}-{random_part}"


def invoice_to_response(invoice: Invoice) -> dict:
    """Convert Invoice model to response dict with string IDs."""
    customer_data = None
    customer_name = None

    if invoice.customer:
        customer_name = f"{invoice.customer.first_name} {invoice.customer.last_name}"
        customer_data = {
            "id": str(invoice.customer.id),
            "first_name": invoice.customer.first_name,
            "last_name": invoice.customer.last_name,
            "email": invoice.customer.email,
            "phone": invoice.customer.phone,
        }

    return {
        "id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "customer_id": str(invoice.customer_id),
        "customer_name": customer_name,
        "customer": customer_data,
        "work_order_id": str(invoice.work_order_id) if invoice.work_order_id else None,
        "status": invoice.status,
        "line_items": invoice.line_items or [],
        "subtotal": invoice.subtotal or 0,
        "tax_rate": invoice.tax_rate or 0,
        "tax": invoice.tax or 0,
        "total": invoice.total or 0,
        "due_date": invoice.due_date,
        "paid_date": invoice.paid_date,
        "notes": invoice.notes,
        "terms": invoice.terms,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
        "updated_at": invoice.updated_at.isoformat() if invoice.updated_at else None,
    }


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """List invoices with pagination and filtering."""
    try:
        # Base query with customer eager loading
        query = select(Invoice).options(selectinload(Invoice.customer))

        # Apply filters
        if status:
            query = query.where(Invoice.status == status)

        if customer_id:
            query = query.where(Invoice.customer_id == customer_id)

        if date_from:
            query = query.where(Invoice.created_at >= date_from)

        if date_to:
            query = query.where(Invoice.created_at <= date_to)

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

        return {
            "items": [invoice_to_response(inv) for inv in invoices],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing invoices: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single invoice by ID."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    return invoice_to_response(invoice)


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new invoice."""
    # Verify customer exists
    customer_result = await db.execute(
        select(Customer).where(Customer.id == invoice_data.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Generate invoice number
    invoice_number = generate_invoice_number()

    # Convert line items to dict format
    line_items = [item.model_dump() for item in invoice_data.line_items]

    invoice = Invoice(
        invoice_number=invoice_number,
        customer_id=invoice_data.customer_id,
        work_order_id=invoice_data.work_order_id,
        status=invoice_data.status,
        line_items=line_items,
        subtotal=invoice_data.subtotal or 0,
        tax_rate=invoice_data.tax_rate or 0,
        tax=invoice_data.tax or 0,
        total=invoice_data.total or 0,
        due_date=invoice_data.due_date,
        notes=invoice_data.notes,
        terms=invoice_data.terms,
    )

    # Recalculate totals if needed
    invoice.calculate_totals()

    db.add(invoice)
    await db.commit()

    # Reload with customer relationship
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice.id)
    )
    invoice = result.scalar_one()

    return invoice_to_response(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an invoice."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    # Update only provided fields
    update_data = invoice_data.model_dump(exclude_unset=True)

    # Convert line items if provided
    if 'line_items' in update_data and update_data['line_items']:
        update_data['line_items'] = [
            item.model_dump() if hasattr(item, 'model_dump') else item
            for item in update_data['line_items']
        ]

    for field, value in update_data.items():
        setattr(invoice, field, value)

    # Recalculate totals if line items or tax rate changed
    if 'line_items' in update_data or 'tax_rate' in update_data:
        invoice.calculate_totals()

    await db.commit()
    await db.refresh(invoice)
    return invoice_to_response(invoice)


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(
    invoice_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an invoice."""
    result = await db.execute(select(Invoice).where(Invoice.id == invoice_id))
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    await db.delete(invoice)
    await db.commit()


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
async def send_invoice(
    invoice_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send an invoice to the customer (changes status to 'sent')."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    if invoice.status == "paid":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send a paid invoice",
        )

    if invoice.status == "void":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send a voided invoice",
        )

    invoice.status = "sent"

    # TODO: Actually send email to customer when email service is implemented

    await db.commit()
    await db.refresh(invoice)
    return invoice_to_response(invoice)


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
async def mark_invoice_paid(
    invoice_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark an invoice as paid."""
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.customer))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found",
        )

    if invoice.status == "void":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark a voided invoice as paid",
        )

    invoice.status = "paid"
    invoice.paid_date = datetime.now().strftime("%Y-%m-%d")

    await db.commit()
    await db.refresh(invoice)
    return invoice_to_response(invoice)
