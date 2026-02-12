from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_
from typing import Optional

from app.api.deps import DbSession, CurrentUser
from app.models.customer import Customer
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse,
)
from app.schemas.errors import LIST_ERROR_RESPONSES, CRUD_ERROR_RESPONSES

router = APIRouter()


@router.get(
    "/",
    response_model=CustomerListResponse,
    responses=LIST_ERROR_RESPONSES,
    summary="List customers",
    description="Returns a paginated list of customers with optional filtering by search term, type, stage, and status.",
)
async def list_customers(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    customer_type: Optional[str] = None,
    prospect_stage: Optional[str] = None,
    is_active: Optional[bool] = True,
    include_all: Optional[bool] = None,
):
    """List customers with pagination and filtering."""
    # Base query
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

    if prospect_stage:
        query = query.where(Customer.prospect_stage == prospect_stage)

    # Default to active-only; pass include_all=true to see everything
    if not include_all and is_active is not None:
        query = query.where(Customer.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Customer.created_at.desc())

    # Execute query
    result = await db.execute(query)
    customers = result.scalars().all()

    return CustomerListResponse(
        items=customers,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    responses=CRUD_ERROR_RESPONSES,
    summary="Get customer by ID",
    description="Returns a single customer record with all details including contact information and service history.",
)
async def get_customer(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single customer by ID."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    return customer


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new customer."""
    customer = Customer(**customer_data.model_dump())
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    # Try to set the customer_uuid for invoice FK optimization
    # This may fail if migration 040 hasn't run yet, which is OK
    try:
        customer.ensure_uuid()
        await db.commit()
        await db.refresh(customer)
    except Exception:
        # Column doesn't exist yet - that's OK, app works without it
        pass

    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_data: CustomerUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a customer."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Update only provided fields
    update_data = customer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)

    await db.commit()
    await db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a customer (soft delete - sets is_active=false).

    Note: Hard delete is not possible due to foreign key constraints
    from work_orders, messages, activities, invoices, and many other tables.
    """
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    # Soft delete - set is_active to False instead of hard delete
    # This preserves data integrity and historical records
    customer.is_active = False
    await db.commit()
