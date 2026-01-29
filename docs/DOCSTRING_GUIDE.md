# Docstring Standards Guide

This guide defines documentation standards for the React CRM API codebase using Google-style docstrings.

## Function Docstrings

```python
def create_customer(
    db: AsyncSession,
    customer_data: CustomerCreate,
    current_user: User,
) -> Customer:
    """
    Create a new customer in the database.

    Creates a customer record with the provided data and associates it
    with the current user's organization.

    Args:
        db: Database session for the operation.
        customer_data: Validated customer creation data.
        current_user: Authenticated user making the request.

    Returns:
        The newly created customer with generated ID and timestamps.

    Raises:
        ConflictError: If a customer with the same email already exists.
        ValidationError: If the customer data fails business validation.

    Example:
        >>> customer = await create_customer(db, data, user)
        >>> print(customer.id)
        123
    """
```

## Class Docstrings

```python
class CustomerService:
    """
    Service layer for customer operations.

    Handles business logic for customer management including CRUD operations,
    validation, and integration with external services.

    Attributes:
        db: Database session for operations.
        cache: Optional cache client for read-through caching.

    Example:
        >>> service = CustomerService(db)
        >>> customer = await service.get_by_id(123)
    """
```

## API Endpoint Docstrings

```python
@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
    responses=get_error_responses(401, 404, 500)
)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CustomerResponse:
    """
    Retrieve a customer by ID.

    Returns the full customer record including contact information,
    service history summary, and account status.

    Args:
        customer_id: Unique identifier of the customer.
        db: Database session (injected).
        current_user: Authenticated user (injected).

    Returns:
        CustomerResponse: Complete customer data.

    Raises:
        HTTPException 401: If not authenticated.
        HTTPException 404: If customer not found.
    """
```

## Module Docstrings

```python
"""
Customer service module.

Provides business logic for customer management operations including:
- CRUD operations for customer records
- Customer search and filtering
- Service history aggregation
- Integration with billing system

Dependencies:
    - app.models.customer: Customer model
    - app.schemas.customer: Pydantic schemas
    - app.services.billing: Billing integration

Example:
    >>> from app.services.customer import CustomerService
    >>> service = CustomerService(db)
    >>> customers = await service.search("john")
"""
```

## Type Hints

Always use type hints for function arguments and return values:

```python
from typing import Optional, List

async def search_customers(
    query: str,
    limit: int = 20,
    offset: int = 0,
    active_only: bool = True,
) -> List[Customer]:
    """Search customers by name or email."""
```

## Docstring Sections

Use these sections in order when applicable:

1. **Summary line** - One-line description (required)
2. **Extended description** - Multi-line elaboration (optional)
3. **Args** - Parameter descriptions (if any)
4. **Returns** - Return value description (if not None)
5. **Raises** - Exceptions that may be raised (if any)
6. **Example** - Usage example (for complex functions)
7. **Note** - Special considerations (optional)
8. **Warning** - Important caveats (optional)

## Constants and Configuration

```python
# Maximum customers per page in list endpoints
MAX_PAGE_SIZE = 100

# Cache TTL for customer lookup (seconds)
CUSTOMER_CACHE_TTL = 300
```

## Private Functions

Private functions (prefixed with `_`) need minimal documentation:

```python
def _normalize_phone(phone: str) -> str:
    """Normalize phone number to E.164 format."""
```

## When to Document

- **Always**: Public functions, classes, modules, API endpoints
- **Recommended**: Complex private functions, non-obvious algorithms
- **Optional**: Simple helper functions, obvious one-liners

## OpenAPI Integration

For FastAPI endpoints, add response documentation:

```python
from app.schemas.errors import get_error_responses, CRUD_ERROR_RESPONSES

@router.post(
    "/",
    response_model=CustomerResponse,
    responses=CRUD_ERROR_RESPONSES,
    summary="Create a new customer",
    description="Creates a customer record with contact and service information.",
)
```
