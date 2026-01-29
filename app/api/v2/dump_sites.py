"""Dump Sites API endpoints for waste disposal location management."""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from app.api.deps import DbSession, CurrentUser
from app.models.dump_site import DumpSite

router = APIRouter()


# Pydantic Schemas
class DumpSiteBase(BaseModel):
    name: str
    address_state: str
    fee_per_gallon: float
    address_line1: Optional[str] = None
    address_city: Optional[str] = None
    address_postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool = True
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    hours_of_operation: Optional[str] = None


class DumpSiteCreate(DumpSiteBase):
    pass


class DumpSiteUpdate(BaseModel):
    name: Optional[str] = None
    address_state: Optional[str] = None
    fee_per_gallon: Optional[float] = None
    address_line1: Optional[str] = None
    address_city: Optional[str] = None
    address_postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    hours_of_operation: Optional[str] = None


@router.get("/")
async def list_dump_sites(
    db: DbSession,
    current_user: CurrentUser,
    state: Optional[str] = Query(None, description="Filter by state (TX, SC, TN)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """List all dump sites with optional filtering."""
    query = select(DumpSite)

    if state:
        query = query.where(DumpSite.address_state == state.upper())

    if is_active is not None:
        query = query.where(DumpSite.is_active == is_active)

    query = query.order_by(DumpSite.address_state, DumpSite.name)

    result = await db.execute(query)
    sites = result.scalars().all()

    return {
        "sites": [
            {
                "id": str(site.id),
                "name": site.name,
                "address_line1": site.address_line1,
                "address_city": site.address_city,
                "address_state": site.address_state,
                "address_postal_code": site.address_postal_code,
                "latitude": site.latitude,
                "longitude": site.longitude,
                "fee_per_gallon": site.fee_per_gallon,
                "is_active": site.is_active,
                "notes": site.notes,
                "contact_name": site.contact_name,
                "contact_phone": site.contact_phone,
                "hours_of_operation": getattr(site, 'hours_of_operation', None),
                "created_at": site.created_at.isoformat() if site.created_at else None,
                "updated_at": site.updated_at.isoformat() if site.updated_at else None,
            }
            for site in sites
        ],
        "total": len(sites),
    }


@router.get("/{site_id}")
async def get_dump_site(
    site_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single dump site by ID."""
    result = await db.execute(select(DumpSite).where(DumpSite.id == site_id))
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dump site not found",
        )

    return {
        "id": str(site.id),
        "name": site.name,
        "address_line1": site.address_line1,
        "address_city": site.address_city,
        "address_state": site.address_state,
        "address_postal_code": site.address_postal_code,
        "latitude": site.latitude,
        "longitude": site.longitude,
        "fee_per_gallon": site.fee_per_gallon,
        "is_active": site.is_active,
        "notes": site.notes,
        "contact_name": site.contact_name,
        "contact_phone": site.contact_phone,
        "hours_of_operation": getattr(site, 'hours_of_operation', None),
        "created_at": site.created_at.isoformat() if site.created_at else None,
        "updated_at": site.updated_at.isoformat() if site.updated_at else None,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_dump_site(
    request: DumpSiteCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new dump site."""
    # Validate fee is positive
    if request.fee_per_gallon <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fee per gallon must be greater than 0",
        )

    # Normalize state to uppercase
    state = request.address_state.upper()
    if len(state) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="State must be a 2-letter code (e.g., TX, SC, TN)",
        )

    site = DumpSite(
        name=request.name,
        address_line1=request.address_line1,
        address_city=request.address_city,
        address_state=state,
        address_postal_code=request.address_postal_code,
        latitude=request.latitude,
        longitude=request.longitude,
        fee_per_gallon=request.fee_per_gallon,
        is_active=request.is_active,
        notes=request.notes,
        contact_name=request.contact_name,
        contact_phone=request.contact_phone,
        # hours_of_operation will be added after migration 027 runs
    )

    db.add(site)
    await db.commit()
    await db.refresh(site)

    return {
        "id": str(site.id),
        "name": site.name,
        "address_state": site.address_state,
        "fee_per_gallon": site.fee_per_gallon,
        "is_active": site.is_active,
        "created_at": site.created_at.isoformat() if site.created_at else None,
    }


@router.patch("/{site_id}")
async def update_dump_site(
    site_id: str,
    request: DumpSiteUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an existing dump site."""
    result = await db.execute(select(DumpSite).where(DumpSite.id == site_id))
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dump site not found",
        )

    # Update only provided fields
    update_data = request.model_dump(exclude_unset=True)

    # Validate fee if provided
    if "fee_per_gallon" in update_data and update_data["fee_per_gallon"] <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fee per gallon must be greater than 0",
        )

    # Normalize state if provided
    if "address_state" in update_data:
        update_data["address_state"] = update_data["address_state"].upper()

    for field, value in update_data.items():
        setattr(site, field, value)

    await db.commit()
    await db.refresh(site)

    return {
        "id": str(site.id),
        "name": site.name,
        "address_state": site.address_state,
        "fee_per_gallon": site.fee_per_gallon,
        "is_active": site.is_active,
        "updated_at": site.updated_at.isoformat() if site.updated_at else None,
    }


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dump_site(
    site_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Soft delete a dump site (marks as inactive)."""
    result = await db.execute(select(DumpSite).where(DumpSite.id == site_id))
    site = result.scalar_one_or_none()

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dump site not found",
        )

    # Soft delete - mark as inactive
    site.is_active = False
    await db.commit()
