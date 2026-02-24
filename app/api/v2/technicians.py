from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, or_, text as sql_text
from typing import Optional, Literal
import logging

from app.api.deps import DbSession, CurrentUser, EntityCtx
from app.models.technician import Technician
from app.schemas.technician import (
    TechnicianCreate,
    TechnicianUpdate,
    TechnicianResponse,
    TechnicianListResponse,
    TechnicianPerformanceStats,
    TechnicianJobDetail,
    TechnicianJobsResponse,
)
from app.services.cache_service import get_cache_service, TTL

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


@router.get("")
async def list_technicians(
    db: DbSession,
    current_user: CurrentUser,
    entity: EntityCtx,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    active_only: Optional[bool] = True,
):
    """List technicians with pagination and filtering."""
    # Check cache first
    cache = get_cache_service()
    cache_key = f"technicians:list:{page}:{page_size}:{search}:{active_only}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        from sqlalchemy import text as sql_text

        # Build WHERE clause based on filters
        where_clauses = []
        params = {"limit": page_size, "offset": (page - 1) * page_size}

        if active_only:
            where_clauses.append("is_active = true")

        if search:
            where_clauses.append(
                "(first_name ILIKE :search OR last_name ILIKE :search OR email ILIKE :search OR employee_id ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        # Multi-entity filtering
        if entity:
            if entity.is_default:
                where_clauses.append("(entity_id = :entity_id OR entity_id IS NULL)")
            else:
                where_clauses.append("entity_id = :entity_id")
            params["entity_id"] = str(entity.id)

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        # Use raw SQL to avoid ORM issues
        sql = f"""
            SELECT id, first_name, last_name, email, phone, employee_id, is_active,
                   skills, assigned_vehicle, vehicle_capacity_gallons,
                   license_number, license_expiry, hourly_rate, notes,
                   home_region, home_address, home_city, home_state, home_postal_code,
                   home_latitude, home_longitude, created_at, updated_at
            FROM technicians
            {where_sql}
            ORDER BY first_name, last_name
            LIMIT :limit OFFSET :offset
        """
        result = await db.execute(sql_text(sql), params)
        rows = result.fetchall()

        # Count total with same filter
        count_sql = f"SELECT COUNT(*) FROM technicians {where_sql}"
        count_result = await db.execute(sql_text(count_sql), params)
        total = count_result.scalar()

        # Convert rows to response dicts
        items = []
        for row in rows:
            first_name = row[1] or ""
            last_name = row[2] or ""

            # Handle skills - may be list, tuple, or comma-separated string
            # Note: Database has corrupted data where skills were stored as char arrays
            skills_val = row[7]
            if skills_val is None:
                skills = []
            elif isinstance(skills_val, (list, tuple)):
                # Check if this is a corrupted char array (all items are single chars)
                if skills_val and all(isinstance(s, str) and len(s) <= 1 for s in skills_val):
                    joined = "".join(skills_val)
                    skills = [s.strip() for s in joined.split(",") if s.strip()]
                else:
                    skills = list(skills_val)
            elif isinstance(skills_val, str):
                skills = [s.strip() for s in skills_val.split(",") if s.strip()]
            else:
                skills = []

            # Handle datetime fields - convert to ISO string for serialization
            created_at = None
            if row[21]:
                try:
                    created_at = row[21].isoformat() if hasattr(row[21], "isoformat") else str(row[21])
                except Exception:
                    created_at = None

            updated_at = None
            if row[22]:
                try:
                    updated_at = row[22].isoformat() if hasattr(row[22], "isoformat") else str(row[22])
                except Exception:
                    updated_at = None

            items.append(
                {
                    "id": str(row[0]),
                    "first_name": first_name,
                    "last_name": last_name,
                    "full_name": f"{first_name} {last_name}".strip(),
                    "email": row[3],
                    "phone": row[4],
                    "employee_id": row[5],
                    "is_active": bool(row[6]) if row[6] is not None else True,
                    "skills": skills,
                    "assigned_vehicle": row[8],
                    "vehicle_capacity_gallons": float(row[9]) if row[9] else None,
                    "license_number": row[10],
                    "license_expiry": str(row[11]) if row[11] else None,
                    "hourly_rate": float(row[12]) if row[12] else None,
                    "notes": row[13],
                    "home_region": row[14],
                    "home_address": row[15],
                    "home_city": row[16],
                    "home_state": row[17],
                    "home_postal_code": row[18],
                    "home_latitude": float(row[19]) if row[19] else None,
                    "home_longitude": float(row[20]) if row[20] else None,
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        result = {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
        await cache.set(cache_key, result, ttl=TTL.LONG)
        return result
    except Exception as e:
        import traceback

        logger.error(f"Error in list_technicians: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching technicians",
        )


# =====================================================
# Performance Stats Endpoints (MUST be before /{technician_id})
# =====================================================


@router.get("/{technician_id}/performance", response_model=TechnicianPerformanceStats)
async def get_technician_performance(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get aggregated performance statistics for a technician."""
    import traceback

    try:
        # First verify technician exists
        tech_result = await db.execute(select(Technician).where(Technician.id == technician_id))
        if not tech_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # Get performance stats using raw SQL for efficiency
        stats_sql = """
            WITH completed_jobs AS (
                SELECT
                    id, customer_id, job_type,
                    COALESCE(total_amount, 0) as total_amount,
                    scheduled_date
                FROM work_orders
                WHERE technician_id = :tech_id
                  AND status = 'completed'
            ),
            returns_calc AS (
                SELECT COUNT(DISTINCT c1.id) as return_count
                FROM completed_jobs c1
                WHERE EXISTS (
                    SELECT 1 FROM completed_jobs c2
                    WHERE c1.customer_id = c2.customer_id
                      AND c1.id != c2.id
                      AND c1.scheduled_date > c2.scheduled_date
                      AND c1.scheduled_date - c2.scheduled_date <= 30
                )
            )
            SELECT
                COUNT(*) as total_jobs,
                COALESCE(SUM(total_amount), 0) as total_revenue,
                COUNT(*) FILTER (WHERE job_type IN ('pumping', 'grease_trap')) as pump_out_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('pumping', 'grease_trap')), 0) as pump_out_revenue,
                COUNT(*) FILTER (WHERE job_type IN ('repair', 'maintenance')) as repair_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type IN ('repair', 'maintenance')), 0) as repair_revenue,
                COUNT(*) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')) as other_jobs,
                COALESCE(SUM(total_amount) FILTER (WHERE job_type NOT IN ('pumping', 'grease_trap', 'repair', 'maintenance')), 0) as other_revenue,
                COALESCE((SELECT return_count FROM returns_calc), 0) as returns_count
            FROM completed_jobs
        """

        result = await db.execute(sql_text(stats_sql), {"tech_id": technician_id})
        row = result.fetchone()

        if row:
            return TechnicianPerformanceStats(
                technician_id=technician_id,
                total_jobs_completed=int(row[0] or 0),
                total_revenue=float(row[1] or 0),
                pump_out_jobs=int(row[2] or 0),
                pump_out_revenue=float(row[3] or 0),
                repair_jobs=int(row[4] or 0),
                repair_revenue=float(row[5] or 0),
                other_jobs=int(row[6] or 0),
                other_revenue=float(row[7] or 0),
                returns_count=int(row[8] or 0),
            )
        else:
            return TechnicianPerformanceStats(technician_id=technician_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technician performance: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get performance stats: {str(e)}"
        )


@router.get("/{technician_id}/jobs", response_model=TechnicianJobsResponse)
async def get_technician_jobs(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
    job_category: Literal["pump_outs", "repairs", "all"] = Query("all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get detailed list of jobs for a technician."""
    import traceback
    import re

    try:
        # First verify technician exists
        tech_result = await db.execute(select(Technician).where(Technician.id == technician_id))
        if not tech_result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Technician not found",
            )

        # Build job type filter
        if job_category == "pump_outs":
            job_type_filter = "AND wo.job_type IN ('pumping', 'grease_trap')"
        elif job_category == "repairs":
            job_type_filter = "AND wo.job_type IN ('repair', 'maintenance')"
        else:
            job_type_filter = ""

        offset = (page - 1) * page_size

        # Get jobs with customer info
        jobs_sql = f"""
            SELECT
                wo.id,
                wo.scheduled_date::text,
                wo.actual_end_time::text as completed_date,
                wo.customer_id,
                COALESCE(c.first_name || ' ' || c.last_name, 'Customer #' || wo.customer_id::text) as customer_name,
                COALESCE(
                    NULLIF(TRIM(COALESCE(wo.service_address_line1, '') || ' ' || COALESCE(wo.service_city, '') || ', ' || COALESCE(wo.service_state, '')), ' , '),
                    'No address'
                ) as service_location,
                wo.job_type,
                wo.status,
                COALESCE(wo.total_amount, 0) as total_amount,
                wo.total_labor_minutes as duration_minutes,
                wo.notes,
                wo.estimated_duration_hours as labor_hours,
                0.0 as parts_cost
            FROM work_orders wo
            LEFT JOIN customers c ON wo.customer_id = c.id
            WHERE wo.technician_id = :tech_id
              AND wo.status = 'completed'
              {job_type_filter}
            ORDER BY wo.scheduled_date DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """

        result = await db.execute(sql_text(jobs_sql), {"tech_id": technician_id, "limit": page_size, "offset": offset})
        rows = result.fetchall()

        # Get total count
        count_sql = f"""
            SELECT COUNT(*)
            FROM work_orders wo
            WHERE wo.technician_id = :tech_id
              AND wo.status = 'completed'
              {job_type_filter}
        """
        count_result = await db.execute(sql_text(count_sql), {"tech_id": technician_id})
        total = count_result.scalar() or 0

        # Build response items
        items = []
        for row in rows:
            gallons_pumped = None
            tank_size = None
            notes = row[10] or ""

            if row[6] in ("pumping", "grease_trap"):
                gallon_match = re.search(r"(\d+)\s*(?:gallons?|gal)", notes, re.IGNORECASE)
                if gallon_match:
                    gallons_pumped = int(gallon_match.group(1))
                tank_match = re.search(r"(\d+)\s*(?:gallon)?\s*tank", notes, re.IGNORECASE)
                if tank_match:
                    tank_size = f"{tank_match.group(1)} gallon"

            items.append(
                TechnicianJobDetail(
                    id=str(row[0]),
                    scheduled_date=row[1],
                    completed_date=row[2],
                    customer_id=row[3],
                    customer_name=row[4],
                    service_location=row[5],
                    job_type=row[6],
                    status=row[7],
                    total_amount=float(row[8] or 0),
                    duration_minutes=int(row[9]) if row[9] else None,
                    notes=notes if notes else None,
                    gallons_pumped=gallons_pumped,
                    tank_size=tank_size,
                    labor_hours=float(row[11]) if row[11] else None,
                    parts_cost=float(row[12]) if row[12] else None,
                )
            )

        return TechnicianJobsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            job_category=job_category,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting technician jobs: {traceback.format_exc()}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get jobs: {str(e)}")


