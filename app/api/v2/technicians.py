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
        "skills": tech.skills or [],
        "assigned_vehicle": tech.assigned_vehicle,
        "vehicle_capacity_gallons": tech.vehicle_capacity_gallons,
        "license_number": tech.license_number,
        "license_expiry": str(tech.license_expiry) if tech.license_expiry else None,
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
        from sqlalchemy import text as sql_text

        # Use raw SQL to avoid ORM issues
        sql = """
            SELECT id, first_name, last_name, email, phone, employee_id, is_active,
                   skills, assigned_vehicle, vehicle_capacity_gallons,
                   license_number, license_expiry, hourly_rate, notes,
                   home_region, home_address, home_city, home_state, home_postal_code,
                   home_latitude, home_longitude, created_at, updated_at
            FROM technicians
            ORDER BY first_name, last_name
            LIMIT :limit OFFSET :offset
        """
        offset = (page - 1) * page_size
        result = await db.execute(sql_text(sql), {"limit": page_size, "offset": offset})
        rows = result.fetchall()

        # Count total
        count_result = await db.execute(sql_text("SELECT COUNT(*) FROM technicians"))
        total = count_result.scalar()

        # Convert rows to response dicts
        items = []
        for row in rows:
            items.append({
                "id": str(row[0]),
                "first_name": row[1],
                "last_name": row[2],
                "full_name": f"{row[1]} {row[2]}",
                "email": row[3],
                "phone": row[4],
                "employee_id": row[5],
                "is_active": row[6],
                "skills": row[7] or [],
                "assigned_vehicle": row[8],
                "vehicle_capacity_gallons": row[9],
                "license_number": row[10],
                "license_expiry": str(row[11]) if row[11] else None,
                "hourly_rate": row[12],
                "notes": row[13],
                "home_region": row[14],
                "home_address": row[15],
                "home_city": row[16],
                "home_state": row[17],
                "home_postal_code": row[18],
                "home_latitude": row[19],
                "home_longitude": row[20],
                "created_at": row[21].isoformat() if row[21] else None,
                "updated_at": row[22].isoformat() if row[22] else None,
            })

        return {
            "items": items,
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
