"""
Estimates API - Alias for Quotes API.
The frontend uses /estimates for listing while /quotes is used for CRUD.
This provides compatibility for the estimates listing endpoint.
"""
from fastapi import APIRouter, Query, HTTPException, status
from sqlalchemy import select, func
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.quote import Quote
from app.models.customer import Customer
from app.schemas.quote import QuoteListResponse, QuoteResponse
from app.api.v2.quotes import enrich_quote_with_customer

router = APIRouter()


@router.get("/", response_model=QuoteListResponse)
async def list_estimates(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    """List estimates/quotes with pagination and filtering."""
    # Base query
    query = select(Quote)

    # Apply filters
    if customer_id:
        query = query.where(Quote.customer_id == customer_id)

    if status_filter:
        query = query.where(Quote.status == status_filter)

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

    # Enrich each quote with customer data
    enriched_quotes = []
    for quote in quotes:
        enriched = await enrich_quote_with_customer(quote, db)
        enriched_quotes.append(enriched)

    return QuoteListResponse(
        items=enriched_quotes,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{estimate_id}", response_model=QuoteResponse)
async def get_estimate(
    estimate_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single estimate/quote by ID with customer details."""
    result = await db.execute(
        select(Quote).where(Quote.id == estimate_id)
    )
    quote = result.scalar_one_or_none()

    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Estimate not found",
        )

    # Enrich with customer data
    return await enrich_quote_with_customer(quote, db)
