"""Equipment API - Customer equipment tracking (septic tanks, pumps, etc.)."""
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
from datetime import datetime, date
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.equipment import Equipment
from app.schemas.equipment import (
    EquipmentCreate,
    EquipmentUpdate,
    EquipmentResponse,
    EquipmentListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse date string to date object."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def format_date(d: Optional[date]) -> Optional[str]:
    """Format date object to string."""
    if not d:
        return None
    return d.isoformat() if hasattr(d, 'isoformat') else str(d)


def equipment_to_response(equipment: Equipment) -> dict:
    """Convert Equipment model to response dict."""
    return {
        "id": str(equipment.id),
        "customer_id": str(equipment.customer_id),
        "equipment_type": equipment.equipment_type,
        "manufacturer": equipment.manufacturer,
        "model": equipment.model,
        "serial_number": equipment.serial_number,
        "capacity_gallons": equipment.capacity_gallons,
        "size_description": equipment.size_description,
        "install_date": format_date(equipment.install_date),
        "installed_by": equipment.installed_by,
        "warranty_expiry": format_date(equipment.warranty_expiry),
        "warranty_notes": equipment.warranty_notes,
        "last_service_date": format_date(equipment.last_service_date),
        "next_service_date": format_date(equipment.next_service_date),
        "service_interval_months": equipment.service_interval_months,
        "location_description": equipment.location_description,
        "latitude": equipment.latitude,
        "longitude": equipment.longitude,
        "condition": equipment.condition,
        "notes": equipment.notes,
        "is_active": equipment.is_active,
        "created_at": equipment.created_at.isoformat() if equipment.created_at else None,
        "updated_at": equipment.updated_at.isoformat() if equipment.updated_at else None,
    }


@router.get("")
async def list_equipment(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[str] = None,
    equipment_type: Optional[str] = None,
    condition: Optional[str] = None,
    is_active: Optional[str] = None,
    needs_service: Optional[bool] = None,  # Equipment where next_service_date <= today
):
    """List equipment with pagination and filtering."""
    try:
        # Base query
        query = select(Equipment)

        # Apply filters
        if customer_id:
            query = query.where(Equipment.customer_id == int(customer_id))

        if equipment_type:
            query = query.where(Equipment.equipment_type == equipment_type)

        if condition:
            query = query.where(Equipment.condition == condition)

        if is_active:
            query = query.where(Equipment.is_active == is_active)

        if needs_service:
            today = date.today()
            query = query.where(Equipment.next_service_date <= today)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Equipment.created_at.desc())

        # Execute query
        result = await db.execute(query)
        equipment_list = result.scalars().all()

        return {
            "items": [equipment_to_response(e) for e in equipment_list],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        import traceback
        logger.error(f"Error in list_equipment: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "error": str(e)}


@router.get("/{equipment_id}", response_model=EquipmentResponse)
async def get_equipment(
    equipment_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single equipment record by ID."""
    result = await db.execute(select(Equipment).where(Equipment.id == equipment_id))
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found",
        )

    return equipment_to_response(equipment)


@router.post("", response_model=EquipmentResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment(
    equipment_data: EquipmentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new equipment record."""
    data = equipment_data.model_dump()

    # Convert customer_id from string to int
    data["customer_id"] = int(data["customer_id"])

    # Parse date fields
    for date_field in ["install_date", "warranty_expiry", "last_service_date", "next_service_date"]:
        if data.get(date_field):
            data[date_field] = parse_date(data[date_field])

    equipment = Equipment(**data)
    db.add(equipment)
    await db.commit()
    await db.refresh(equipment)
    return equipment_to_response(equipment)


@router.patch("/{equipment_id}", response_model=EquipmentResponse)
async def update_equipment(
    equipment_id: str,
    equipment_data: EquipmentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an equipment record."""
    result = await db.execute(select(Equipment).where(Equipment.id == equipment_id))
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found",
        )

    # Update only provided fields
    update_data = equipment_data.model_dump(exclude_unset=True)

    # Parse date fields
    for date_field in ["install_date", "warranty_expiry", "last_service_date", "next_service_date"]:
        if date_field in update_data and update_data[date_field]:
            update_data[date_field] = parse_date(update_data[date_field])

    for field, value in update_data.items():
        setattr(equipment, field, value)

    await db.commit()
    await db.refresh(equipment)
    return equipment_to_response(equipment)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_equipment(
    equipment_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an equipment record."""
    result = await db.execute(select(Equipment).where(Equipment.id == equipment_id))
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Equipment not found",
        )

    await db.delete(equipment)
    await db.commit()


@router.get("/customer/{customer_id}/service-due")
async def get_customer_service_due(
    customer_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get all equipment for a customer that needs service."""
    today = date.today()
    query = select(Equipment).where(
        Equipment.customer_id == int(customer_id),
        Equipment.next_service_date <= today,
        Equipment.is_active == "active"
    ).order_by(Equipment.next_service_date)

    result = await db.execute(query)
    equipment_list = result.scalars().all()

    return {
        "items": [equipment_to_response(e) for e in equipment_list],
        "total": len(equipment_list),
    }
