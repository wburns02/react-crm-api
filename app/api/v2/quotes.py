"""
Quotes API - Manage customer quotes and estimates.
"""

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import Response
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.quote import Quote
from app.models.customer import Customer
from app.schemas.quote import (
    QuoteCreate,
    QuoteUpdate,
    QuoteResponse,
    QuoteListResponse,
    QuoteConvertRequest,
    QuoteConvertResponse,
)
from app.models.work_order import WorkOrder

# PDF Generation imports
try:
    from weasyprint import HTML

    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    WEASYPRINT_AVAILABLE = False

router = APIRouter()


def generate_quote_number() -> str:
    """Generate a unique quote number."""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"Q-{timestamp}-{unique_id}"


def build_customer_address(customer: Customer) -> str:
    """Build a formatted address string from customer fields."""
    parts = []
    if customer.address_line1:
        parts.append(customer.address_line1)
    if customer.city:
        city_state = customer.city
        if customer.state:
            city_state += f", {customer.state}"
        if customer.postal_code:
            city_state += f" {customer.postal_code}"
        parts.append(city_state)
    return ", ".join(parts) if parts else None


async def enrich_quote_with_customer(quote: Quote, db: DbSession) -> dict:
    """Enrich a quote with customer details."""
    # Fetch customer data
    customer_result = await db.execute(select(Customer).where(Customer.id == quote.customer_id))
    customer = customer_result.scalar_one_or_none()

    # Build response dict from quote
    quote_dict = {
        "id": quote.id,
        "quote_number": quote.quote_number,
        "customer_id": quote.customer_id,
        "title": quote.title,
        "description": quote.description,
        "line_items": quote.line_items or [],
        "subtotal": quote.subtotal,
        "tax_rate": quote.tax_rate,
        "tax": quote.tax,
        "discount": quote.discount,
        "total": quote.total,
        "status": quote.status,
        "valid_until": quote.valid_until,
        "notes": quote.notes,
        "terms": quote.terms,
        "signature_data": quote.signature_data,
        "signed_at": quote.signed_at,
        "signed_by": quote.signed_by,
        "approval_status": quote.approval_status,
        "approved_by": quote.approved_by,
        "approved_at": quote.approved_at,
        "converted_to_work_order_id": quote.converted_to_work_order_id,
        "converted_at": quote.converted_at,
        "created_at": quote.created_at,
        "updated_at": quote.updated_at,
        "sent_at": quote.sent_at,
    }

    # Add customer details if found
    if customer:
        quote_dict["customer_name"] = f"{customer.first_name or ''} {customer.last_name or ''}".strip() or None
        quote_dict["customer_email"] = customer.email
        quote_dict["customer_phone"] = customer.phone
        quote_dict["customer_address"] = build_customer_address(customer)
    else:
        quote_dict["customer_name"] = None
        quote_dict["customer_email"] = None
        quote_dict["customer_phone"] = None
        quote_dict["customer_address"] = None

    return quote_dict


