from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.technician import Technician
from app.schemas.technician import (
    TechnicianCreate,
    TechnicianUpdate,
    TechnicianResponse,
    TechnicianListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def technician_to_response(tech: Technician) -> dict:
    """Convert Technician model to response dict with string ID."""
    return {
        "id": str(tech.id),
        "first_name": tech.first_name,
        "last_name": tech.last_name,
        "full_name": f"{tech.first_name} {tech.last_name}",
        "email": tech.email,
        "phone": tech.phone,
        "employee_id": tech.employee_id,
        "is_active": tech.is_active,
        "home_region": tech.home_region,
        "home_address": tech.home_address,
        "home_city": tech.home_city,
        "home_state": tech.home_state,
        "home_postal_code": tech.home_postal_code,
        "home_latitude": tech.home_latitude,
        "home_longitude": tech.home_longitude,
        "skills": tech.skills,
        "assigned_vehicle": tech.assigned_vehicle,
        "vehicle_capacity_gallons": tech.vehicle_capacity_gallons,
        "license_number": tech.license_number,
        "license_expiry": tech.license_expiry,
        "hourly_rate": tech.hourly_rate,
        "notes": tech.notes,
        "created_at": tech.created_at.isoformat() if tech.created_at else None,
        "updated_at": tech.updated_at.isoformat() if tech.updated_at else None,
    }


@router.get("/", response_model=TechnicianListResponse)
async def list_technicians(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    active_only: Optional[bool] = None,
):
    """List technicians with pagination and filtering."""
    try:
        # Base query
        query = select(Technician)

        # Apply filters
        if search:
            search_filter = or_(
                Technician.first_name.ilike(f"%{search}%"),
                Technician.last_name.ilike(f"%{search}%"),
                Technician.email.ilike(f"%{search}%"),
                Technician.phone.ilike(f"%{search}%"),
                Technician.employee_id.ilike(f"%{search}%"),
            )
            query = query.where(search_filter)

        if active_only is True:
            query = query.where(Technician.is_active == True)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Technician.first_name, Technician.last_name)

        # Execute query
        result = await db.execute(query)
        technicians = result.scalars().all()

        return {
            "items": [technician_to_response(t) for t in technicians],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing technicians: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {type(e).__name__}: {str(e)}"
        )


@router.get("/{technician_id}", response_model=TechnicianResponse)
async def get_technician(
    technician_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single technician by ID."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    return technician_to_response(technician)


@router.post("/", response_model=TechnicianResponse, status_code=status.HTTP_201_CREATED)
async def create_technician(
    technician_data: TechnicianCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new technician."""
    technician = Technician(**technician_data.model_dump())
    db.add(technician)
    await db.commit()
    await db.refresh(technician)
    return technician_to_response(technician)


@router.patch("/{technician_id}", response_model=TechnicianResponse)
async def update_technician(
    technician_id: int,
    technician_data: TechnicianUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a technician."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # Update only provided fields
    update_data = technician_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(technician, field, value)

    await db.commit()
    await db.refresh(technician)
    return technician_to_response(technician)


@router.delete("/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_technician(
    technician_id: int,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a technician (soft delete - sets is_active=false)."""
    result = await db.execute(select(Technician).where(Technician.id == technician_id))
    technician = result.scalar_one_or_none()

    if not technician:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Technician not found",
        )

    # Soft delete - set is_active to False
    technician.is_active = False
    await db.commit()
