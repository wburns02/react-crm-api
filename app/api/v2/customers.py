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

router = APIRouter()


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    customer_type: Optional[str] = None,
    prospect_stage: Optional[str] = None,
    is_active: Optional[bool] = None,
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

    if is_active is not None:
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


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
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
    return customer


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
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
    customer_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a customer."""
    result = await db.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found",
        )

    await db.delete(customer)
    await db.commit()