@router.get("/", response_model=QuoteListResponse)
async def list_quotes(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """List quotes with pagination and filtering."""
    # Base query
    query = select(Quote)

    # Apply filters
    if customer_id:
        query = query.where(Quote.customer_id == customer_id)

    if status:
        query = query.where(Quote.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Quote.created_at.desc())

    # Execute query
    result = await db.execute(query)
    quotes = result.scalars().all()

    return QuoteListResponse(
        items=quotes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{quote_id}", response_model=QuoteResponse)
async def get_quote(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single quote by ID with customer details."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    # Enrich with customer data
    return await enrich_quote_with_customer(quote, db)


@router.post("/", response_model=QuoteResponse, status_code=status.HTTP_201_CREATED)
async def create_quote(
    quote_data: QuoteCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new quote."""
    data = quote_data.model_dump()
    data["quote_number"] = generate_quote_number()

    quote = Quote(**data)

    # Calculate totals from line items
    quote.calculate_totals()

    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: str,
    quote_data: QuoteUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a quote."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    # Update only provided fields
    update_data = quote_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(quote, field, value)

    # Recalculate totals if line_items changed
    if "line_items" in update_data:
        quote.calculate_totals()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a quote as sent."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    quote.status = "sent"
    quote.sent_at = datetime.utcnow()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/accept", response_model=QuoteResponse)
async def accept_quote(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a quote as accepted by customer."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    if quote.status not in ["sent", "draft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot accept quote with status '{quote.status}'. Must be 'sent' or 'draft'.",
        )

    quote.status = "accepted"

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/decline", response_model=QuoteResponse)
async def decline_quote(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a quote as declined by customer."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    if quote.status not in ["sent", "draft"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot decline quote with status '{quote.status}'. Must be 'sent' or 'draft'.",
        )

    quote.status = "declined"

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/convert", response_model=QuoteConvertResponse)
async def convert_quote_to_work_order(
    quote_id: str,
    convert_data: QuoteConvertRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Convert an accepted quote to a work order.

    Creates a new WorkOrder with the quote's customer, total amount,
    and service address. The quote is marked as 'converted' and linked
    to the new work order.
    """
    # Fetch the quote
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    if quote.status not in ["sent", "accepted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only sent or accepted quotes can be converted",
        )

    if quote.converted_to_work_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quote already converted to work order {quote.converted_to_work_order_id}",
        )

    # Fetch customer for service address
    customer_result = await db.execute(select(Customer).where(Customer.id == quote.customer_id))
    customer = customer_result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer not found for this quote",
        )

    # Generate UUID for work order (WorkOrder.id is String(36))
    work_order_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Build notes from quote title/description
    notes_parts = []
    if quote.title:
        notes_parts.append(f"From Quote: {quote.title}")
    if quote.description:
        notes_parts.append(quote.description)
    if convert_data.notes:
        notes_parts.append(convert_data.notes)

    # Include line items summary in notes
    if quote.line_items:
        line_items_summary = "\n\nQuote Line Items:"
        for item in quote.line_items:
            service = item.get("service", item.get("description", "Item"))
            qty = item.get("quantity", 1)
            amount = item.get("amount", 0)
            line_items_summary += f"\n- {service} (x{qty}): ${amount:.2f}"
        notes_parts.append(line_items_summary)

    combined_notes = "\n\n".join(notes_parts) if notes_parts else None

    # Create the WorkOrder
    work_order = WorkOrder(
        id=work_order_id,
        customer_id=quote.customer_id,
        technician_id=convert_data.technician_id,
        job_type=convert_data.job_type,
        priority=convert_data.priority,
        status="draft",
        scheduled_date=convert_data.scheduled_date,
        service_address_line1=customer.address_line1,
        service_address_line2=customer.address_line2,
        service_city=customer.city,
        service_state=customer.state,
        service_postal_code=customer.postal_code,
        service_latitude=customer.latitude if hasattr(customer, "latitude") else None,
        service_longitude=customer.longitude if hasattr(customer, "longitude") else None,
        notes=combined_notes,
        total_amount=quote.total,
        created_at=now,
        updated_at=now,
    )

    db.add(work_order)

    # Update the quote
    quote.status = "converted"
    quote.converted_at = now
    quote.converted_to_work_order_id = work_order_id

    await db.commit()
    await db.refresh(quote)
    await db.refresh(work_order)

    # Enrich quote with customer data for response
    quote_response = await enrich_quote_with_customer(quote, db)

    return QuoteConvertResponse(
        quote=QuoteResponse(**quote_response),
        work_order_id=work_order_id,
        message=f"Successfully created work order {work_order_id} from quote {quote.quote_number}",
    )


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a quote."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    await db.delete(quote)
    await db.commit()


def generate_quote_pdf_html(quote_data: dict) -> str:
    """Generate HTML template for quote PDF."""
    # Format dates
    created_date = ""
    if quote_data.get("created_at"):
        try:
            if isinstance(quote_data["created_at"], str):
                created_date = quote_data["created_at"][:10]
            else:
                created_date = quote_data["created_at"].strftime("%B %d, %Y")
        except Exception:
            created_date = str(quote_data["created_at"])[:10]

    valid_until = ""
    if quote_data.get("valid_until"):
        try:
            if isinstance(quote_data["valid_until"], str):
                valid_until = quote_data["valid_until"][:10]
            else:
                valid_until = quote_data["valid_until"].strftime("%B %d, %Y")
        except Exception:
            valid_until = str(quote_data["valid_until"])[:10]

    # Generate line items rows
    line_items_html = ""
    for item in quote_data.get("line_items", []):
        service = item.get("service", item.get("description", ""))
        description = item.get("description", "")
        qty = item.get("quantity", 1)
        rate = float(item.get("rate", 0))
        amount = float(item.get("amount", qty * rate))
        line_items_html += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb;">{service}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: center;">{qty}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">${rate:,.2f}</td>
            <td style="padding: 12px; border-bottom: 1px solid #e5e7eb; text-align: right;">${amount:,.2f}</td>
        </tr>
        """

    # Format totals
    subtotal = float(quote_data.get("subtotal", 0) or 0)
    tax = float(quote_data.get("tax", 0) or 0)
    tax_rate = float(quote_data.get("tax_rate", 0) or 0)
    total = float(quote_data.get("total", 0) or 0)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: letter;
                margin: 0.75in;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                color: #1f2937;
                line-height: 1.5;
                font-size: 14px;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 40px;
                border-bottom: 3px solid #4f46e5;
                padding-bottom: 20px;
            }}
            .company-name {{
                font-size: 28px;
                font-weight: bold;
                color: #4f46e5;
                margin-bottom: 5px;
            }}
            .company-info {{
                color: #6b7280;
                font-size: 12px;
            }}
            .estimate-title {{
                text-align: right;
            }}
            .estimate-title h1 {{
                font-size: 32px;
                color: #1f2937;
                margin: 0;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            .estimate-number {{
                font-size: 16px;
                color: #4f46e5;
                font-weight: 600;
                margin-top: 5px;
            }}
            .info-section {{
                display: flex;
                justify-content: space-between;
                margin-bottom: 30px;
            }}
            .info-box {{
                width: 48%;
            }}
            .info-box h3 {{
                font-size: 12px;
                text-transform: uppercase;
                color: #6b7280;
                margin-bottom: 10px;
                letter-spacing: 1px;
            }}
            .info-box p {{
                margin: 3px 0;
            }}
            .customer-name {{
                font-size: 16px;
                font-weight: 600;
                color: #1f2937;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }}
            th {{
                background-color: #4f46e5;
                color: white;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            th:nth-child(2), th:nth-child(3), th:nth-child(4) {{
                text-align: center;
            }}
            th:last-child {{
                text-align: right;
            }}
            .totals {{
                margin-left: auto;
                width: 300px;
            }}
            .totals-row {{
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid #e5e7eb;
            }}
            .totals-row.total {{
                border-bottom: none;
                border-top: 2px solid #4f46e5;
                margin-top: 10px;
                padding-top: 15px;
                font-size: 18px;
                font-weight: bold;
                color: #4f46e5;
            }}
            .notes-section {{
                margin-top: 40px;
                padding: 20px;
                background-color: #f9fafb;
                border-radius: 8px;
            }}
            .notes-section h3 {{
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 10px;
                color: #374151;
            }}
            .notes-section p {{
                margin: 0;
                color: #6b7280;
            }}
            .footer {{
                margin-top: 50px;
                text-align: center;
                color: #9ca3af;
                font-size: 12px;
                border-top: 1px solid #e5e7eb;
                padding-top: 20px;
            }}
            .status-badge {{
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                background-color: #dbeafe;
                color: #1d4ed8;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <div>
                <div class="company-name">Mac Septic Services</div>
                <div class="company-info">
                    Professional Septic Solutions<br>
                    Texas Licensed & Insured
                </div>
            </div>
            <div class="estimate-title">
                <h1>Estimate</h1>
                <div class="estimate-number">{quote_data.get("quote_number", f"EST-{quote_data.get('id', '')}")}</div>
            </div>
        </div>

        <div class="info-section">
            <div class="info-box">
                <h3>Bill To</h3>
                <p class="customer-name">{quote_data.get("customer_name", "Customer")}</p>
                <p>{quote_data.get("customer_address", "") or ""}</p>
                <p>{quote_data.get("customer_email", "") or ""}</p>
                <p>{quote_data.get("customer_phone", "") or ""}</p>
            </div>
            <div class="info-box" style="text-align: right;">
                <h3>Estimate Details</h3>
                <p><strong>Date:</strong> {created_date}</p>
                <p><strong>Valid Until:</strong> {valid_until or "N/A"}</p>
                <p><strong>Status:</strong> <span class="status-badge">{quote_data.get("status", "draft").upper()}</span></p>
            </div>
        </div>

        <table>
            <thead>
                <tr>
                    <th>Description</th>
                    <th>Qty</th>
                    <th>Rate</th>
                    <th>Amount</th>
                </tr>
            </thead>
            <tbody>
                {line_items_html if line_items_html else '<tr><td colspan="4" style="padding: 20px; text-align: center; color: #9ca3af;">No line items</td></tr>'}
            </tbody>
        </table>

        <div class="totals">
            <div class="totals-row">
                <span>Subtotal</span>
                <span>${subtotal:,.2f}</span>
            </div>
            <div class="totals-row">
                <span>Tax ({tax_rate}%)</span>
                <span>${tax:,.2f}</span>
            </div>
            <div class="totals-row total">
                <span>Total</span>
                <span>${total:,.2f}</span>
            </div>
        </div>

        {"<div class='notes-section'><h3>Notes</h3><p>" + (quote_data.get("notes") or "") + "</p></div>" if quote_data.get("notes") else ""}

        {"<div class='notes-section'><h3>Terms & Conditions</h3><p>" + (quote_data.get("terms") or "") + "</p></div>" if quote_data.get("terms") else ""}

        <div class="footer">
            <p>Thank you for considering Mac Septic Services!</p>
            <p>Questions? Contact us at support@macseptic.com</p>
        </div>
    </body>
    </html>
    """
    return html


@router.get("/{quote_id}/pdf")
async def generate_quote_pdf(
    quote_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate and download PDF for a quote."""
    if not WEASYPRINT_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="PDF generation is not available. WeasyPrint not installed.",
        )

    # Get quote
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    # Enrich with customer data
    quote_data = await enrich_quote_with_customer(quote, db)

    # Generate HTML
    html_content = generate_quote_pdf_html(quote_data)

    # Convert to PDF
    try:
        pdf_bytes = HTML(string=html_content).write_pdf()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate PDF: {str(e)}",
        )

    # Generate filename
    quote_number = quote_data.get("quote_number", f"EST-{quote_id}")
    filename = f"Estimate_{quote_number}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
        },
    )
