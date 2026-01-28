"""
Quotes API - Manage customer quotes and estimates.
"""
from fastapi import APIRouter, HTTPException, status, Query
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
)

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
    customer_result = await db.execute(
        select(Customer).where(Customer.id == quote.customer_id)
    )
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
    customer_id: Optional[int] = None,
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
    quote_id: int,
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
    data['quote_number'] = generate_quote_number()

    quote = Quote(**data)

    # Calculate totals from line items
    quote.calculate_totals()

    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


@router.patch("/{quote_id}", response_model=QuoteResponse)
async def update_quote(
    quote_id: int,
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
    if 'line_items' in update_data:
        quote.calculate_totals()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/send", response_model=QuoteResponse)
async def send_quote(
    quote_id: int,
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
    quote_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Mark a quote as accepted."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    quote.status = "accepted"

    await db.commit()
    await db.refresh(quote)
    return quote


@router.post("/{quote_id}/convert", response_model=QuoteResponse)
async def convert_quote_to_work_order(
    quote_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Convert an accepted quote to a work order."""
    result = await db.execute(select(Quote).where(Quote.id == quote_id))
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quote not found",
        )

    if quote.status not in ['sent', 'accepted']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only sent or accepted quotes can be converted",
        )

    # TODO: Create work order from quote
    # For now, just mark as converted
    quote.status = "converted"
    quote.converted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(quote)
    return quote


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: int,
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