# =====================================================
# Basic CRUD Endpoints
# =====================================================


@router.get("/{technician_id}", response_model=TechnicianResponse)
async def get_technician(
    technician_id: str,
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


@router.post("", response_model=TechnicianResponse, status_code=status.HTTP_201_CREATED)
async def create_technician(
    technician_data: TechnicianCreate,
    db: DbSession,
    current_user: CurrentUser,
    entity: EntityCtx,
):
    """Create a new technician."""
    import uuid
    from datetime import datetime

    try:
        tech_data = technician_data.model_dump()
        tech_data["id"] = uuid.uuid4()  # UUID object (not string) — DB column is native uuid
        tech_data["created_at"] = datetime.utcnow()
        tech_data["updated_at"] = datetime.utcnow()

        # Remove None employee_id to avoid unique constraint issues with empty strings
        if tech_data.get("employee_id") is None or tech_data.get("employee_id") == "":
            tech_data.pop("employee_id", None)

        # Convert vehicle_capacity_gallons to int if present (model expects Integer)
        if tech_data.get("vehicle_capacity_gallons") is not None:
            tech_data["vehicle_capacity_gallons"] = int(tech_data["vehicle_capacity_gallons"])

        if entity:
            tech_data["entity_id"] = entity.id
        technician = Technician(**tech_data)
        db.add(technician)
        await db.commit()
        await db.refresh(technician)
        await get_cache_service().delete_pattern("technicians:*")
        await get_cache_service().delete_pattern("dashboard:*")
        return technician_to_response(technician)
    except Exception as e:
        logger.error(f"Error creating technician: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create technician",
        )


@router.patch("/{technician_id}", response_model=TechnicianResponse)
async def update_technician(
    technician_id: str,
    technician_data: TechnicianUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a technician."""
    try:
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
        await get_cache_service().delete_pattern("technicians:*")
        await get_cache_service().delete_pattern("dashboard:*")
        return technician_to_response(technician)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating technician {technician_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update technician",
        )


@router.delete("/{technician_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_technician(
    technician_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a technician (soft delete - sets is_active=false)."""
    try:
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
        await get_cache_service().delete_pattern("technicians:*")
        await get_cache_service().delete_pattern("dashboard:*")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting technician {technician_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete technician",
        )
