"""
Public API Module

Provides OAuth2-authenticated public API endpoints for external integrations.
All endpoints are prefixed with /api/public/v1.

Security Features:
- OAuth2 client credentials flow for authentication
- Per-client rate limiting
- Scope-based authorization
- Request logging and auditing
"""

from fastapi import APIRouter

# Create the main public API router
router = APIRouter(prefix="/api/public/v1", tags=["Public API"])
