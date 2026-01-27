"""
Estimates API - Alias for Quotes API.
The frontend uses /estimates for listing while /quotes is used for CRUD.
This provides compatibility for the estimates listing endpoint.
"""
from fastapi import APIRouter, Query
from sqlalchemy import select, func
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.quote import Quote
from app.schemas.quote import QuoteListResponse

router = APIRouter()


@router.get("/", response_model=QuoteListResponse)
async def list_estimates(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    customer_id: Optional[int] = None,
    status: Optional[str] = None,
):
    """List estimates/quotes with pagination and filtering."""
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
