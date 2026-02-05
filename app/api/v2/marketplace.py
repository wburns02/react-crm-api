"""
Marketplace API Endpoints

Third-party integration directory.

NOTE: Marketplace is not yet backed by a database. Not in sidebar navigation.
Endpoints return empty results until a real app marketplace is implemented.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Schemas (kept for future implementation)
# =============================================================================


class CategoryStat(BaseModel):
    """Category statistics."""

    category: str
    count: int


# =============================================================================
# API Endpoints - Return empty results (no mock data)
# =============================================================================


@router.get("/apps")
async def get_marketplace_apps(
    db: DbSession,
    current_user: CurrentUser,
    category: Optional[str] = None,
    status: Optional[str] = None,
    pricing: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "popular",
    page: int = 1,
    page_size: int = 12,
) -> dict:
    """Get marketplace apps. Returns empty list - marketplace not yet implemented."""
    return {"apps": [], "total": 0, "page": page, "pageSize": page_size}


@router.get("/apps/{app_id}")
async def get_marketplace_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> dict:
    """Get single marketplace app."""
    raise HTTPException(status_code=404, detail="App not found")


@router.get("/apps/{app_id}/reviews")
async def get_app_reviews(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> list:
    """Get reviews for an app."""
    return []


@router.get("/featured")
async def get_featured_apps(
    db: DbSession,
    current_user: CurrentUser,
) -> list:
    """Get featured apps."""
    return []


@router.get("/categories")
async def get_category_stats(
    db: DbSession,
    current_user: CurrentUser,
) -> list[CategoryStat]:
    """Get category statistics."""
    return []


@router.get("/installed")
async def get_installed_apps(
    db: DbSession,
    current_user: CurrentUser,
) -> list:
    """Get installed apps for current account."""
    return []


@router.post("/install")
async def install_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> dict:
    """Install an app. Not yet implemented."""
    raise HTTPException(
        status_code=501,
        detail="App installation not yet implemented. Marketplace coming soon.",
    )


@router.delete("/installed/{app_id}")
async def uninstall_app(
    db: DbSession,
    current_user: CurrentUser,
    app_id: str,
) -> dict:
    """Uninstall an app."""
    raise HTTPException(status_code=404, detail="No installed apps found")
