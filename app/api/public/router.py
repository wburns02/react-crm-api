"""
Public API Router

Combines all public API endpoints under /api/public/v1.
"""

from fastapi import APIRouter

from app.api.public import oauth, customers, work_orders

# Create the main public API router
public_router = APIRouter()

# Include OAuth endpoints (no prefix - they're already at /oauth/*)
public_router.include_router(oauth.router)

# Include resource endpoints
public_router.include_router(customers.router)
public_router.include_router(work_orders.router)
