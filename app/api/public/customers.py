"""
Public API - Customer Endpoints

Provides public API access to customer resources with OAuth2 authentication.
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Query, Depends, Response
from sqlalchemy import select, func, or_
from pydantic import BaseModel, EmailStr, Field

from app.schemas.types import UUIDStr

from app.api.public.deps import PublicAPIClient, DbSession, require_scope
from app.models.customer import Customer
from app.core.rate_limit import get_public_api_rate_limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["Public API - Customers"])


# ============================================================================
# Schemas (Simplified for Public API)
# ============================================================================


class PublicCustomerBase(BaseModel):
    """Base customer schema for public API."""

    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=50)
    postal_code: Optional[str] = Field(None, max_length=20)
    customer_type: Optional[str] = None
    tags: Optional[str] = None


class PublicCustomerCreate(PublicCustomerBase):
    """Schema for creating a customer via public API."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)


class PublicCustomerUpdate(PublicCustomerBase):
    """Schema for updating a customer via public API."""

    pass


class PublicCustomerResponse(PublicCustomerBase):
    """Schema for customer response in public API."""

    id: UUIDStr
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PublicCustomerListResponse(BaseModel):
    """Paginated customer list response."""

    items: list[PublicCustomerResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "",
    response_model=PublicCustomerListResponse,
    dependencies=[Depends(require_scope("customers:read"))],
    summary="List Customers",
    description="""
    List customers with pagination and filtering.

    **Required Scope:** `customers:read` or `customers` or `admin`

    **Pagination:**
    - `page`: Page number (default: 1)
    - `page_size`: Items per page (default: 20, max: 100)

    **Filtering:**
    - `search`: Search by name, email, or phone
    - `customer_type`: Filter by customer type
    - `is_active`: Filter by active status
    """,
)
async def list_customers(
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search term"),
    customer_type: Optional[str] = Query(None, description="Filter by type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """List customers with pagination and optional filtering."""
    # Build query
    query = select(Customer)

    # Apply filters
    if search:
        search_filter = or_(
            Customer.first_name.ilike(f"%{search}%"),
            Customer.last_name.ilike(f"%{search}%"),
            Customer.email.ilike(f"%{search}%"),
            Customer.phone.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)

    if customer_type:
        query = query.where(Customer.customer_type == customer_type)

    if is_active is not None:
        query = query.where(Customer.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Customer.created_at.desc())

    # Execute query
    result = await db.execute(query)
    customers = result.scalars().all()

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.debug(f"Customer list request by {client.client_id}: returned {len(customers)} of {total}")

    return PublicCustomerListResponse(
        items=customers,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(customers)) < total,
    )


@router.get(
    "/{customer_id}",
    response_model=PublicCustomerResponse,
    dependencies=[Depends(require_scope("customers:read"))],
    summary="Get Customer",
    description="""
    Get a single customer by ID.

    **Required Scope:** `customers:read` or `customers` or `admin`
    """,
)
async def get_customer(
    customer_id: str,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Get a single customer by ID."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Customer with ID {customer_id} not found",
            },
        )

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.debug(f"Customer {customer_id} retrieved by {client.client_id}")

    return customer


@router.post(
    "",
    response_model=PublicCustomerResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_scope("customers:write"))],
    summary="Create Customer",
    description="""
    Create a new customer.

    **Required Scope:** `customers:write` or `customers` or `admin`
    """,
)
async def create_customer(
    customer_data: PublicCustomerCreate,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Create a new customer."""
    # Create customer
    customer = Customer(
        **customer_data.model_dump(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.info(f"Customer created via public API: {customer.id} by {client.client_id}")

    return customer


@router.put(
    "/{customer_id}",
    response_model=PublicCustomerResponse,
    dependencies=[Depends(require_scope("customers:write"))],
    summary="Update Customer",
    description="""
    Update an existing customer.

    **Required Scope:** `customers:write` or `customers` or `admin`

    Only provided fields will be updated.
    """,
)
async def update_customer(
    customer_id: str,
    customer_data: PublicCustomerUpdate,
    response: Response,
    db: DbSession,
    client: PublicAPIClient,
):
    """Update a customer."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Customer with ID {customer_id} not found",
            },
        )

    # Update only provided fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)

    customer.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(customer)

    # Add rate limit headers
    rate_limiter = get_public_api_rate_limiter()
    headers = rate_limiter.get_rate_limit_headers(
        client.client_id,
        client.rate_limit_per_minute,
    )
    for key, value in headers.items():
        response.headers[key] = value

    logger.info(f"Customer updated via public API: {customer.id} by {client.client_id}")

    return customer


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_scope("customers:write"))],
    summary="Delete Customer",
    description="""
    Delete a customer.

    **Required Scope:** `customers:write` or `customers` or `admin`

    Note: This performs a hard delete. Consider using PUT to set `is_active: false` instead.
    """,
)
async def delete_customer(
    customer_id: str,
    db: DbSession,
    client: PublicAPIClient,
):
    """Delete a customer."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "not_found",
                "message": f"Customer with ID {customer_id} not found",
            },
        )

    await db.delete(customer)
    await db.commit()

    logger.info(f"Customer deleted via public API: {customer_id} by {client.client_id}")
